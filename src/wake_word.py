"""
LUMI — Wake-Word Detector Interface

Defines the WakeWordDetector ABC, a MockWakeWordDetector, and an
openWakeWord adapter (loaded lazily to avoid hard failing when the library
is not installed).

Architecture: wake-word detection runs on every frame.  VAD does NOT gate
the wake-word detector — the detector must see all audio frames.
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
class WakeWordEvent:
    """Emitted when the detector crosses the score threshold."""
    score: float
    model_name: str
    timestamp_s: float = field(default_factory=time.time)


class WakeWordDetector(abc.ABC):
    """Abstract wake-word detector."""

    @abc.abstractmethod
    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        """Process one audio chunk.

        Args:
            audio_chunk: 1-D int16 numpy array.

        Returns:
            WakeWordEvent if the threshold is crossed and cooldown has
            elapsed, else None.
        """
        ...

    @abc.abstractmethod
    def reset(self) -> None:
        """Reset internal state (e.g. after the utterance has been captured)."""
        ...


class MockWakeWordDetector(WakeWordDetector):
    """Deterministic mock for tests.

    Fires a WakeWordEvent at frame N (default 0), then obeys cooldown.
    """

    def __init__(self, score: float = 0.9, trigger_at_frame: int = 0,
                 cooldown_ms: int = 2000, threshold: float = 0.6) -> None:
        self._score = score
        self._trigger_at = trigger_at_frame
        self._cooldown_ms = cooldown_ms
        self._threshold = threshold
        self._frame_count = 0
        self._last_trigger_time: float = 0.0

    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        now = time.time()
        cooldown_s = self._cooldown_ms / 1000.0

        if (self._frame_count == self._trigger_at
                and self._score >= self._threshold
                and (now - self._last_trigger_time) >= cooldown_s):
            self._frame_count += 1
            self._last_trigger_time = now
            return WakeWordEvent(score=self._score, model_name="mock")

        self._frame_count += 1
        return None

    def reset(self) -> None:
        self._frame_count = 0
        self._last_trigger_time = 0.0


class _BelowThresholdDetector(WakeWordDetector):
    """Mock detector that never fires (score always below threshold)."""

    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        return None

    def reset(self) -> None:
        pass


class OpenWakeWordDetector(WakeWordDetector):
    """Adapter for the openWakeWord library.

    Loads the custom hey_lumi.onnx model if available; otherwise falls back
    to a pretrained hey_jarvis model if installed.  If neither model is
    useable, raises RuntimeError at construction time so the caller can
    substitute a mock.

    Frame requirements (openWakeWord default):
        - 16 000 Hz, mono, int16 or float32.
        - Audio is fed in 80-ms chunks (1 280 samples at 16 kHz).
    """

    CHUNK_SAMPLES: int = 1280  # 80 ms at 16 kHz

    def __init__(self, model_path: Optional[str], threshold: float,
                 cooldown_ms: int = 2000) -> None:
        try:
            import openwakeword as oww  # noqa: F401
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "openWakeWord is not installed. "
                "Run: pip install openwakeword"
            ) from exc

        self._threshold = threshold
        self._cooldown_ms = cooldown_ms
        self._last_trigger_time: float = 0.0

        resolved_path: Optional[str] = None
        if model_path:
            p = Path(model_path)
            if p.exists():
                resolved_path = str(p)
                logger.info("Wake-word: loaded custom model from %s", resolved_path)
            else:
                logger.warning(
                    "Wake-word custom model not found at %s; "
                    "trying fallback pretrained model.",
                    model_path,
                )

        try:
            if resolved_path:
                self._model = Model(wakeword_models=[resolved_path])
                self._model_name = Path(resolved_path).stem
            else:
                # Let openWakeWord pick a default pretrained model.
                self._model = Model()
                # Discover which model names were loaded.
                names = list(getattr(self._model, "models", {}).keys())
                self._model_name = names[0] if names else "unknown"
                logger.info(
                    "Wake-word: using pretrained model(s): %s", names
                )
        except Exception as exc:
            raise RuntimeError(
                f"Failed to load openWakeWord model: {exc}"
            ) from exc

    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        now = time.time()
        cooldown_s = self._cooldown_ms / 1000.0

        # openWakeWord expects float32 [-1.0, 1.0] or int16.
        # We pass int16 directly; the library converts internally.
        prediction = self._model.predict(audio_chunk)

        # prediction is a dict: {model_name: score}
        for model_name, score in prediction.items():
            if score >= self._threshold and (now - self._last_trigger_time) >= cooldown_s:
                self._last_trigger_time = now
                return WakeWordEvent(score=float(score), model_name=model_name)

        return None

    def reset(self) -> None:
        self._last_trigger_time = 0.0


def make_wake_word_detector(config) -> WakeWordDetector:
    """Factory: return the best available detector for the given config.

    Falls back to MockWakeWordDetector when openWakeWord is unavailable.
    """
    try:
        return OpenWakeWordDetector(
            model_path=str(config.wake_word.resolve_model_path()),
            threshold=config.wake_word.score_threshold,
            cooldown_ms=config.wake_word.cooldown_ms,
        )
    except RuntimeError as exc:
        logger.warning(
            "Real wake-word detector unavailable (%s). "
            "Falling back to mock (threshold=%.2f). "
            "Wake-word testing with real audio is NOT available.",
            exc,
            config.wake_word.score_threshold,
        )
        return MockWakeWordDetector(threshold=config.wake_word.score_threshold)
