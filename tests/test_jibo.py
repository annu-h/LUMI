"""
LUMI — Tests for JIBO Kids Integration

Comprehensive test suite using small synthetic fixtures.
Does NOT require the full dataset or a loaded AI model.

Tests cover:
  - Dataset discovery
  - Audio/transcript matching
  - Missing and malformed transcripts
  - Stable IDs
  - Manifest generation and loading
  - Incremental rescanning
  - Catalog queries for letters and digits
  - Evaluation reference normalization
  - WER calculation
  - Missing model and audio handling
  - Preservation of original source data
"""

import json
import os
import struct
import tempfile
from pathlib import Path

import pytest

from src.jibo_adapter import (
    JiboDatasetAdapter,
    JiboRecord,
    WAVInfo,
    generate_inventory_report,
    make_record_id,
    parse_child_code,
    read_wav_info,
    sha256_file,
    TASK_CATEGORIES,
)
from src.jibo_catalog import (
    EducationalRecord,
    JiboEducationalCatalog,
    identify_letter_or_digit,
)
from src.jibo_eval import (
    compute_wer,
    normalize_for_wer,
    is_unintelligible,
    EvalReport,
    EvalSample,
)


# ---------------------------------------------------------------------------
# Fixtures: synthetic WAV files and dataset structure
# ---------------------------------------------------------------------------

def make_wav_bytes(
    sample_rate: int = 16000,
    channels: int = 1,
    bits: int = 16,
    num_samples: int = 16000,  # 1 second of audio
) -> bytes:
    """Create a minimal valid WAV file in memory."""
    bytes_per_sample = bits // 8
    data_size = num_samples * channels * bytes_per_sample
    fmt_size = 16
    riff_size = 4 + (8 + fmt_size) + (8 + data_size)

    buf = bytearray()
    # RIFF header
    buf += b"RIFF"
    buf += struct.pack("<I", riff_size)
    buf += b"WAVE"

    # fmt chunk
    buf += b"fmt "
    buf += struct.pack("<I", fmt_size)
    buf += struct.pack("<H", 1)  # PCM
    buf += struct.pack("<H", channels)
    buf += struct.pack("<I", sample_rate)
    buf += struct.pack("<I", sample_rate * channels * bytes_per_sample)  # byte_rate
    buf += struct.pack("<H", channels * bytes_per_sample)  # block_align
    buf += struct.pack("<H", bits)

    # data chunk
    buf += b"data"
    buf += struct.pack("<I", data_size)
    buf += b"\x00" * data_size

    return bytes(buf)


@pytest.fixture
def synthetic_dataset(tmp_path):
    """Create a synthetic JIBO-like dataset directory."""
    data_dir = tmp_path / "data"

    # Create letters_digits with WAV + TXT pairs
    ld_dir = data_dir / "letters_digits"
    ld_dir.mkdir(parents=True)

    # Sample files following TXYY7ZZZ naming
    samples = [
        ("T1017001_letters", "A"),
        ("T1017002_letters", "B"),
        ("T1027003_digits", "1"),
        ("T1027004_digits", "five"),
        ("T2017005_letters", "zee"),
    ]

    for stem, transcript in samples:
        wav_path = ld_dir / f"{stem}.wav"
        txt_path = ld_dir / f"{stem}.txt"
        wav_path.write_bytes(make_wav_bytes())
        txt_path.write_text(transcript, encoding="utf-8")

    # Add a WAV without transcript (missing transcript)
    orphan_wav = ld_dir / "T1017006_letters.wav"
    orphan_wav.write_bytes(make_wav_bytes())

    # Add a transcript without WAV (orphan transcript)
    orphan_txt = ld_dir / "T1017007_letters.txt"
    orphan_txt.write_text("C", encoding="utf-8")

    # Create brush directory with a sample
    brush_dir = data_dir / "brush"
    brush_dir.mkdir()
    (brush_dir / "T1027010_brush.wav").write_bytes(make_wav_bytes())
    (brush_dir / "T1027010_brush.txt").write_text(
        "you put the toothpaste on", encoding="utf-8"
    )

    # Create colors directory with a sample
    colors_dir = data_dir / "colors"
    colors_dir.mkdir()
    (colors_dir / "T2027020_colors.wav").write_bytes(make_wav_bytes())
    (colors_dir / "T2027020_colors.txt").write_text(
        "you mix red and blue", encoding="utf-8"
    )

    # Create blocks directory (empty — tests missing category handling)
    blocks_dir = data_dir / "blocks"
    blocks_dir.mkdir()

    return tmp_path


