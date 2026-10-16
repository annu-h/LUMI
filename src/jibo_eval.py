"""
LUMI — Faster-Whisper Evaluation on JIBO Kids Corpus

Repeatable evaluation script that:
  - Selects valid audio/transcript pairs from the JIBO manifest.
  - Runs a local Faster-Whisper model (base.en or tiny.en).
  - Computes word error rate (WER) against reference transcripts.
  - Saves machine-readable results.
  - Supports comparing tiny.en vs base.en on the same evaluation subset.

Privacy: Audio and transcripts are processed locally only.
No cloud APIs are used.  Speaker identifiers are not logged.

Normalization rules are documented below and preserved alongside results.
"""

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

NORMALIZATION_RULES = """
Normalization rules applied to both hypothesis and reference text:
1. Convert to lowercase.
2. Remove bracketed annotations (e.g., [unintelligible], [noise]).
3. Remove punctuation except apostrophes in contractions.
4. Normalize digit words to digits: "one" → "1", etc.
5. Normalize letter name spellings: "bee" → "b", etc.
6. Collapse whitespace and strip.

Unintelligible markers like [unintelligible] are removed from both
reference and hypothesis.  Samples where the ENTIRE reference is
unintelligible are SKIPPED (not evaluated).

These rules are saved alongside results for reproducibility.
"""

# Letter name → single letter (lowercase)
LETTER_NORM = {
    "ay": "a", "bee": "b", "see": "c", "dee": "d", "ee": "e",
    "eff": "f", "gee": "g", "aitch": "h", "eye": "i", "jay": "j",
    "kay": "k", "ell": "l", "em": "m", "en": "n", "oh": "o",
    "pee": "p", "cue": "q", "are": "r", "ess": "s", "tee": "t",
    "you": "u", "vee": "v", "double-u": "w", "ex": "x",
    "why": "y", "wye": "y", "zee": "z", "zed": "z",
}

DIGIT_NORM = {
    "zero": "0", "one": "1", "two": "2", "three": "3",
    "four": "4", "five": "5", "six": "6", "seven": "7",
    "eight": "8", "nine": "9", "ten": "10",
}


def normalize_for_wer(text: str) -> str:
    """Normalize text for WER computation.

    Applies the documented normalization rules consistently to both
    hypothesis and reference.
    """
    if not text:
        return ""

    text = text.lower()

    # Remove bracketed annotations
    text = re.sub(r"\[.*?\]", "", text)

    # Remove punctuation except apostrophes
    text = re.sub(r"[^\w\s']", " ", text)

    # Normalize letter names and digit names
    tokens = text.split()
    normalized_tokens = []
    for tok in tokens:
        if tok in LETTER_NORM:
            normalized_tokens.append(LETTER_NORM[tok])
        elif tok in DIGIT_NORM:
            normalized_tokens.append(DIGIT_NORM[tok])
        else:
            normalized_tokens.append(tok)

    # Collapse whitespace
    return " ".join(normalized_tokens).strip()


def is_unintelligible(text: str) -> bool:
    """Check if the entire reference consists only of unintelligible markers."""
    if not text:
        return True
    cleaned = re.sub(r"\[.*?\]", "", text).strip()
    return len(cleaned) == 0


# ---------------------------------------------------------------------------
# WER calculation
# ---------------------------------------------------------------------------

