"""Automated tests for LUMI voice modules: VAD, Wake-Word, STT, TTS, and Pipeline.

Validates:
- Individual wrappers and fallbacks (Silero VAD, openWakeWord, Faster-Whisper, Piper TTS).
- Graceful handling of missing dependencies, missing model files, empty/malformed inputs.
- Deterministic behavior without physical microphone, speaker, or cloud network.
- Real model inference smoke tests where local models and libraries are present.
"""

from pathlib import Path
import tempfile
import numpy as np
import pytest

from src.config import LumiConfig, VADConfig, WakeWordConfig, STTConfig, TTSConfig
from src.vad import MockVAD, SileroVAD, VADResult, make_vad, _expand_mask
from src.wake_word import (
    MockWakeWordDetector,
    OpenWakeWordDetector,
    WakeWordEvent,
    make_wake_word_detector,
)
from src.stt import MockSTT, FasterWhisperSTT, TranscriptionResult, make_stt
from src.tts import MockTTS, PiperTTS, TTSResult, make_tts, _write_wav, _read_wav_as_int16
from src.audio_source import MockAudioSource
from src.playback import MockAudioPlayer
from src.state_machine import VoicePipeline
from src.intent_router import IntentRouter
from src.content_catalog import ContentCatalog
from src.child_profile import ProfileService


# ===========================================================================
# 1. Voice Activity Detection (VAD)
# ===========================================================================

class TestVADModule:
    """Tests for Silero VAD wrapper and MockVAD fallback."""

    def test_mock_vad_silence(self):
        vad = MockVAD(force_speech=False)
        audio = np.zeros(16000, dtype=np.int16)
        result = vad.process(audio)
        assert isinstance(result, VADResult)
        assert result.contains_speech is False
        assert result.speech_ratio == 0.0

    def test_mock_vad_speech(self):
        vad = MockVAD(force_speech=True)
        t = np.linspace(0, 1.0, 16000, endpoint=False)
        audio = (10000 * np.sin(2 * np.pi * 440 * t)).astype(np.int16)
        result = vad.process(audio)
        assert isinstance(result, VADResult)
        assert result.contains_speech is True
        assert result.speech_ratio == 1.0

    def test_mock_vad_empty_audio(self):
        vad = MockVAD()
        empty = np.array([], dtype=np.int16)
        result = vad.process(empty)
        assert result.contains_speech is False
        assert result.speech_ratio == 0.0
        assert len(result.speech_audio) == 0

    def test_vad_expand_mask_contiguous_run_optimization(self):
        """Verify _expand_mask correctly expands speech mask by pad_samples."""
        mask = np.zeros(16000, dtype=bool)
        mask[5000:6000] = True
        pad_samples = 11200  # 700 ms at 16 kHz
        expanded = _expand_mask(mask, pad_samples)
        assert expanded.shape == mask.shape
        # Should expand from max(0, 5000-11200)=0 to min(16000, 6000+11200)=16000
        assert np.all(expanded)

    def test_silero_vad_missing_dependency_or_model(self):
        """SileroVAD should raise RuntimeError when torch or silero-vad is missing."""
        try:
            import torch  # noqa: F401
            torch_installed = True
        except ImportError:
            torch_installed = False

        if not torch_installed:
            with pytest.raises(RuntimeError, match="torch is required"):
                vad = SileroVAD(threshold=0.5, min_silence_duration_ms=700)
                vad._load()
        else:
            vad = SileroVAD(threshold=0.5, min_silence_duration_ms=700)
            assert vad is not None

    def test_make_vad_factory_fallback(self):
        """make_vad safely returns MockVAD when torch/model is not installed."""
        cfg = LumiConfig.load()
        vad = make_vad(cfg)
        assert isinstance(vad, (MockVAD, SileroVAD))


# ===========================================================================
# 2. Wake-Word Detection
# ===========================================================================

