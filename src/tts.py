"""
LUMI — Text-to-Speech Interface

Defines the TTS ABC, a MockTTS, and a PiperTTS adapter.

Responsibilities:
  - Generate English speech locally (no cloud APIs).
  - Cache synthesized audio to avoid re-generating unchanged phrases.
  - Provide a mockable playback interface.
  - Support offline operation once models are installed.
"""

import abc
import hashlib
import logging
import struct
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TTSResult:
    """Output from a TTS synthesis call."""
    audio: np.ndarray          # 1-D int16 PCM samples
    sample_rate: int
    duration_s: float
    synthesis_time_s: float
    from_cache: bool
    backend: str
    error: Optional[str] = None


class TTS(abc.ABC):
    """Abstract TTS interface."""

    @abc.abstractmethod
    def synthesize(self, text: str) -> TTSResult:
        """Synthesize text to speech.

        Args:
            text: The phrase to synthesize.

        Returns:
            TTSResult with audio samples.
        """
        ...


class MockTTS(TTS):
    """Mock TTS — returns short silence or a sine-wave tone.

    Used in tests without requiring a voice model.
    """

    SAMPLE_RATE = 22050

    def __init__(self, duration_s: float = 0.5, use_tone: bool = False) -> None:
        self._duration_s = duration_s
        self._use_tone = use_tone

    def synthesize(self, text: str) -> TTSResult:
        t0 = time.monotonic()
        n = int(self.SAMPLE_RATE * self._duration_s)

        if self._use_tone:
            t = np.linspace(0.0, self._duration_s, n, endpoint=False)
            audio = (8000 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
        else:
            audio = np.zeros(n, dtype=np.int16)

        return TTSResult(
            audio=audio,
            sample_rate=self.SAMPLE_RATE,
            duration_s=self._duration_s,
            synthesis_time_s=time.monotonic() - t0,
            from_cache=False,
            backend="mock",
        )


class PiperTTS(TTS):
    """Adapter for the Piper TTS library.

    Requires:
        - piper-tts Python package
        - Voice model (.onnx) and config (.onnx.json) at the configured paths

    Caches synthesized audio as WAV files under output_dir.  If a cached
    file exists for the given text hash, it is read directly.
    """

    SAMPLE_RATE = 22050  # Piper Lessac medium voice default

    def __init__(self, model_path: str, config_path: str,
                 output_dir: str, length_scale: float = 1.1) -> None:
        self._model_path = Path(model_path)
        self._config_path = Path(config_path)
        self._output_dir = Path(output_dir)
        self._length_scale = length_scale
        self._voice = None
        self._output_dir.mkdir(parents=True, exist_ok=True)

    def _load(self) -> None:
        """Lazy-load the Piper voice model."""
        if self._voice is not None:
            return

        if not self._model_path.exists():
            raise RuntimeError(
                f"Piper voice model not found: {self._model_path}. "
                "Download it from https://huggingface.co/rhasspy/piper-voices."
            )
        if not self._config_path.exists():
            raise RuntimeError(
                f"Piper voice config not found: {self._config_path}."
            )

        try:
            from piper.voice import PiperVoice
        except ImportError as exc:
            raise RuntimeError(
                "piper-tts is not installed. Run: pip install piper-tts"
            ) from exc

        try:
            self._voice = PiperVoice.load(
                str(self._model_path),
                config_path=str(self._config_path),
                use_cuda=False,
            )
            logger.info("Piper voice loaded from %s", self._model_path)
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load Piper voice: {exc}"
            ) from exc

    def _cache_path(self, text: str) -> Path:
        h = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
        return self._output_dir / f"{h}.wav"

    def synthesize(self, text: str) -> TTSResult:
        t0 = time.monotonic()
        cache_path = self._cache_path(text)

        # Return cached WAV if it exists
        if cache_path.exists():
            try:
                audio = _read_wav_as_int16(cache_path)
                duration_s = len(audio) / self.SAMPLE_RATE
                return TTSResult(
                    audio=audio,
                    sample_rate=self.SAMPLE_RATE,
                    duration_s=duration_s,
                    synthesis_time_s=time.monotonic() - t0,
                    from_cache=True,
                    backend="piper",
                )
            except Exception as exc:
                logger.warning("Cache read failed (%s); re-synthesizing.", exc)

        # Synthesize
        try:
            self._load()
        except RuntimeError as exc:
            return TTSResult(
                audio=np.array([], dtype=np.int16),
                sample_rate=self.SAMPLE_RATE,
                duration_s=0.0,
                synthesis_time_s=time.monotonic() - t0,
                from_cache=False,
                backend="piper",
                error=str(exc),
            )

        try:
            # Collect raw audio bytes from Piper
            audio_bytes = b""
            synthesize_args = {"length_scale": self._length_scale}
            for audio_chunk in self._voice.synthesize_stream_raw(
                text, **synthesize_args
            ):
                audio_bytes += audio_chunk

            audio = np.frombuffer(audio_bytes, dtype=np.int16)

            # Write to cache
            _write_wav(cache_path, audio, self.SAMPLE_RATE)
            logger.debug("Piper: synthesized %d samples for '%s'", len(audio), text)

        except Exception as exc:
            logger.exception("Piper synthesis failed: %s", exc)
            return TTSResult(
                audio=np.array([], dtype=np.int16),
                sample_rate=self.SAMPLE_RATE,
                duration_s=0.0,
                synthesis_time_s=time.monotonic() - t0,
                from_cache=False,
                backend="piper",
                error=str(exc),
            )

        duration_s = len(audio) / self.SAMPLE_RATE
        return TTSResult(
            audio=audio,
            sample_rate=self.SAMPLE_RATE,
            duration_s=duration_s,
            synthesis_time_s=time.monotonic() - t0,
            from_cache=False,
            backend="piper",
        )