def compute_wer(reference: str, hypothesis: str) -> tuple[float, dict]:
    """Compute Word Error Rate using the standard edit-distance algorithm.

    Returns:
        (wer, detail_dict)
        wer: float in [0.0, ...] (can exceed 1.0 if insertions dominate)
        detail_dict: {"substitutions": int, "insertions": int,
                      "deletions": int, "ref_words": int, "errors": int}

    If reference is empty, returns WER of 0.0 if hypothesis is also empty,
    otherwise returns float('inf').
    """
    ref_words = reference.split()
    hyp_words = hypothesis.split()

    n = len(ref_words)
    m = len(hyp_words)

    if n == 0:
        if m == 0:
            return 0.0, {"substitutions": 0, "insertions": 0,
                         "deletions": 0, "ref_words": 0, "errors": 0}
        return float("inf"), {"substitutions": 0, "insertions": m,
                              "deletions": 0, "ref_words": 0, "errors": m}

    # Dynamic programming table
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        d[i][0] = i
    for j in range(m + 1):
        d[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_words[i - 1] == hyp_words[j - 1]:
                d[i][j] = d[i - 1][j - 1]
            else:
                sub = d[i - 1][j - 1] + 1
                ins = d[i][j - 1] + 1
                dele = d[i - 1][j] + 1
                d[i][j] = min(sub, ins, dele)

    # Backtrace to count S, I, D
    i, j = n, m
    subs = ins = dels = 0
    while i > 0 or j > 0:
        if i > 0 and j > 0 and ref_words[i - 1] == hyp_words[j - 1]:
            i -= 1
            j -= 1
        elif i > 0 and j > 0 and d[i][j] == d[i - 1][j - 1] + 1:
            subs += 1
            i -= 1
            j -= 1
        elif j > 0 and d[i][j] == d[i][j - 1] + 1:
            ins += 1
            j -= 1
        elif i > 0 and d[i][j] == d[i - 1][j] + 1:
            dels += 1
            i -= 1
        else:
            # Fallback (shouldn't happen with correct DP)
            break

    errors = subs + ins + dels
    wer = errors / n

    return wer, {
        "substitutions": subs,
        "insertions": ins,
        "deletions": dels,
        "ref_words": n,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EvalSample:
    """One evaluation sample result."""
    record_id: str
    audio_path: str
    reference_raw: str
    reference_normalized: str
    hypothesis_raw: str
    hypothesis_normalized: str
    wer: float
    wer_detail: dict = field(default_factory=dict)
    inference_time_s: float = 0.0
    audio_duration_s: float = 0.0
    status: str = "ok"  # "ok" | "skipped" | "error"
    error_message: Optional[str] = None


@dataclass
class EvalReport:
    """Aggregated evaluation results."""
    model_name: str
    device: str
    compute_type: str
    beam_size: int
    total_samples: int = 0
    evaluated: int = 0
    skipped: int = 0
    failed: int = 0
    mean_wer: float = 0.0
    median_wer: float = 0.0
    total_ref_words: int = 0
    total_errors: int = 0
    overall_wer: float = 0.0  # corpus-level WER
    total_audio_duration_s: float = 0.0
    total_inference_time_s: float = 0.0
    rtf: float = 0.0  # real-time factor
    samples: list[EvalSample] = field(default_factory=list)
    normalization_rules: str = NORMALIZATION_RULES
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Evaluator
# ---------------------------------------------------------------------------

class FasterWhisperEvaluator:
    """Evaluates Faster-Whisper against JIBO Kids transcripts."""

    def __init__(
        self,
        dataset_root: str | Path,
        model_name: str = "base.en",
        device: str = "cpu",
        compute_type: str = "int8",
        beam_size: int = 1,
        language: str = "en",
        max_samples: Optional[int] = None,
    ):
        self.dataset_root = Path(dataset_root).resolve()
        self.model_name = model_name
        self.device = device
        self.compute_type = compute_type
        self.beam_size = beam_size
        self.language = language
        self.max_samples = max_samples
        self._model = None

    def _load_model(self):
        """Lazy-load the Faster-Whisper model."""
        if self._model is not None:
            return

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise RuntimeError(
                "faster-whisper is not installed. "
                "Run: pip install faster-whisper"
            ) from exc

        logger.info(
            "Loading Whisper model '%s' on %s (%s)…",
            self.model_name, self.device, self.compute_type,
        )
        self._model = WhisperModel(
            self.model_name,
            device=self.device,
            compute_type=self.compute_type,
        )

    def _transcribe_file(self, wav_path: Path) -> tuple[str, float, float]:
        """Transcribe a single WAV file.

        Returns (text, inference_time_s, audio_duration_s).
        """
        import soundfile as sf

        audio, sr = sf.read(wav_path, dtype="float32")
        if len(audio.shape) > 1:
            audio = audio.mean(axis=1)  # mono mix
        audio_duration = len(audio) / sr

        # Resample to 16 kHz if needed
        if sr != 16000:
            # Simple linear interpolation (good enough for eval)
            ratio = 16000 / sr
            new_len = int(len(audio) * ratio)
            indices = np.linspace(0, len(audio) - 1, new_len)
            audio = np.interp(indices, np.arange(len(audio)), audio)

        t0 = time.monotonic()
        segments_iter, info = self._model.transcribe(
            audio,
            beam_size=self.beam_size,
            language=self.language,
            vad_filter=False,
        )
        segments = list(segments_iter)
        inference_time = time.monotonic() - t0

        text = " ".join(seg.text for seg in segments).strip()
        return text, inference_time, audio_duration

    def evaluate(self, records) -> EvalReport:
        """Run evaluation on a list of JiboRecords.

        Records without transcripts or with fully unintelligible
        transcripts are skipped.
        """
        self._load_model()

        report = EvalReport(
            model_name=self.model_name,
            device=self.device,
            compute_type=self.compute_type,
            beam_size=self.beam_size,
            timestamp=time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        )

        # Filter to valid evaluation pairs
        eval_records = []
        for r in records:
            if not r.transcript_text:
                report.skipped += 1
                continue
            if is_unintelligible(r.transcript_text):
                report.skipped += 1
                continue
            wav_path = self.dataset_root / r.audio_path
            if not wav_path.exists():
                report.skipped += 1
                continue
            eval_records.append(r)

        if self.max_samples and len(eval_records) > self.max_samples:
            eval_records = eval_records[:self.max_samples]

        report.total_samples = len(records)

        for r in eval_records:
            wav_path = self.dataset_root / r.audio_path

            ref_normalized = normalize_for_wer(r.transcript_text)
            if not ref_normalized:
                report.skipped += 1
                continue

            try:
                hyp_raw, inf_time, audio_dur = self._transcribe_file(wav_path)
                hyp_normalized = normalize_for_wer(hyp_raw)

                wer, wer_detail = compute_wer(ref_normalized, hyp_normalized)

                sample = EvalSample(
                    record_id=r.record_id,
                    audio_path=r.audio_path,
                    reference_raw=r.transcript_text,
                    reference_normalized=ref_normalized,
                    hypothesis_raw=hyp_raw,
                    hypothesis_normalized=hyp_normalized,
                    wer=round(wer, 4),
                    wer_detail=wer_detail,
                    inference_time_s=round(inf_time, 4),
                    audio_duration_s=round(audio_dur, 4),
                    status="ok",
                )
                report.samples.append(sample)
                report.evaluated += 1
                report.total_ref_words += wer_detail["ref_words"]
                report.total_errors += wer_detail["errors"]
                report.total_audio_duration_s += audio_dur
                report.total_inference_time_s += inf_time

            except Exception as exc:
                sample = EvalSample(
                    record_id=r.record_id,
                    audio_path=r.audio_path,
                    reference_raw=r.transcript_text or "",
                    reference_normalized=ref_normalized,
                    hypothesis_raw="",
                    hypothesis_normalized="",
                    wer=float("inf"),
                    status="error",
                    error_message=str(exc),
                )
                report.samples.append(sample)
                report.failed += 1

        # Aggregate metrics
        ok_samples = [s for s in report.samples if s.status == "ok"]
        if ok_samples:
            wers = [s.wer for s in ok_samples if s.wer != float("inf")]
            if wers:
                report.mean_wer = round(sum(wers) / len(wers), 4)
                sorted_wers = sorted(wers)
                mid = len(sorted_wers) // 2
                if len(sorted_wers) % 2 == 0:
                    report.median_wer = round(
                        (sorted_wers[mid - 1] + sorted_wers[mid]) / 2, 4
                    )
                else:
                    report.median_wer = round(sorted_wers[mid], 4)

            if report.total_ref_words > 0:
                report.overall_wer = round(
                    report.total_errors / report.total_ref_words, 4
                )

            if report.total_audio_duration_s > 0:
                report.rtf = round(
                    report.total_inference_time_s / report.total_audio_duration_s,
                    4,
                )

        return report

    @staticmethod
    def save_report(report: EvalReport, output_path: str | Path) -> Path:
        """Save evaluation report as JSON."""
        path = Path(output_path)
        data = asdict(report)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        logger.info("Evaluation report saved to %s", path)
        return path


# ---------------------------------------------------------------------------
# CLI-compatible entry point
# ---------------------------------------------------------------------------

def run_evaluation(
    dataset_root: str,
    model_name: str = "base.en",
    output_path: Optional[str] = None,
    max_samples: Optional[int] = None,
) -> EvalReport:
    """Convenience function to run a full evaluation.

    Usage from command line:
        python -m src.jibo_eval --dataset-root datasets/Jibo_Kids --model base.en
    """
    from .jibo_adapter import JiboDatasetAdapter

    adapter = JiboDatasetAdapter(dataset_root, compute_hashes=False)

    # Try loading existing manifest first
    meta, records = adapter.load_manifest()
    if not records:
        records = adapter.scan()
        if records:
            adapter.write_manifest(records)

    if not records:
        raise FileNotFoundError(
            f"No JIBO records found at {dataset_root}. "
            "Ensure the dataset is extracted."
        )

    evaluator = FasterWhisperEvaluator(
        dataset_root=dataset_root,
        model_name=model_name,
        max_samples=max_samples,
    )

    report = evaluator.evaluate(records)

    if output_path is None:
        output_path = str(
            Path(dataset_root) / f"eval_results_{model_name.replace('.', '_')}.json"
        )

    FasterWhisperEvaluator.save_report(report, output_path)
    return report


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO)

    parser = argparse.ArgumentParser(
        description="Evaluate Faster-Whisper on JIBO Kids Corpus"
    )
    parser.add_argument(
        "--dataset-root", required=True,
        help="Path to the Jibo_Kids dataset directory",
    )
    parser.add_argument(
        "--model", default="base.en",
        choices=["base.en", "tiny.en"],
        help="Whisper model to evaluate (default: base.en)",
    )
    parser.add_argument(
        "--output", default=None,
        help="Output path for the JSON results report",
    )
    parser.add_argument(
        "--max-samples", type=int, default=None,
        help="Maximum number of samples to evaluate",
    )

    args = parser.parse_args()

    report = run_evaluation(
        dataset_root=args.dataset_root,
        model_name=args.model,
        output_path=args.output,
        max_samples=args.max_samples,
    )

    print(f"\n{'='*60}")
    print(f"Model: {report.model_name}")
    print(f"Evaluated: {report.evaluated}, Skipped: {report.skipped}, Failed: {report.failed}")
    print(f"Overall WER: {report.overall_wer:.2%}")
    print(f"Mean WER: {report.mean_wer:.2%}")
    print(f"Median WER: {report.median_wer:.2%}")
    print(f"RTF (real-time factor): {report.rtf:.3f}")
    print(f"{'='*60}")