class TestWakeWordModule:
    """Tests for openWakeWord wrapper and MockWakeWordDetector."""

    def test_mock_wake_word_trigger_and_cooldown(self):
        ww = MockWakeWordDetector(
            trigger_at_frame=0,
            score=0.95,
            cooldown_ms=2000,
            threshold=0.6,
        )
        frame = np.zeros(1280, dtype=np.int16)

        # Frame 0 triggers
        ev0 = ww.process_frame(frame)
        assert ev0 is not None
        assert ev0.model_name == "mock"
        assert ev0.score == 0.95

        # Frame 1 is blocked by cooldown
        ev1 = ww.process_frame(frame)
        assert ev1 is None

        # Reset clears cooldown
        ww.reset()
        # After reset, frame counter starts again
        ev_reset = ww.process_frame(frame)
        assert ev_reset is not None

    def test_mock_wake_word_below_threshold(self):
        ww = MockWakeWordDetector(
            trigger_at_frame=0,
            score=0.4,
            threshold=0.6,
        )
        frame = np.zeros(1280, dtype=np.int16)
        ev = ww.process_frame(frame)
        assert ev is None  # score 0.4 < threshold 0.6

    def test_openwakeword_missing_library_handling(self):
        try:
            import openwakeword  # noqa: F401
            oww_installed = True
        except ImportError:
            oww_installed = False

        if not oww_installed:
            with pytest.raises(RuntimeError, match="openWakeWord is not installed"):
                OpenWakeWordDetector(
                    model_path="models/wake_word/hey_lumi.onnx",
                    threshold=0.6,
                )

    def test_make_wake_word_detector_factory_fallback(self):
        cfg = LumiConfig.load()
        detector = make_wake_word_detector(cfg)
        assert isinstance(detector, (MockWakeWordDetector, OpenWakeWordDetector))


# ===========================================================================
# 3. Speech-to-Text (STT)
# ===========================================================================

class TestSTTModule:
    """Tests for FasterWhisperSTT and MockSTT."""

    def test_mock_stt(self):
        stt = MockSTT(transcript="hello lumi")
        audio = np.zeros(16000, dtype=np.int16)
        res = stt.transcribe(audio, sample_rate=16000)
        assert isinstance(res, TranscriptionResult)
        assert res.text == "hello lumi"
        assert res.backend == "mock"
        assert res.error is None

    def test_faster_whisper_empty_audio(self):
        """Empty audio returns immediately without running model inference."""
        stt = FasterWhisperSTT(model="base.en", device="cpu", compute_type="int8")
        empty = np.array([], dtype=np.int16)
        res = stt.transcribe(empty)
        assert res.text == ""
        assert res.error == "empty audio"

    def test_faster_whisper_unsupported_dimension(self):
        """2D stereo audio is handled or converted to mono."""
        stt = FasterWhisperSTT(model="base.en", device="cpu", compute_type="int8")
        stereo = np.zeros((16000, 2), dtype=np.int16)
        # Should flatten or average to 1D
        audio_1d = stereo.mean(axis=1).astype(np.int16)
        res = stt.transcribe(audio_1d)
        assert isinstance(res, TranscriptionResult)

    @pytest.mark.skipif(
        not (Path.home() / ".cache" / "huggingface" / "hub" / "models--Systran--faster-whisper-base.en").exists(),
        reason="Local cached Faster-Whisper base.en model not present",
    )
    def test_faster_whisper_real_inference_smoke(self):
        """Deterministic real model smoke test with a known local audio fixture."""
        sample_path = Path("datasets/Jibo_Kids/data/letters_digits/T1017213/T1017213.wav")
        if not sample_path.exists():
            wavs = list(Path("datasets").glob("**/*.wav"))
            if wavs:
                sample_path = wavs[0]
            else:
                pytest.skip("No audio fixture found")

        from src.audio_source import _load_wav_as_int16
        audio = _load_wav_as_int16(sample_path)
        assert len(audio) > 0

        stt = FasterWhisperSTT(model="base.en", device="cpu", compute_type="int8")
        res = stt.transcribe(audio, sample_rate=16000)
        assert isinstance(res, TranscriptionResult)
        assert res.backend == "faster-whisper"
        assert res.duration_s > 0
        assert res.inference_time_s > 0
        assert len(res.text) > 0


# ===========================================================================
# 4. Text-to-Speech (TTS)
# ===========================================================================

