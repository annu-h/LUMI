"""
LUMI — JIBO Kids Dataset Adapter

Discovers and catalogues the JIBO Kids Corpus from a configurable local path.
Parses the real directory and filename structure, links each WAV recording
to its corresponding transcript, generates stable IDs, and builds a
versioned JSONL manifest.

Does NOT copy audio files into the LUMI source tree — originals are
referenced using relative paths.

Privacy: This dataset contains children's speech.  Speaker identifiers
and transcripts must not be logged at DEBUG level or uploaded to external
services.
"""

import hashlib
import json
import logging
import os
import re
import struct
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MANIFEST_VERSION = "1.0.0"
MANIFEST_FILENAME = "jibo_manifest.jsonl"

# Task categories as documented in the JIBO Kids README
TASK_CATEGORIES = {
    "letters_digits": "Letter and digit identification",
    "brush": "Explanation task: brushing teeth",
    "colors": "Explanation task: mixing paint into colors",
    "blocks": "Explanation task: determining number of cubes",
}

# Regex for the TXYY7ZZZ naming convention
# T + X(1-2) + YY(01-03) + 7 + ZZZ(digits)
CHILD_ID_PATTERN = re.compile(
    r"T(?P<study_year>[12])"
    r"(?P<school_year>0[123])"
    r"7"
    r"(?P<child_id>\d{3})"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class WAVInfo:
    """Metadata extracted from a WAV file header (no full decode needed)."""
    sample_rate: int = 0
    channels: int = 0
    bits_per_sample: int = 0
    duration_s: float = 0.0
    file_size: int = 0
    audio_format: int = 1  # 1 = PCM


@dataclass
class JiboRecord:
    """A single audio/transcript pair from the JIBO Kids Corpus."""
    record_id: str                            # Stable, deterministic ID
    task_category: str                        # letters_digits | brush | colors | blocks
    audio_path: str                           # Relative path to WAV
    transcript_path: Optional[str] = None     # Relative path to TXT (None if missing)
    transcript_text: Optional[str] = None     # Contents of transcript file
    child_code: Optional[str] = None          # Full TXYY7ZZZ code
    study_year: Optional[int] = None          # 1 or 2
    school_year: Optional[str] = None         # "01"=Pre-K, "02"=K, "03"=grade 1
    child_id: Optional[str] = None            # ZZZ unique child identifier
    gender_hint: Optional[str] = None         # "male" (odd) | "female" (even)
    wav_info: Optional[WAVInfo] = None
    file_hash: Optional[str] = None           # SHA-256 of the WAV file
    issues: list[str] = field(default_factory=list)


@dataclass
class ManifestMeta:
    """Metadata header for the JSONL manifest."""
    version: str = MANIFEST_VERSION
    dataset_name: str = "jibo_kids"
    dataset_version: str = "v1.0.0"
    created_at: str = ""
    dataset_root: str = ""
    total_records: int = 0
    total_audio_bytes: int = 0
    total_duration_s: float = 0.0
    categories: dict = field(default_factory=dict)
    issues_count: int = 0


# ---------------------------------------------------------------------------
# WAV header reader (minimal, no dependency beyond struct)
# ---------------------------------------------------------------------------

def read_wav_info(wav_path: Path) -> Optional[WAVInfo]:
    """Read WAV header without decoding the entire file.

    Returns None if the file cannot be parsed as a valid WAV.
    """
    try:
        file_size = wav_path.stat().st_size
        with open(wav_path, "rb") as f:
            # RIFF header
            riff = f.read(12)
            if len(riff) < 12 or riff[:4] != b"RIFF" or riff[8:12] != b"WAVE":
                return None

            # Find 'fmt ' chunk
            while True:
                chunk_header = f.read(8)
                if len(chunk_header) < 8:
                    return None
                chunk_id = chunk_header[:4]
                chunk_size = struct.unpack("<I", chunk_header[4:8])[0]

                if chunk_id == b"fmt ":
                    if chunk_size < 16:
                        return None
                    fmt_data = f.read(16)
                    audio_format = struct.unpack("<H", fmt_data[0:2])[0]
                    channels = struct.unpack("<H", fmt_data[2:4])[0]
                    sample_rate = struct.unpack("<I", fmt_data[4:8])[0]
                    # byte_rate = struct.unpack("<I", fmt_data[8:12])[0]
                    # block_align = struct.unpack("<H", fmt_data[12:14])[0]
                    bits_per_sample = struct.unpack("<H", fmt_data[14:16])[0]

                    # Skip rest of fmt chunk
                    remaining = chunk_size - 16
                    if remaining > 0:
                        f.seek(remaining, 1)

                    # Find 'data' chunk for duration
                    while True:
                        dh = f.read(8)
                        if len(dh) < 8:
                            # No data chunk found — estimate from file size
                            data_bytes = max(0, file_size - 44)
                            break
                        did = dh[:4]
                        dsz = struct.unpack("<I", dh[4:8])[0]
                        if did == b"data":
                            data_bytes = dsz
                            break
                        f.seek(dsz, 1)

                    bytes_per_sample = max(1, bits_per_sample // 8)
                    total_samples = data_bytes / (channels * bytes_per_sample)
                    duration_s = total_samples / sample_rate if sample_rate else 0.0

                    return WAVInfo(
                        sample_rate=sample_rate,
                        channels=channels,
                        bits_per_sample=bits_per_sample,
                        duration_s=round(duration_s, 3),
                        file_size=file_size,
                        audio_format=audio_format,
                    )
                else:
                    f.seek(chunk_size, 1)

    except (OSError, struct.error) as exc:
        logger.debug("WAV parse error for %s: %s", wav_path.name, exc)
        return None


# ---------------------------------------------------------------------------
# File hashing
# ---------------------------------------------------------------------------

def sha256_file(path: Path, chunk_size: int = 65536) -> str:
    """Compute SHA-256 hex digest of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Child-code parsing
# ---------------------------------------------------------------------------

def parse_child_code(filename: str) -> dict:
    """Extract child metadata from TXYY7ZZZ naming convention.

    Returns a dict with keys: child_code, study_year, school_year,
    child_id, gender_hint.  All values are None if parsing fails.
    """
    result = {
        "child_code": None,
        "study_year": None,
        "school_year": None,
        "child_id": None,
        "gender_hint": None,
    }
    # Search anywhere in the filename
    m = CHILD_ID_PATTERN.search(filename)
    if m:
        result["child_code"] = m.group(0)
        result["study_year"] = int(m.group("study_year"))
        result["school_year"] = m.group("school_year")
        cid = m.group("child_id")
        result["child_id"] = cid
        try:
            result["gender_hint"] = "male" if int(cid) % 2 == 1 else "female"
        except ValueError:
            pass
    return result


# ---------------------------------------------------------------------------
# Stable ID generation
# ---------------------------------------------------------------------------

def make_record_id(task_category: str, relative_audio_path: str) -> str:
    """Generate a stable, deterministic record ID.

    Based on task category and the relative audio path (forward-slash
    normalized).  This is reproducible across runs and platforms.
    """
    normalized = relative_audio_path.replace("\\", "/")
    raw = f"jibo:{task_category}:{normalized}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Dataset scanner
# ---------------------------------------------------------------------------

class JiboDatasetAdapter:
    """Discovers and catalogues the JIBO Kids Corpus from a local path.

    Usage:
        adapter = JiboDatasetAdapter("/path/to/Jibo_Kids")
        records = adapter.scan()
        adapter.write_manifest(records)
    """

    def __init__(self, dataset_root: str | Path, compute_hashes: bool = True):
        """
        Args:
            dataset_root: Path to the Jibo_Kids directory (containing data/).
            compute_hashes: If True, compute SHA-256 for each WAV.
        """
        self.root = Path(dataset_root).resolve()
        self.data_dir = self.root / "data"
        self.compute_hashes = compute_hashes
        self._manifest_path = self.root / MANIFEST_FILENAME

    @property
    def manifest_path(self) -> Path:
        return self._manifest_path

    def is_available(self) -> bool:
        """Check whether the dataset directory structure exists."""
        return self.data_dir.is_dir()

    def scan(self) -> list[JiboRecord]:
        """Scan the dataset and return all discovered records.

        Does not modify or delete any files.
        """
        if not self.is_available():
            logger.warning("JIBO dataset not found at %s", self.data_dir)
            return []

        records: list[JiboRecord] = []

        for category in TASK_CATEGORIES:
            cat_dir = self.data_dir / category
            if not cat_dir.is_dir():
                logger.warning("Expected category dir missing: %s", cat_dir)
                continue

            wav_files = sorted(cat_dir.rglob("*.wav"))
            txt_files = {p.stem: p for p in cat_dir.rglob("*.txt")}

            for wav_path in wav_files:
                rel_audio = wav_path.relative_to(self.root).as_posix()
                record_id = make_record_id(category, rel_audio)

                # Parse child code from filename
                meta = parse_child_code(wav_path.stem)

                # Look for matching transcript
                transcript_path = txt_files.get(wav_path.stem)
                rel_transcript = None
                transcript_text = None
                issues: list[str] = []

                if transcript_path:
                    rel_transcript = transcript_path.relative_to(
                        self.root
                    ).as_posix()
                    try:
                        transcript_text = transcript_path.read_text(
                            encoding="utf-8"
                        ).strip()
                    except (OSError, UnicodeDecodeError) as exc:
                        issues.append(f"transcript_read_error: {exc}")
                else:
                    issues.append("missing_transcript")

                # Read WAV info
                wav_info = read_wav_info(wav_path)
                if wav_info is None:
                    issues.append("corrupt_or_unreadable_wav")

                # Compute hash
                file_hash = None
                if self.compute_hashes:
                    try:
                        file_hash = sha256_file(wav_path)
                    except OSError as exc:
                        issues.append(f"hash_error: {exc}")

                record = JiboRecord(
                    record_id=record_id,
                    task_category=category,
                    audio_path=rel_audio,
                    transcript_path=rel_transcript,
                    transcript_text=transcript_text,
                    child_code=meta["child_code"],
                    study_year=meta["study_year"],
                    school_year=meta["school_year"],
                    child_id=meta["child_id"],
                    gender_hint=meta["gender_hint"],
                    wav_info=wav_info,
                    file_hash=file_hash,
                    issues=issues,
                )
                records.append(record)

            # Check for orphan transcripts (TXT without matching WAV)
            wav_stems = {p.stem for p in wav_files}
            for txt_stem, txt_path in txt_files.items():
                if txt_stem not in wav_stems:
                    logger.info(
                        "Orphan transcript (no WAV): %s", txt_path.name
                    )

        logger.info("Scanned %d records from JIBO dataset", len(records))
        return records

    def write_manifest(self, records: list[JiboRecord]) -> Path:
        """Write records to a versioned JSONL manifest file.

        Line 1 is always the metadata header.
        Subsequent lines are individual records.

        Returns the path to the written manifest.
        """
        # Build category summary
        cat_counts: dict[str, int] = {}
        total_bytes = 0
        total_duration = 0.0
        issues_count = 0

        for r in records:
            cat_counts[r.task_category] = cat_counts.get(r.task_category, 0) + 1
            if r.wav_info:
                total_bytes += r.wav_info.file_size
                total_duration += r.wav_info.duration_s
            if r.issues:
                issues_count += 1

        meta = ManifestMeta(
            version=MANIFEST_VERSION,
            created_at=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            dataset_root=self.root.as_posix(),
            total_records=len(records),
            total_audio_bytes=total_bytes,
            total_duration_s=round(total_duration, 2),
            categories=cat_counts,
            issues_count=issues_count,
        )

        with open(self._manifest_path, "w", encoding="utf-8") as f:
            # Header line
            header = {"__manifest_meta__": asdict(meta)}
            f.write(json.dumps(header, ensure_ascii=False) + "\n")

            # Record lines
            for r in records:
                row = asdict(r)
                # Serialize WAVInfo inline
                if row.get("wav_info") and isinstance(row["wav_info"], dict):
                    pass  # already a dict from asdict
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

        logger.info("Manifest written to %s (%d records)", self._manifest_path, len(records))
        return self._manifest_path

    def load_manifest(self) -> tuple[Optional[ManifestMeta], list[JiboRecord]]:
        """Load an existing manifest.  Returns (meta, records)."""
        if not self._manifest_path.exists():
            return None, []

        meta = None
        records: list[JiboRecord] = []

        with open(self._manifest_path, "r", encoding="utf-8") as f:
            for i, line in enumerate(f):
                line = line.strip()
                if not line:
                    continue
                data = json.loads(line)

                if i == 0 and "__manifest_meta__" in data:
                    md = data["__manifest_meta__"]
                    meta = ManifestMeta(**{
                        k: v for k, v in md.items()
                        if k in ManifestMeta.__dataclass_fields__
                    })
                    continue

                # Reconstruct WAVInfo
                wi_data = data.pop("wav_info", None)
                wav_info = None
                if wi_data and isinstance(wi_data, dict):
                    wav_info = WAVInfo(**{
                        k: v for k, v in wi_data.items()
                        if k in WAVInfo.__dataclass_fields__
                    })

                record = JiboRecord(
                    wav_info=wav_info,
                    **{k: v for k, v in data.items()
                       if k in JiboRecord.__dataclass_fields__ and k != "wav_info"}
                )
                records.append(record)

        return meta, records

    def incremental_scan(self) -> list[JiboRecord]:
        """Scan only new files not present in the existing manifest.

        If no manifest exists, performs a full scan.
        """
        existing_meta, existing_records = self.load_manifest()
        if not existing_records:
            return self.scan()

        known_paths = {r.audio_path for r in existing_records}
        full_scan = self.scan()

        new_records = [r for r in full_scan if r.audio_path not in known_paths]
        if new_records:
            logger.info(
                "Incremental scan found %d new records", len(new_records)
            )
            all_records = existing_records + new_records
            self.write_manifest(all_records)
            return all_records

        logger.info("Incremental scan: no new records found")
        return existing_records


# ---------------------------------------------------------------------------
# Inventory report
# ---------------------------------------------------------------------------

def generate_inventory_report(records: list[JiboRecord]) -> dict:
    """Generate a structured inventory report from scanned records.

    Returns a dict suitable for JSON serialization.
    """
    report: dict = {
        "total_recordings": len(records),
        "total_size_bytes": 0,
        "total_duration_s": 0.0,
        "categories": {},
        "sample_rates": set(),
        "channels": set(),
        "bits_per_sample": set(),
        "audio_formats": set(),
        "records_with_transcripts": 0,
        "records_missing_transcripts": 0,
        "records_with_issues": 0,
        "duplicate_hashes": [],
        "issues_detail": [],
        "unique_children": set(),
        "school_year_distribution": {},
        "gender_distribution": {},
    }

    hash_map: dict[str, list[str]] = {}

    for r in records:
        # Category counts
        cat = r.task_category
        if cat not in report["categories"]:
            report["categories"][cat] = {"count": 0, "size_bytes": 0, "duration_s": 0.0}
        report["categories"][cat]["count"] += 1

        # WAV info
        if r.wav_info:
            report["total_size_bytes"] += r.wav_info.file_size
            report["total_duration_s"] += r.wav_info.duration_s
            report["categories"][cat]["size_bytes"] += r.wav_info.file_size
            report["categories"][cat]["duration_s"] += r.wav_info.duration_s
            report["sample_rates"].add(r.wav_info.sample_rate)
            report["channels"].add(r.wav_info.channels)
            report["bits_per_sample"].add(r.wav_info.bits_per_sample)
            report["audio_formats"].add(r.wav_info.audio_format)

        # Transcripts
        if r.transcript_path:
            report["records_with_transcripts"] += 1
        else:
            report["records_missing_transcripts"] += 1

        # Issues
        if r.issues:
            report["records_with_issues"] += 1
            report["issues_detail"].append({
                "record_id": r.record_id,
                "audio_path": r.audio_path,
                "issues": r.issues,
            })

        # Hashes for duplicate detection
        if r.file_hash:
            hash_map.setdefault(r.file_hash, []).append(r.audio_path)

        # Child demographics
        if r.child_code:
            report["unique_children"].add(r.child_code)
        if r.school_year:
            sy = r.school_year
            report["school_year_distribution"][sy] = (
                report["school_year_distribution"].get(sy, 0) + 1
            )
        if r.gender_hint:
            g = r.gender_hint
            report["gender_distribution"][g] = (
                report["gender_distribution"].get(g, 0) + 1
            )

    # Find duplicates
    for h, paths in hash_map.items():
        if len(paths) > 1:
            report["duplicate_hashes"].append({"hash": h, "files": paths})

    # Convert sets to sorted lists for JSON serialization
    report["sample_rates"] = sorted(report["sample_rates"])
    report["channels"] = sorted(report["channels"])
    report["bits_per_sample"] = sorted(report["bits_per_sample"])
    report["audio_formats"] = sorted(report["audio_formats"])
    report["unique_children"] = len(report["unique_children"])
    report["total_duration_s"] = round(report["total_duration_s"], 2)

    return report