# ---------------------------------------------------------------------------
# Minimal WAV helpers (stdlib + numpy, no soundfile dependency)
# ---------------------------------------------------------------------------

def _write_wav(path: Path, audio: np.ndarray, sample_rate: int) -> None:
    """Write a mono 16-bit PCM WAV file."""
    num_samples = len(audio)
    num_channels = 1
    bits_per_sample = 16
    byte_rate = sample_rate * num_channels * bits_per_sample // 8
    block_align = num_channels * bits_per_sample // 8
    data_size = num_samples * block_align

    with open(path, "wb") as f:
        # RIFF header
        f.write(b"RIFF")
        f.write(struct.pack("<I", 36 + data_size))
        f.write(b"WAVE")
        # fmt chunk
        f.write(b"fmt ")
        f.write(struct.pack("<I", 16))
        f.write(struct.pack(
            "<HHIIHH",
            1,              # PCM
            num_channels,
            sample_rate,
            byte_rate,
            block_align,
            bits_per_sample,
        ))
        # data chunk
        f.write(b"data")
        f.write(struct.pack("<I", data_size))
        f.write(audio.tobytes())


def _read_wav_as_int16(path: Path) -> np.ndarray:
    """Read a mono 16-bit PCM WAV file to an int16 array."""
    from src.audio_source import _load_wav_as_int16
    return _load_wav_as_int16(path)


def make_tts(config) -> TTS:
    """Factory: return the configured TTS backend."""
    from pathlib import Path as P
    from src.config import PROJECT_ROOT

    model_path = PROJECT_ROOT / config.tts.model_path
    config_path = PROJECT_ROOT / config.tts.config_path
    output_dir = PROJECT_ROOT / config.tts.output_dir

    if not model_path.exists() or not config_path.exists():
        logger.warning(
            "Piper voice model or config not found — using MockTTS. "
            "TTS will not produce real speech."
        )
        return MockTTS()

    return PiperTTS(
        model_path=str(model_path),
        config_path=str(config_path),
        output_dir=str(output_dir),
        length_scale=config.tts.length_scale,
    )
