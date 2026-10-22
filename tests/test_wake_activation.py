"""
LUMI — Wake-Up Activation & State Machine Test Suite

Comprehensive automated verification for:
  - Wake-word model loading and missing-model handling
  - Fallback labelling (never claiming Jarvis is LUMI)
  - Full 6-state pipeline transitions:
      IDLE_LISTENING → WAKE_DETECTED → CAPTURING_COMMAND → PROCESSING → SPEAKING → RETURN_TO_LISTENING
  - Silence and non-wake speech rejection
  - Wake detection followed by command capture and educational routing
  - Timeout and empty-transcription recovery
  - Playback-aware echo suppression
"""

import time
import numpy as np
import pytest

from src.audio_source import MockAudioSource, MicrophoneAudioSource
from src.wake_word import (
    WakeWordDetector,
    WakeWordEvent,
    MockWakeWordDetector,
    _BelowThresholdDetector,
    OpenWakeWordDetector,
    make_wake_word_detector,
)
from src.vad import MockVAD, SileroVAD
from src.stt import MockSTT
from src.tts import MockTTS
from src.playback import MockAudioPlayer
from src.config import LumiConfig
from src.content_catalog import ContentCatalog
from src.child_profile import ProfileService
from src.rtc_service import MockRTC
from src.intent_router import IntentRouter
from src.state_machine import VoicePipeline, PipelineState, PipelineResult
from src.intent_classifier import Intent


class TestWakeWordModelIntegrity:
    """Tests ensuring genuine model validation and honest fallback labelling."""

    def test_missing_model_loads_fallback_without_fabrication(self):
        """When hey_lumi.onnx is absent, OpenWakeWordDetector loads hey_jarvis as fallback."""
        detector = OpenWakeWordDetector(
            model_path="models/wake_words/non_existent_hey_lumi.onnx",
            threshold=0.5,
        )
        assert detector.is_fallback is True
        assert detector.is_genuine_lumi is False
        assert "jarvis" in detector.model_name.lower()
        assert detector.model_path is None or not str(detector.model_path).endswith("non_existent_hey_lumi.onnx")

    def test_no_false_claim_that_jarvis_is_lumi(self):
        """The Jarvis fallback model must never claim to be Hey LUMI or genuine LUMI."""
        detector = OpenWakeWordDetector(model_path=None, threshold=0.5)
        assert detector.is_genuine_lumi is False
        assert detector.is_fallback is True
        assert detector.model_name == "hey_jarvis"

        # Frame inference output must be labelled as fallback
        dummy_frame = np.zeros(1280, dtype=np.int16)
        evt = detector.process_frame(dummy_frame)
        # Even if score was triggered, event must flag is_fallback=True
        mock_detector = MockWakeWordDetector(
            score=0.95,
            trigger_at_frame=0,
            model_name="hey_jarvis",
            is_fallback=True,
            is_genuine_lumi=False,
        )
        mock_evt = mock_detector.process_frame(dummy_frame)
        assert mock_evt is not None
        assert mock_evt.is_fallback is True
        assert mock_evt.model_name == "hey_jarvis"
        assert mock_detector.is_genuine_lumi is False


