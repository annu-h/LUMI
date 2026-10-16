"""
LUMI — Audio Playback Interface

Defines the AudioPlayer ABC and a MockAudioPlayer for tests.
A real sounddevice-backed player will be wired in a later stage.
"""

import abc
import logging
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PlaybackResult:
    """Result of a playback request."""
    played: bool
    duration_s: float
    error: Optional[str] = None


class AudioPlayer(abc.ABC):
    """Abstract audio playback interface."""

    @abc.abstractmethod
    def play(self, audio: np.ndarray, sample_rate: int = 22050) -> PlaybackResult:
        """Play audio samples.

        Args:
            audio: 1-D int16 numpy array.
            sample_rate: Playback rate in Hz.

        Returns:
            PlaybackResult.
        """
        ...

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop any currently playing audio immediately."""
        ...


class MockAudioPlayer(AudioPlayer):
    """Records calls for test assertions; does not produce sound."""

    @dataclass
    class _Call:
        num_samples: int
        sample_rate: int
        duration_s: float

    def __init__(self) -> None:
        self.calls: list[MockAudioPlayer._Call] = []
        self._stopped = False

    def play(self, audio: np.ndarray, sample_rate: int = 22050) -> PlaybackResult:
        audio = np.asarray(audio, dtype=np.int16)
        duration_s = len(audio) / sample_rate
        self.calls.append(
            self._Call(num_samples=len(audio), sample_rate=sample_rate,
                       duration_s=duration_s)
        )
        logger.debug("[MockPlayer] play: %d samples @ %d Hz (%.2f s)",
                     len(audio), sample_rate, duration_s)
        return PlaybackResult(played=True, duration_s=duration_s)

    def stop(self) -> None:
        self._stopped = True
        logger.debug("[MockPlayer] stop() called")

    @property
    def play_count(self) -> int:
        return len(self.calls)

    def reset(self) -> None:
        self.calls.clear()
        self._stopped = False


class SounddevicePlayer(AudioPlayer):
    """Live audio playback using sounddevice.

    Blocks until playback finishes (suitable for the current sequential
    state machine; can be made non-blocking if needed).
    """

    def play(self, audio: np.ndarray, sample_rate: int = 22050) -> PlaybackResult:
        try:
            import sounddevice as sd
        except ImportError as exc:
            return PlaybackResult(
                played=False,
                duration_s=0.0,
                error="sounddevice not installed",
            )

        audio = np.asarray(audio, dtype=np.int16)
        duration_s = len(audio) / sample_rate

        try:
            sd.play(audio, samplerate=sample_rate, blocking=True)
            return PlaybackResult(played=True, duration_s=duration_s)
        except Exception as exc:
            logger.warning("Playback error: %s", exc)
            return PlaybackResult(played=False, duration_s=0.0, error=str(exc))

    def stop(self) -> None:
        try:
            import sounddevice as sd
            sd.stop()
        except ImportError:
            pass
