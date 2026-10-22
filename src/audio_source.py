"""
LUMI — Audio Source Interface

Defines the AudioSource ABC, FileAudioSource, MockAudioSource, and
MicrophoneAudioSource (backed by sounddevice for live microphone input).
"""

import abc
import logging
import queue
import struct
import time
from pathlib import Path
from typing import Iterator, Optional
import numpy as np

logger = logging.getLogger(__name__)


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

        Returns an empty array when the source is exhausted or timed out.
        """
        ...

    def flush(self) -> None:
        """Flush any pending buffered audio (e.g. for echo suppression). Default no-op."""
        pass

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

    def flush(self) -> None:
        pass


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

    def flush(self) -> None:
        pass

    @classmethod
    def sine_wave(cls, freq_hz: float = 440.0, duration_s: float = 1.0,
                  sample_rate: int = 16000, amplitude: int = 8000) -> "MockAudioSource":
        """Create a MockAudioSource with a sine wave (useful in tests to simulate
        non-silent audio)."""
        t = np.linspace(0.0, duration_s, int(sample_rate * duration_s), endpoint=False)
        wave = (amplitude * np.sin(2.0 * np.pi * freq_hz * t)).astype(np.int16)
        return cls(audio=wave)


class MicrophoneAudioSource(AudioSource):
    """Live microphone audio capture using sounddevice.

    Streams 16 kHz mono int16 audio from the default or specified input device.
    Includes thread-safe buffering, non-blocking reads with timeouts, and
    buffer flushing for playback-aware echo suppression.
    """

    def __init__(self, sample_rate: int = 16000, device: Optional[int | str] = None,
                 blocksize: int = 512, queue_maxsize: int = 300,
                 read_timeout_s: float = 0.5) -> None:
        self._sample_rate = sample_rate
        self._device = device
        self._blocksize = blocksize
        self._queue_maxsize = queue_maxsize
        self._read_timeout_s = read_timeout_s
        self._queue: queue.Queue[np.ndarray] = queue.Queue(maxsize=queue_maxsize)
        self._residual = np.array([], dtype=np.int16)
        self._stream = None
        self._overflow_count = 0

    def _audio_callback(self, indata, frames, time_info, status):
        if status:
            logger.debug("Microphone status flag: %s", status)
        # Convert channel 0 to int16 mono
        raw = indata[:, 0]
        if raw.dtype == np.float32:
            chunk = (np.clip(raw, -1.0, 1.0) * 32767.0).astype(np.int16)
        else:
            chunk = np.asarray(raw, dtype=np.int16)

        try:
            self._queue.put_nowait(chunk)
        except queue.Full:
            self._overflow_count += 1
            # Drop oldest frame to keep latency real-time
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(chunk)
            except Exception:
                pass

    def __enter__(self) -> "MicrophoneAudioSource":
        try:
            import sounddevice as sd
        except ImportError as exc:
            raise RuntimeError("sounddevice is not installed. Run: pip install sounddevice") from exc

        self.flush()
        try:
            self._stream = sd.InputStream(
                samplerate=self._sample_rate,
                channels=1,
                dtype="int16",
                device=self._device,
                blocksize=self._blocksize,
                callback=self._audio_callback,
            )
            self._stream.start()
            logger.info("MicrophoneAudioSource: stream started @ %d Hz (device=%s)", self._sample_rate, self._device)
        except Exception as exc:
            raise RuntimeError(f"Failed to start microphone audio stream: {exc}") from exc
        return self

    def __exit__(self, *args) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                logger.debug("Error closing microphone stream: %s", exc)
            self._stream = None
        self.flush()

    def read_frames(self, num_frames: int) -> np.ndarray:
        """Read exactly num_frames samples, assembling from queue chunks."""
        collected = [self._residual] if len(self._residual) > 0 else []
        total = len(self._residual)
        self._residual = np.array([], dtype=np.int16)

        deadline = time.monotonic() + self._read_timeout_s
        while total < num_frames and time.monotonic() < deadline:
            try:
                chunk = self._queue.get(timeout=0.05)
                collected.append(chunk)
                total += len(chunk)
            except queue.Empty:
                continue

        if not collected:
            return np.array([], dtype=np.int16)

        full = np.concatenate(collected)
        if len(full) >= num_frames:
            ret = full[:num_frames]
            self._residual = full[num_frames:]
            return ret
        else:
            return full

    def flush(self) -> None:
        """Flush any pending buffered audio (e.g. for echo suppression)."""
        self._residual = np.array([], dtype=np.int16)
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


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