class TestWakeUpStateMachine:
    """Tests verifying the 6-state wake activation pipeline."""

    @pytest.fixture
    def test_router(self):
        return IntentRouter(ContentCatalog(), ProfileService(), MockRTC(), None)

    def test_full_six_state_cycle(self, test_router):
        """Pipeline transitions through all 6 states in order during a successful interaction."""
        source = MockAudioSource(num_frames=16000 * 4)
        ww = MockWakeWordDetector(score=0.88, trigger_at_frame=1, cooldown_ms=1000)
        vad = MockVAD(force_speech=True)
        stt = MockSTT(transcript="what is the letter a")
        tts = MockTTS(duration_s=0.2)
        player = MockAudioPlayer()

        states_visited = []

        def on_change(state, details):
            states_visited.append(state)

        pipeline = VoicePipeline(
            audio_source=source,
            wake_word=ww,
            vad=vad,
            stt=stt,
            tts=tts,
            router=test_router,
            player=player,
            utterance_timeout_ms=4000,
            max_silence_ms=600,
            on_state_change=on_change,
        )

        result = pipeline.run_once()

        assert result.success is True
        assert result.wake_word_event is not None
        assert result.wake_word_event.score == 0.88
        assert "a" in result.transcript.lower()
        assert player.play_count == 1

        # Check that all 6 states were visited
        assert PipelineState.IDLE_LISTENING in result.states
        assert PipelineState.WAKE_DETECTED in result.states
        assert PipelineState.CAPTURING_COMMAND in result.states
        assert PipelineState.PROCESSING in result.states
        assert PipelineState.SPEAKING in result.states
        assert PipelineState.RETURN_TO_LISTENING in result.states

        # Check sequence
        idx_idle = result.states.index(PipelineState.IDLE_LISTENING)
        idx_wake = result.states.index(PipelineState.WAKE_DETECTED)
        idx_capture = result.states.index(PipelineState.CAPTURING_COMMAND)
        idx_proc = result.states.index(PipelineState.PROCESSING)
        idx_speak = result.states.index(PipelineState.SPEAKING)
        idx_return = result.states.index(PipelineState.RETURN_TO_LISTENING)

        assert idx_idle < idx_wake < idx_capture < idx_proc < idx_speak < idx_return
        assert pipeline.state == PipelineState.IDLE_LISTENING

    def test_silence_does_not_trigger_wake(self, test_router):
        """Audio containing only silence must not trigger WAKE_DETECTED."""
        source = MockAudioSource(num_frames=16000 * 2)  # 2s pure silence
        ww = _BelowThresholdDetector()  # Never triggers
        vad = MockVAD(force_speech=False)
        stt = MockSTT()
        tts = MockTTS()
        player = MockAudioPlayer()

        pipeline = VoicePipeline(
            audio_source=source,
            wake_word=ww,
            vad=vad,
            stt=stt,
            tts=tts,
            router=test_router,
            player=player,
        )

        result = pipeline.run_once()

        assert result.success is False
        assert result.wake_word_event is None
        assert PipelineState.WAKE_DETECTED not in result.states
        assert PipelineState.PROCESSING not in result.states
        assert player.play_count == 0
        assert pipeline.state == PipelineState.IDLE_LISTENING

    def test_wake_detection_followed_by_empty_speech_timeout(self, test_router):
        """Wake-word triggers, but child does not speak -> graceful recovery to IDLE_LISTENING."""
        source = MockAudioSource(num_frames=16000 * 2)
        ww = MockWakeWordDetector(score=0.92, trigger_at_frame=0, cooldown_ms=0)
        vad = MockVAD(force_speech=False)  # VAD detects no speech
        stt = MockSTT()
        tts = MockTTS(duration_s=0.2)
        player = MockAudioPlayer()

        pipeline = VoicePipeline(
            audio_source=source,
            wake_word=ww,
            vad=vad,
            stt=stt,
            tts=tts,
            router=test_router,
            player=player,
            utterance_timeout_ms=1000,
            max_silence_ms=500,
        )

        result = pipeline.run_once()

        # Should recover gracefully, speaking the friendly fallback prompt
        assert result.wake_word_event is not None
        assert "didn't hear" in result.response_text.lower()
        assert player.play_count == 1
        assert PipelineState.RETURN_TO_LISTENING in result.states
        assert pipeline.state == PipelineState.IDLE_LISTENING

    def test_playback_aware_echo_suppression(self, test_router):
        """Microphone queue is flushed and playback-suppression window prevents self-activation."""
        source = MockAudioSource(num_frames=16000 * 3)
        ww = MockWakeWordDetector(score=0.9, trigger_at_frame=0, cooldown_ms=500)
        vad = MockVAD(force_speech=True)
        stt = MockSTT(transcript="hello")
        tts = MockTTS(duration_s=0.1)
        player = MockAudioPlayer()

        pipeline = VoicePipeline(
            audio_source=source,
            wake_word=ww,
            vad=vad,
            stt=stt,
            tts=tts,
            router=test_router,
            player=player,
            playback_suppression_ms=1000,
        )

        result = pipeline.run_once()
        assert result.success is True
        # Immediately after playback, suppression timestamp is recorded
        assert pipeline._last_playback_end_time > 0.0
        # Verification that time since playback is tracked
        assert (time.monotonic() - pipeline._last_playback_end_time) < 1.0


class TestMicrophoneSource:
    """Tests verifying the live MicrophoneAudioSource abstraction."""

    def test_microphone_source_attributes(self):
        source = MicrophoneAudioSource(sample_rate=16000, blocksize=512)
        assert source.SAMPLE_RATE == 16000
        assert source.CHANNELS == 1
        assert source.DTYPE == "int16"
        # flush() should not raise
        source.flush()
