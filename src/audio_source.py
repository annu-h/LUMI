"""
LUMI — Audio Source Interface

Defines the AudioSource ABC and a MockAudioSource for tests and development.
A live microphone implementation will be added in a later stage.
"""

import abc
import struct
from pathlib import Path
from typing import Iterator
import numpy as np


class AudioSource(abc.ABC):
    """Abstract audio source. Implementations must be context managers."""

    SAMPLE_RATE: int = 16000  # Hz
    CHANNELS: int = 1         # Mono
    DTYPE: str = "int16"      # 16-bit PCM

    @abc.abstractmethod
    def __enter__(self) -> "AudioSource":
        ...

    @abc.abstractmethod
    def __exit__(self, *args) -> None:
        ...

    @abc.abstractmethod
    def read_frames(self, num_frames: int) -> np.ndarray:
        """Return a 1-D int16 numpy array of `num_frames` samples.

        Returns an empty array when the source is exhausted.
        """
        ...

    def iter_chunks(self, chunk_frames: int) -> Iterator[np.ndarray]:
        """Iterate audio as fixed-size chunks."""
        while True:
            chunk = self.read_frames(chunk_frames)
            if len(chunk) == 0:
                return
            yield chunk


class FileAudioSource(AudioSource):
    """Read audio from a WAV file via numpy (no soundfile dependency required
    for basic usage — uses struct to parse raw PCM from WAV header).

    For production use, soundfile is preferred for broader format support.
    """

    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._file = None
        self._audio: np.ndarray | None = None
        self._pos = 0

    def __enter__(self) -> "FileAudioSource":
        if not self._path.exists():
            raise FileNotFoundError(f"Audio file not found: {self._path}")
        self._audio = _load_wav_as_int16(self._path)
        self._pos = 0
        return self

    def __exit__(self, *args) -> None:
        self._audio = None
        self._pos = 0

    def read_frames(self, num_frames: int) -> np.ndarray:
        if self._audio is None:
            raise RuntimeError("FileAudioSource not opened (use as context manager)")
        chunk = self._audio[self._pos : self._pos + num_frames]
        self._pos += len(chunk)
        return chunk


class MockAudioSource(AudioSource):
    """Audio source backed by a pre-supplied numpy array.

    Used in tests to simulate audio without hardware or file I/O.
    """

    def __init__(self, audio: np.ndarray | None = None,
                 num_frames: int = 16000) -> None:
        """
        Args:
            audio: 1-D int16 numpy array. If None, generates silence.
            num_frames: Number of silence frames when audio is None.
        """
        if audio is None:
            self._audio = np.zeros(num_frames, dtype=np.int16)
        else:
            self._audio = np.asarray(audio, dtype=np.int16)
        self._pos = 0

    def __enter__(self) -> "MockAudioSource":
        self._pos = 0
        return self

    def __exit__(self, *args) -> None:
        pass

    def read_frames(self, num_frames: int) -> np.ndarray:
        chunk = self._audio[self._pos : self._pos + num_frames]
        self._pos += len(chunk)
        return chunk

    @classmethod
    def sine_wave(cls, freq_hz: float = 440.0, duration_s: float = 1.0,
                  sample_rate: int = 16000, amplitude: int = 8000) -> "MockAudioSource":
        """Create a MockAudioSource with a sine wave (useful in tests to simulate
        non-silent audio)."""
        t = np.linspace(0.0, duration_s, int(sample_rate * duration_s), endpoint=False)
        wave = (amplitude * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.int16)
        return cls(audio=wave)


# ---------------------------------------------------------------------------
# Minimal WAV loader (PCM only, no dependencies beyond stdlib + numpy)
# ---------------------------------------------------------------------------

def _load_wav_as_int16(path: Path) -> np.ndarray:
    """Read a mono or stereo 16-bit WAV file and return mono int16 samples."""
    with open(path, "rb") as f:
        data = f.read()

    # Validate RIFF/WAVE header
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError(f"Not a valid WAV file: {path}")

    # Locate fmt and data chunks
    pos = 12
    fmt_data: bytes | None = None
    audio_data: bytes | None = None

    while pos + 8 <= len(data):
        chunk_id = data[pos:pos+4]
        chunk_size = struct.unpack_from("<I", data, pos + 4)[0]
        chunk_body = data[pos+8: pos+8+chunk_size]
        pos += 8 + chunk_size
        if chunk_id == b"fmt ":
            fmt_data = chunk_body
        elif chunk_id == b"data":
            audio_data = chunk_body

    if fmt_data is None or audio_data is None:
        raise ValueError(f"WAV file missing fmt or data chunk: {path}")

    # Parse fmt chunk
    audio_format, channels, sample_rate, _, _, bits_per_sample = struct.unpack_from(
        "<HHIIHH", fmt_data
    )

    if audio_format == 1:
        if bits_per_sample != 16:
            raise ValueError(
                f"Only 16-bit PCM supported (bits={bits_per_sample}): {path}"
            )
        samples = np.frombuffer(audio_data, dtype=np.int16)
    elif audio_format == 3:
        if bits_per_sample != 32:
            raise ValueError(
                f"Only 32-bit float supported (bits={bits_per_sample}): {path}"
            )
        f_samples = np.frombuffer(audio_data, dtype=np.float32)
        samples = (np.clip(f_samples, -1.0, 1.0) * 32767.0).astype(np.int16)
    else:
        raise ValueError(f"Unsupported WAV format (format={audio_format}): {path}")

    # Downmix stereo to mono
    if channels == 2:
        samples = samples.reshape(-1, 2).mean(axis=1).astype(np.int16)
    elif channels != 1:
        raise ValueError(f"Only mono/stereo WAV supported (channels={channels}): {path}")

    return samples