# ---------------------------------------------------------------------------
# Tests: Dataset Discovery
# ---------------------------------------------------------------------------

class TestDatasetDiscovery:
    def test_available_when_data_dir_exists(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset)
        assert adapter.is_available()

    def test_not_available_when_no_data_dir(self, tmp_path):
        adapter = JiboDatasetAdapter(tmp_path)
        assert not adapter.is_available()

    def test_scan_returns_records(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        assert len(records) > 0

    def test_scan_finds_all_wav_files(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        # 5 letter_digits WAVs + 1 orphan WAV (no transcript) + 1 brush + 1 colors = 8
        wav_count = sum(1 for r in records if r.audio_path.endswith(".wav"))
        assert wav_count == 8

    def test_scan_empty_dataset_returns_empty(self, tmp_path):
        (tmp_path / "data").mkdir()
        adapter = JiboDatasetAdapter(tmp_path)
        records = adapter.scan()
        assert records == []


# ---------------------------------------------------------------------------
# Tests: Audio/Transcript Matching
# ---------------------------------------------------------------------------

class TestAudioTranscriptMatching:
    def test_matching_pairs_found(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        paired = [r for r in records if r.transcript_path is not None]
        # 5 letter_digits pairs + 1 brush + 1 colors = 7
        assert len(paired) == 7

    def test_missing_transcript_flagged(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        missing = [r for r in records if "missing_transcript" in r.issues]
        assert len(missing) == 1
        assert "T1017006" in missing[0].audio_path

    def test_transcript_text_loaded(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        for r in records:
            if r.transcript_path:
                assert r.transcript_text is not None
                assert len(r.transcript_text) > 0


# ---------------------------------------------------------------------------
# Tests: Missing and Malformed Transcripts
# ---------------------------------------------------------------------------

class TestMalformedTranscripts:
    def test_malformed_wav_detected(self, tmp_path):
        data_dir = tmp_path / "data" / "letters_digits"
        data_dir.mkdir(parents=True)

        # Write invalid WAV content
        bad_wav = data_dir / "T1017099_test.wav"
        bad_wav.write_bytes(b"NOT_A_WAV_FILE")
        (data_dir / "T1017099_test.txt").write_text("A", encoding="utf-8")

        adapter = JiboDatasetAdapter(tmp_path, compute_hashes=False)
        records = adapter.scan()
        bad = [r for r in records if "corrupt_or_unreadable_wav" in r.issues]
        assert len(bad) == 1

    def test_empty_transcript_preserved(self, tmp_path):
        data_dir = tmp_path / "data" / "letters_digits"
        data_dir.mkdir(parents=True)
        (data_dir / "T1017099_test.wav").write_bytes(make_wav_bytes())
        (data_dir / "T1017099_test.txt").write_text("", encoding="utf-8")

        adapter = JiboDatasetAdapter(tmp_path, compute_hashes=False)
        records = adapter.scan()
        assert records[0].transcript_text == ""


# ---------------------------------------------------------------------------
# Tests: Stable IDs
# ---------------------------------------------------------------------------

class TestStableIDs:
    def test_same_input_produces_same_id(self):
        id1 = make_record_id("letters_digits", "data/letters_digits/T1017001.wav")
        id2 = make_record_id("letters_digits", "data/letters_digits/T1017001.wav")
        assert id1 == id2

    def test_different_inputs_produce_different_ids(self):
        id1 = make_record_id("letters_digits", "data/letters_digits/T1017001.wav")
        id2 = make_record_id("letters_digits", "data/letters_digits/T1017002.wav")
        assert id1 != id2

    def test_id_is_deterministic_hex(self):
        rid = make_record_id("brush", "data/brush/T1027010.wav")
        assert len(rid) == 16
        assert all(c in "0123456789abcdef" for c in rid)

    def test_path_normalization(self):
        """Forward and backslashes produce the same ID."""
        id1 = make_record_id("letters_digits", "data\\letters_digits\\test.wav")
        id2 = make_record_id("letters_digits", "data/letters_digits/test.wav")
        assert id1 == id2


# ---------------------------------------------------------------------------
# Tests: Manifest Generation and Loading
# ---------------------------------------------------------------------------

class TestManifest:
    def test_write_and_load_manifest(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        adapter.write_manifest(records)

        assert adapter.manifest_path.exists()

        meta, loaded = adapter.load_manifest()
        assert meta is not None
        assert meta.total_records == len(records)
        assert len(loaded) == len(records)

    def test_manifest_is_jsonl(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        adapter.write_manifest(records)

        with open(adapter.manifest_path, "r") as f:
            lines = f.readlines()

        # First line is metadata, rest are records
        assert len(lines) == len(records) + 1

        # Each line is valid JSON
        for line in lines:
            json.loads(line)

    def test_manifest_metadata_correct(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        adapter.write_manifest(records)

        meta, _ = adapter.load_manifest()
        assert meta.dataset_name == "jibo_kids"
        assert meta.version == "1.0.0"
        assert meta.total_records == len(records)

    def test_loaded_records_preserve_data(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        adapter.write_manifest(records)

        _, loaded = adapter.load_manifest()

        for orig, loaded_rec in zip(records, loaded):
            assert orig.record_id == loaded_rec.record_id
            assert orig.audio_path == loaded_rec.audio_path
            assert orig.task_category == loaded_rec.task_category
            assert orig.transcript_text == loaded_rec.transcript_text


# ---------------------------------------------------------------------------
# Tests: Incremental Rescanning
# ---------------------------------------------------------------------------

class TestIncrementalScan:
    def test_incremental_detects_new_files(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        adapter.write_manifest(records)
        original_count = len(records)

        # Add a new file
        new_wav = synthetic_dataset / "data" / "letters_digits" / "T1017099_new.wav"
        new_wav.write_bytes(make_wav_bytes())
        (synthetic_dataset / "data" / "letters_digits" / "T1017099_new.txt").write_text(
            "Z", encoding="utf-8"
        )

        updated = adapter.incremental_scan()
        assert len(updated) == original_count + 1

    def test_incremental_no_changes(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        adapter.write_manifest(records)

        updated = adapter.incremental_scan()
        assert len(updated) == len(records)


# ---------------------------------------------------------------------------
# Tests: Child Code Parsing
# ---------------------------------------------------------------------------

class TestChildCodeParsing:
    def test_valid_code(self):
        result = parse_child_code("T1027235_letters")
        assert result["child_code"] == "T1027235"
        assert result["study_year"] == 1
        assert result["school_year"] == "02"
        assert result["child_id"] == "235"
        assert result["gender_hint"] == "male"  # 235 is odd

    def test_female_child(self):
        result = parse_child_code("T2017002_digits")
        assert result["gender_hint"] == "female"  # 002 is even

    def test_pre_kindergarten(self):
        result = parse_child_code("T1017100")
        assert result["school_year"] == "01"

    def test_no_match(self):
        result = parse_child_code("random_file_name")
        assert result["child_code"] is None

    def test_grade_1(self):
        result = parse_child_code("T2037300_test")
        assert result["school_year"] == "03"


# ---------------------------------------------------------------------------
# Tests: WAV Info Reading
# ---------------------------------------------------------------------------

class TestWAVInfo:
    def test_valid_wav(self, tmp_path):
        wav_path = tmp_path / "test.wav"
        wav_path.write_bytes(make_wav_bytes(sample_rate=16000, channels=1, num_samples=16000))

        info = read_wav_info(wav_path)
        assert info is not None
        assert info.sample_rate == 16000
        assert info.channels == 1
        assert info.bits_per_sample == 16
        assert info.duration_s == pytest.approx(1.0, abs=0.01)

    def test_invalid_wav(self, tmp_path):
        bad_path = tmp_path / "bad.wav"
        bad_path.write_bytes(b"NOT_A_WAV")
        info = read_wav_info(bad_path)
        assert info is None

    def test_stereo_wav(self, tmp_path):
        wav_path = tmp_path / "stereo.wav"
        wav_path.write_bytes(make_wav_bytes(channels=2, num_samples=8000))
        info = read_wav_info(wav_path)
        assert info is not None
        assert info.channels == 2


# ---------------------------------------------------------------------------
# Tests: Catalog Queries for Letters and Digits
# ---------------------------------------------------------------------------

class TestEducationalCatalog:
    def _make_catalog(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        catalog = JiboEducationalCatalog()
        catalog.build_from_jibo_records(records)
        return catalog

    def test_catalog_has_letters(self, synthetic_dataset):
        catalog = self._make_catalog(synthetic_dataset)
        letters = catalog.query_letters()
        assert len(letters) > 0

    def test_query_specific_letter(self, synthetic_dataset):
        catalog = self._make_catalog(synthetic_dataset)
        a_records = catalog.query_letters("A")
        assert len(a_records) >= 1
        assert all(r.target_value == "A" for r in a_records)

    def test_query_specific_digit(self, synthetic_dataset):
        catalog = self._make_catalog(synthetic_dataset)
        one_records = catalog.query_digits("1")
        # "1" transcript → digit
        assert len(one_records) >= 1

    def test_available_letters(self, synthetic_dataset):
        catalog = self._make_catalog(synthetic_dataset)
        available = catalog.available_letters()
        assert "A" in available
        assert "B" in available

    def test_speech_eval_includes_non_letter_tasks(self, synthetic_dataset):
        catalog = self._make_catalog(synthetic_dataset)
        eval_recs = catalog.query_speech_eval()
        task_cats = {r.task_category for r in eval_recs}
        # Brush and colors tasks should be speech eval
        assert "brush" in task_cats or "colors" in task_cats

    def test_speech_eval_filter_by_task(self, synthetic_dataset):
        catalog = self._make_catalog(synthetic_dataset)
        brush_recs = catalog.query_speech_eval("brush")
        assert all(r.task_category == "brush" for r in brush_recs)

    def test_summary(self, synthetic_dataset):
        catalog = self._make_catalog(synthetic_dataset)
        summary = catalog.summary()
        assert "total_records" in summary
        assert "available_letters" in summary
        assert "available_digits" in summary

    def test_nonexistent_letter_returns_empty(self, synthetic_dataset):
        catalog = self._make_catalog(synthetic_dataset)
        assert catalog.query_letters("Q") == []


# ---------------------------------------------------------------------------
# Tests: Letter/Digit Identification
# ---------------------------------------------------------------------------

class TestLetterDigitIdentification:
    def test_single_letter(self):
        ct, val, conf = identify_letter_or_digit("A")
        assert ct == "letter"
        assert val == "A"
        assert conf == "high"

    def test_letter_name(self):
        ct, val, conf = identify_letter_or_digit("bee")
        assert ct == "letter"
        assert val == "B"
        assert conf == "high"

    def test_single_digit(self):
        ct, val, conf = identify_letter_or_digit("5")
        assert ct == "digit"
        assert val == "5"
        assert conf == "high"

    def test_digit_name(self):
        ct, val, conf = identify_letter_or_digit("five")
        assert ct == "digit"
        assert val == "5"
        assert conf == "high"

    def test_empty_transcript(self):
        ct, val, conf = identify_letter_or_digit("")
        assert ct == "speech_eval"
        assert val is None

    def test_none_transcript(self):
        ct, val, conf = identify_letter_or_digit(None)
        assert ct == "speech_eval"
        assert val is None

    def test_complex_transcript(self):
        ct, val, conf = identify_letter_or_digit(
            "you put the toothpaste on the brush"
        )
        assert ct == "speech_eval"

    def test_bracketed_annotation_removed(self):
        ct, val, conf = identify_letter_or_digit("[unintelligible] A")
        assert ct == "letter"
        assert val == "A"


# ---------------------------------------------------------------------------
# Tests: Evaluation Reference Normalization
# ---------------------------------------------------------------------------

class TestNormalization:
    def test_lowercase(self):
        assert normalize_for_wer("HELLO WORLD") == "hello world"

    def test_remove_brackets(self):
        assert normalize_for_wer("[noise] hello") == "hello"

    def test_remove_punctuation(self):
        assert normalize_for_wer("hello, world!") == "hello world"

    def test_preserve_apostrophes(self):
        assert normalize_for_wer("don't stop") == "don't stop"

    def test_normalize_digit_names(self):
        assert normalize_for_wer("one two three") == "1 2 3"

    def test_normalize_letter_names(self):
        assert normalize_for_wer("bee see dee") == "b c d"

    def test_collapse_whitespace(self):
        assert normalize_for_wer("hello   world") == "hello world"

    def test_empty_string(self):
        assert normalize_for_wer("") == ""

    def test_unintelligible_detection(self):
        assert is_unintelligible("[unintelligible]")
        assert is_unintelligible("[noise] [silence]")
        assert not is_unintelligible("[noise] hello")
        assert is_unintelligible("")
        assert is_unintelligible(None)


# ---------------------------------------------------------------------------
# Tests: WER Calculation
# ---------------------------------------------------------------------------

class TestWER:
    def test_perfect_match(self):
        wer, detail = compute_wer("hello world", "hello world")
        assert wer == 0.0
        assert detail["errors"] == 0

    def test_complete_mismatch(self):
        wer, detail = compute_wer("hello world", "foo bar")
        assert wer == 1.0
        assert detail["substitutions"] == 2

    def test_insertion(self):
        wer, detail = compute_wer("hello", "hello world")
        assert detail["insertions"] == 1

    def test_deletion(self):
        wer, detail = compute_wer("hello world", "hello")
        assert detail["deletions"] == 1

    def test_empty_reference_empty_hypothesis(self):
        wer, _ = compute_wer("", "")
        assert wer == 0.0

    def test_empty_reference_nonempty_hypothesis(self):
        wer, _ = compute_wer("", "hello")
        assert wer == float("inf")

    def test_single_word(self):
        wer, detail = compute_wer("a", "b")
        assert wer == 1.0
        assert detail["ref_words"] == 1


# ---------------------------------------------------------------------------
# Tests: Missing Model and Audio Handling
# ---------------------------------------------------------------------------

class TestMissingModelHandling:
    def test_eval_report_structure(self):
        report = EvalReport(
            model_name="test",
            device="cpu",
            compute_type="int8",
            beam_size=1,
        )
        assert report.evaluated == 0
        assert report.failed == 0
        assert report.skipped == 0

    def test_eval_sample_error_state(self):
        sample = EvalSample(
            record_id="test",
            audio_path="missing.wav",
            reference_raw="hello",
            reference_normalized="hello",
            hypothesis_raw="",
            hypothesis_normalized="",
            wer=float("inf"),
            status="error",
            error_message="File not found",
        )
        assert sample.status == "error"
        assert sample.error_message is not None


# ---------------------------------------------------------------------------
# Tests: Preservation of Original Source Data
# ---------------------------------------------------------------------------

class TestSourceDataPreservation:
    def test_scan_does_not_modify_files(self, synthetic_dataset):
        # Record file sizes and contents before scan
        data_dir = synthetic_dataset / "data" / "letters_digits"
        before = {}
        for f in data_dir.iterdir():
            before[f.name] = f.read_bytes()

        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=True)
        adapter.scan()

        # Verify files are unchanged
        for f in data_dir.iterdir():
            assert f.read_bytes() == before[f.name], f"File modified: {f.name}"

    def test_manifest_does_not_delete_source_files(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        adapter.write_manifest(records)

        # All original WAV and TXT files still exist
        for r in records:
            wav_path = synthetic_dataset / r.audio_path
            assert wav_path.exists(), f"Source WAV deleted: {r.audio_path}"
            if r.transcript_path:
                txt_path = synthetic_dataset / r.transcript_path
                assert txt_path.exists(), f"Source TXT deleted: {r.transcript_path}"

    def test_original_transcript_preserved_in_catalog(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()

        catalog = JiboEducationalCatalog()
        catalog.build_from_jibo_records(records)

        for rec in catalog.query_letters():
            assert rec.original_transcript is not None


# ---------------------------------------------------------------------------
# Tests: Inventory Report
# ---------------------------------------------------------------------------

class TestInventoryReport:
    def test_report_structure(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=True)
        records = adapter.scan()
        report = generate_inventory_report(records)

        assert report["total_recordings"] == len(records)
        assert "categories" in report
        assert "letters_digits" in report["categories"]
        assert "duplicate_hashes" in report

    def test_report_counts_match(self, synthetic_dataset):
        adapter = JiboDatasetAdapter(synthetic_dataset, compute_hashes=False)
        records = adapter.scan()
        report = generate_inventory_report(records)

        paired = report["records_with_transcripts"]
        missing = report["records_missing_transcripts"]
        assert paired + missing == report["total_recordings"]