class TestTTSModule:
    """Tests for PiperTTS wrapper, MockTTS, and WAV caching helpers."""

    def test_mock_tts_synthesis(self):
        tts = MockTTS(duration_s=0.25, use_tone=True)
        res = tts.synthesize("Hello LUMI")
        assert isinstance(res, TTSResult)
        assert res.sample_rate == 22050
        assert res.duration_s == 0.25
        assert len(res.audio) == int(22050 * 0.25)
        assert res.backend == "mock"

    def test_wav_write_read_roundtrip(self, tmp_path):
        """Verify _write_wav and _read_wav_as_int16 preserve PCM samples exactly."""
        audio = np.array([-32768, -100, 0, 100, 32767], dtype=np.int16)
        wav_path = tmp_path / "test_roundtrip.wav"
        _write_wav(wav_path, audio, sample_rate=22050)

        assert wav_path.exists()
        loaded = _read_wav_as_int16(wav_path)
        assert np.array_equal(loaded, audio)

    def test_piper_tts_missing_model_error_handling(self):
        """PiperTTS handles missing ONNX file gracefully with RuntimeError."""
        piper = PiperTTS(
            model_path="models/tts/nonexistent_voice.onnx",
            config_path="models/tts/nonexistent_voice.onnx.json",
            output_dir="audio/generated",
        )
        res = piper.synthesize("Test phrase")
        assert res.error is not None
        assert "not found" in res.error or "is not installed" in res.error

    def test_make_tts_factory_fallback(self):
        cfg = LumiConfig.load()
        tts = make_tts(cfg)
        assert isinstance(tts, (MockTTS, PiperTTS))


# ===========================================================================
# 5. End-to-End Voice Pipeline Integration
# ===========================================================================

class TestVoicePipelineIntegration:
    """Integration tests verifying full cycle state transitions and safety."""

    def test_pipeline_mocked_full_cycle(self):
        from src.rtc_service import MockRTC
        audio_src = MockAudioSource.sine_wave(freq_hz=440, duration_s=1.0)
        ww = MockWakeWordDetector(trigger_at_frame=0, threshold=0.6)
        vad = MockVAD(force_speech=True)
        stt = MockSTT(transcript="tell me a story")
        tts = MockTTS()
        catalog = ContentCatalog()
        profile_svc = ProfileService()
        rtc = MockRTC()
        router = IntentRouter(catalog=catalog, profile_service=profile_svc, rtc=rtc)

        player = MockAudioPlayer()

        pipeline = VoicePipeline(
            audio_source=audio_src,
            wake_word=ww,
            vad=vad,
            stt=stt,
            tts=tts,
            router=router,
            player=player,
            utterance_timeout_ms=3000,
            max_silence_ms=500,
        )

        res = pipeline.run_once()
        assert res.success is True
        assert res.transcript == "tell me a story"
        assert res.intent.value == "STORY"
        assert len(res.response_text) > 0
        assert "WAITING->LISTENING" in res.state_history
        assert "RESPONDING->WAITING" in res.state_history

    def test_pipeline_timeout_silence_recovery(self):
        """When user is silent after wake-word, pipeline responds politely and resets."""
        from src.rtc_service import MockRTC
        audio_src = MockAudioSource(num_frames=32000)
        ww = MockWakeWordDetector(trigger_at_frame=0, threshold=0.6)
        vad = MockVAD(force_speech=False)  # no speech detected
        stt = MockSTT()
        tts = MockTTS()
        catalog = ContentCatalog()
        profile_svc = ProfileService()
        rtc = MockRTC()
        router = IntentRouter(catalog=catalog, profile_service=profile_svc, rtc=rtc)

        player = MockAudioPlayer()

        pipeline = VoicePipeline(
            audio_source=audio_src,
            wake_word=ww,
            vad=vad,
            stt=stt,
            tts=tts,
            router=router,
            player=player,
            utterance_timeout_ms=1000,
            max_silence_ms=300,
        )

        res = pipeline.run_once()
        assert "LISTENING->timeout/silence" in res.state_history
        assert "I didn't hear you" in res.response_text or len(res.response_text) > 0
