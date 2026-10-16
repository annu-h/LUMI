"""
LUMI — Voice Activity Detection (VAD)

Defines the VAD ABC, a MockVAD, and a SileroVAD adapter.

Responsibilities:
  - Identify speech regions within a captured audio buffer.
  - Trim leading/trailing silence while preserving speech at utterance edges.
  - Reject audio that contains no speech.
  - Make all settings configurable.

Architecture note: VAD is applied AFTER a wake-word event triggers utterance
capture.  VAD does NOT gate the wake-word detector.
"""

import abc
import logging
from dataclasses import dataclass
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class VADResult:
    """Outcome of a VAD pass over an audio buffer."""
    contains_speech: bool
    speech_audio: np.ndarray  # 1-D int16 array (trimmed or full)
    speech_ratio: float       # fraction of frames classified as speech
    frames_total: int
    frames_speech: int


class VAD(abc.ABC):
    """Abstract voice-activity detector."""

    SAMPLE_RATE: int = 16000

    @abc.abstractmethod
    def process(self, audio: np.ndarray) -> VADResult:
        """Analyse an audio buffer and return a VADResult.

        Args:
            audio: 1-D int16 numpy array at 16 kHz mono.

        Returns:
            VADResult describing speech content and trimmed audio.
        """
        ...


class MockVAD(VAD):
    """Deterministic mock VAD for tests.

    Returns a fixed contains_speech value and speech_ratio based on
    the RMS amplitude of the input (simulating energy-based detection).
    """

    def __init__(self, force_speech: Optional[bool] = None,
                 energy_threshold: float = 100.0) -> None:
        """
        Args:
            force_speech: If not None, always return this value.
            energy_threshold: RMS threshold below which audio is labelled silent.
        """
        self._force_speech = force_speech
        self._energy_threshold = energy_threshold

    def process(self, audio: np.ndarray) -> VADResult:
        if len(audio) == 0:
            return VADResult(
                contains_speech=False,
                speech_audio=np.array([], dtype=np.int16),
                speech_ratio=0.0,
                frames_total=0,
                frames_speech=0,
            )

        audio = np.asarray(audio, dtype=np.int16)
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))

        if self._force_speech is not None:
            speech = self._force_speech
        else:
            speech = rms >= self._energy_threshold

        return VADResult(
            contains_speech=speech,
            speech_audio=audio if speech else np.array([], dtype=np.int16),
            speech_ratio=1.0 if speech else 0.0,
            frames_total=len(audio),
            frames_speech=len(audio) if speech else 0,
        )


class SileroVAD(VAD):
    """Adapter for the Silero VAD model.

    Loads the model from torchhub on first use (requires internet once).
    Subsequent uses are offline.

    Settings:
        threshold: Probability threshold [0.0, 1.0] to classify a chunk
                   as speech (default 0.5).
        min_silence_duration_ms: Trailing silence before utterance is
                                 considered ended (default 700).
    """

    # Silero VAD expects 512-sample chunks at 16 kHz (32 ms)
    CHUNK_SAMPLES: int = 512

    def __init__(self, threshold: float = 0.5,
                 min_silence_duration_ms: int = 700,
                 sample_rate: int = 16000) -> None:
        self._threshold = threshold
        self._min_silence_ms = min_silence_duration_ms
        self._sample_rate = sample_rate
        self._model = None
        self._utils = None

    def _load(self) -> None:
        """Lazy-load the Silero VAD model via torch.hub."""
        if self._model is not None:
            return
        try:
            import torch  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "torch is required for SileroVAD. "
                "Install silero-vad which bundles torch, or pip install torch."
            ) from exc

        try:
            import torch
            self._model, self._utils = torch.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                force_reload=False,
                onnx=False,
            )
            self._model.eval()
            logger.info("SileroVAD model loaded.")
        except Exception as exc:
            raise RuntimeError(f"Failed to load Silero VAD model: {exc}") from exc

    def process(self, audio: np.ndarray) -> VADResult:
        """Run Silero VAD over a complete audio buffer.

        Splits the buffer into 512-sample chunks, scores each chunk,
        then reassembles the speech regions.
        """
        self._load()

        import torch

        audio = np.asarray(audio, dtype=np.int16)

        if len(audio) == 0:
            return VADResult(
                contains_speech=False,
                speech_audio=np.array([], dtype=np.int16),
                speech_ratio=0.0,
                frames_total=0,
                frames_speech=0,
            )

        # Silero expects float32 in [-1.0, 1.0]
        audio_f32 = audio.astype(np.float32) / 32768.0
        num_chunks = len(audio_f32) // self.CHUNK_SAMPLES
        speech_mask = np.zeros(len(audio_f32), dtype=bool)

        self._model.reset_states()

        for i in range(num_chunks):
            start = i * self.CHUNK_SAMPLES
            end = start + self.CHUNK_SAMPLES
            chunk_tensor = torch.from_numpy(audio_f32[start:end])
            score = float(self._model(chunk_tensor, self._sample_rate).item())
            if score >= self._threshold:
                speech_mask[start:end] = True

        # Apply silence-padding: extend each speech region by silence margin
        silence_samples = int(
            self._min_silence_ms * self._sample_rate / 1000
        )
        expanded = _expand_mask(speech_mask, pad_samples=silence_samples)

        speech_indices = np.where(expanded)[0]
        if len(speech_indices) == 0:
            return VADResult(
                contains_speech=False,
                speech_audio=np.array([], dtype=np.int16),
                speech_ratio=0.0,
                frames_total=len(audio),
                frames_speech=0,
            )

        # Trim to the outermost speech boundary
        first, last = speech_indices[0], speech_indices[-1] + 1
        trimmed = audio[first:last]
        frames_speech = int(speech_mask.sum())

        return VADResult(
            contains_speech=True,
            speech_audio=trimmed,
            speech_ratio=frames_speech / len(audio),
            frames_total=len(audio),
            frames_speech=frames_speech,
        )


def _expand_mask(mask: np.ndarray, pad_samples: int) -> np.ndarray:
    """Dilate a boolean mask by `pad_samples` on both sides.

    This prevents cutting off slowly spoken words at utterance edges.
    Optimized to expand contiguous True regions rather than per-sample.
    """
    if pad_samples <= 0 or not mask.any():
        return mask.copy()

    expanded = np.zeros_like(mask, dtype=bool)
    diff = np.diff(mask.astype(np.int8))
    starts = np.where(diff == 1)[0] + 1
    ends = np.where(diff == -1)[0] + 1

    if mask[0]:
        starts = np.r_[0, starts]
    if mask[-1]:
        ends = np.r_[ends, len(mask)]

    for s, e in zip(starts, ends):
        lo = max(0, s - pad_samples)
        hi = min(len(mask), e + pad_samples)
        expanded[lo:hi] = True

    return expanded


def make_vad(config) -> VAD:
    """Factory: return the best available VAD for the given config."""
    try:
        vad = SileroVAD(
            threshold=config.vad.threshold,
            min_silence_duration_ms=config.vad.min_silence_duration_ms,
            sample_rate=config.vad.sample_rate,
        )
        # Pre-load to surface import errors early.
        vad._load()
        return vad
    except RuntimeError as exc:
        logger.warning(
            "SileroVAD unavailable (%s). Falling back to MockVAD.", exc
        )
        return MockVAD()
