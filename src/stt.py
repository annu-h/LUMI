"""
LUMI — Speech-to-Text Interface

Defines the STT ABC, a MockSTT, and a FasterWhisperSTT adapter.

Responsibilities:
  - Transcribe audio locally (no cloud APIs).
  - Reuse a loaded model across utterances.
  - Handle empty transcripts, model failures, and missing files safely.
  - Keep model loading and inference separate.
"""

import abc
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TranscriptionResult:
    """Structured output from a transcription call."""
    text: str                    # Normalized, stripped transcript
    language: Optional[str]      # Detected or forced language code
    duration_s: float            # Length of the audio transcribed
    inference_time_s: float      # Wall-clock time for the inference call
    segments: list = field(default_factory=list)  # Raw segment dicts
    backend: str = "unknown"     # "faster-whisper" | "mock"
    error: Optional[str] = None  # Set if transcription partially failed


class STT(abc.ABC):
    """Abstract speech-to-text interface."""

    @abc.abstractmethod
    def transcribe(self, audio: np.ndarray,
                   sample_rate: int = 16000) -> TranscriptionResult:
        """Transcribe a 1-D int16 numpy audio array.

        Args:
            audio: Mono 16-bit PCM samples.
            sample_rate: Sample rate of the audio (must match model expectation).

        Returns:
            TranscriptionResult.
        """
        ...


class MockSTT(STT):
    """Mock STT for tests.

    Returns a configurable fixed transcript without loading any model.
    """

    def __init__(self, transcript: str = "tell me a story",
                 raise_on_empty: bool = False) -> None:
        self._transcript = transcript
        self._raise_on_empty = raise_on_empty

    def transcribe(self, audio: np.ndarray,
                   sample_rate: int = 16000) -> TranscriptionResult:
        t0 = time.monotonic()
        duration_s = len(audio) / sample_rate

        if self._raise_on_empty and len(audio) == 0:
            return TranscriptionResult(
                text="",
                language="en",
                duration_s=0.0,
                inference_time_s=0.0,
                backend="mock",
                error="empty audio",
            )

        return TranscriptionResult(
            text=self._transcript if len(audio) > 0 else "",
            language="en",
            duration_s=duration_s,
            inference_time_s=time.monotonic() - t0,
            backend="mock",
        )


class FasterWhisperSTT(STT):
    """Adapter for the faster-whisper library.

    Model is loaded once in __init__ and reused for all calls.
    """

    def __init__(self, model: str = "base.en", device: str = "cpu",
                 compute_type: str = "int8", beam_size: int = 1,
                 language: str = "en") -> None:
        """
        Args:
            model: Model identifier ("base.en", "tiny.en", etc.)
            device: "cpu" or "cuda"
            compute_type: "int8", "float16", etc.
            beam_size: Whisper beam search width.
            language: ISO 639-1 language code, or None for auto-detect.
        """
        self._model_id = model
        self._device = device
        self._compute_type = compute_type
        self._beam_size = beam_size
        self._language: Optional[str] = language or None
        self._model = None

    def _load(self) -> None:
        """Load the Whisper model (called lazily on first transcription)."""
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
            self._model_id, self._device, self._compute_type,
        )
        t0 = time.monotonic()
        try:
            self._model = WhisperModel(
                self._model_id,
                device=self._device,
                compute_type=self._compute_type,
            )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load Whisper model '{self._model_id}': {exc}"
            ) from exc

        elapsed = time.monotonic() - t0
        logger.info("Whisper model loaded in %.2f s.", elapsed)

    def transcribe(self, audio: np.ndarray,
                   sample_rate: int = 16000) -> TranscriptionResult:
        """Transcribe mono 16-bit PCM audio."""
        self._load()

        audio = np.asarray(audio, dtype=np.int16)
        duration_s = len(audio) / sample_rate

        if len(audio) == 0:
            return TranscriptionResult(
                text="",
                language=self._language,
                duration_s=0.0,
                inference_time_s=0.0,
                backend="faster-whisper",
                error="empty audio",
            )

        # Faster-Whisper expects float32 [-1.0, 1.0]
        audio_f32 = audio.astype(np.float32) / 32768.0

        t0 = time.monotonic()
        try:
            segments_iter, info = self._model.transcribe(
                audio_f32,
                beam_size=self._beam_size,
                language=self._language,
                vad_filter=False,  # We apply our own VAD upstream.
            )
            segments = list(segments_iter)
        except Exception as exc:
            logger.exception("Whisper inference failed: %s", exc)
            return TranscriptionResult(
                text="",
                language=self._language,
                duration_s=duration_s,
                inference_time_s=time.monotonic() - t0,
                backend="faster-whisper",
                error=str(exc),
            )

        inference_time_s = time.monotonic() - t0
        text = " ".join(seg.text for seg in segments).strip()
        detected_lang = getattr(info, "language", self._language)

        logger.debug(
            "Whisper '%s': '%s' (%.2f s audio, %.2f s inference)",
            self._model_id, text, duration_s, inference_time_s,
        )

        return TranscriptionResult(
            text=text,
            language=detected_lang,
            duration_s=duration_s,
            inference_time_s=inference_time_s,
            segments=[{"text": s.text, "start": s.start, "end": s.end,
                        "avg_logprob": s.avg_logprob,
                        "no_speech_prob": s.no_speech_prob}
                       for s in segments],
            backend="faster-whisper",
        )


def make_stt(config) -> STT:
    """Factory: return the configured STT backend."""
    try:
        stt = FasterWhisperSTT(
            model=config.stt.model,
            device=config.stt.device,
            compute_type=config.stt.compute_type,
            beam_size=config.stt.beam_size,
            language=config.stt.language,
        )
        return stt
    except Exception as exc:
        logger.warning("FasterWhisperSTT unavailable (%s). Using MockSTT.", exc)
        return MockSTT()
