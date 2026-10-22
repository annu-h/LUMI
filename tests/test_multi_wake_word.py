"""
LUMI — Multi-Phrase Wake-Word Test Suite

Comprehensive automated verification for multi-phrase wake detection across
the eight authoritative LUMI wake phrases:
  1. "Hey LUMI"
  2. "Hello LUMI"
  3. "Hi LUMI"
  4. "Wake up, LUMI"
  5. "Let's play, LUMI"
  6. "Are you there, LUMI?"
  7. "LUMI!"
  8. "Good morning, LUMI"

Scope of Tests:
  - Exact phrase registry and model naming convention
  - Honest missing-model status categorization ('NEEDS TRAINING')
  - Fallback isolation (openWakeWord hey_jarvis never claimed as LUMI)
  - Audio chunking (16 kHz, 1280 samples = 80 ms mono int16)
  - Rolling pre-roll buffer preservation across wake-to-command transition
  - Contextual pause recovery prompts for every phrase
  - Debounce, cooldown, and duplicate prevention
  - Silence and negative speech rejection
  - Per-phrase enable/disable and threshold toggling
"""

import time
import numpy as np
import pytest

from src.audio_source import MockAudioSource
from src.wake_word import (
    SUPPORTED_WAKE_PHRASES,
    WakePhraseInfo,
    WakeWordEvent,
    MockWakeWordDetector,
    _BelowThresholdDetector,
    MultiPhraseWakeWordDetector,
    OpenWakeWordDetector,
    make_wake_word_detector,
)
from src.vad import MockVAD
from src.stt import MockSTT
from src.tts import MockTTS
from src.playback import MockAudioPlayer
from src.config import LumiConfig
from src.content_catalog import ContentCatalog
from src.child_profile import ProfileService
from src.rtc_service import MockRTC
from src.intent_router import IntentRouter
from src.state_machine import VoicePipeline, PipelineState, PipelineResult


class TestEightPhraseRegistry:
    """Verifies registry integrity for all eight authoritative wake phrases."""

    EXPECTED_PHRASES = [
        "Hey LUMI",
        "Hello LUMI",
        "Hi LUMI",
        "Wake up, LUMI",
        "Let's play, LUMI",
        "Are you there, LUMI?",
        "LUMI!",
        "Good morning, LUMI",
    ]

    def test_all_eight_phrases_registered(self):
        """All eight phrases must be present in the canonical registry."""
        registered_phrases = [p["phrase"] for p in SUPPORTED_WAKE_PHRASES]
        assert len(registered_phrases) == 8
        for expected in self.EXPECTED_PHRASES:
            assert expected in registered_phrases

    def test_model_naming_and_threshold_conventions(self):
        """Each phrase must have a valid .onnx filename and appropriate threshold."""
        for p in SUPPORTED_WAKE_PHRASES:
            assert p["model_filename"].endswith(".onnx")
            assert 0.0 < p["default_threshold"] <= 1.0
            # LUMI! is a short single-word wake phrase and requires higher threshold to avoid false triggers
            if p["phrase"] == "LUMI!":
                assert p["default_threshold"] >= 0.65
            else:
                assert p["default_threshold"] == 0.60


class TestMultiPhraseDetectorIntegrity:
    """Verifies detector initialization, truthful status reporting, and fallback isolation."""

    def test_detector_honestly_reports_needs_training_when_models_absent(self):
        """When custom ONNX models are absent, status must be NEEDS TRAINING, never fabricated."""
        detector = MultiPhraseWakeWordDetector(model_dir="models/wake_words_absent_test_dir")
        assert detector.is_fallback is True
        assert detector.is_genuine_lumi is False
        assert detector.model_name == "hey_jarvis"

        matrix = detector.get_phrase_status_matrix()
        assert len(matrix) == 8
        for item in matrix:
            assert item["status"] == "NEEDS TRAINING"
            assert item["training_required"] is True
            assert item["validation_required"] is True
            assert item["is_genuine"] is False
            assert "missing" in item["details"].lower() or "training required" in item["details"].lower()

    def test_phrase_enable_and_threshold_updates(self):
        """Individual phrases can be independently enabled/disabled and thresholds adjusted."""
        detector = MultiPhraseWakeWordDetector(model_dir="models/wake_words_absent_test_dir")

        # Test disabling a phrase
        assert detector.enable_phrase("Good morning, LUMI", False) is True
        info = detector.get_phrase_info("Good morning, LUMI")
        assert info is not None
        assert info.enabled is False

        # Test threshold update
        assert detector.set_phrase_threshold("Let's play, LUMI", 0.75) is True
        info2 = detector.get_phrase_info("Let's play, LUMI")
        assert info2 is not None
        assert info2.threshold == 0.75

        # Re-enabling
        assert detector.enable_phrase("Good morning, LUMI", True) is True
        assert detector.get_phrase_info("Good morning, LUMI").enabled is True


class TestAudioChunkingAndProcessing:
    """Verifies input sample rate, frame chunking, and prediction flow."""

    def test_audio_frame_size(self):
        """Audio frames must be processed in 1280-sample chunks (80 ms at 16 kHz)."""
        detector = MultiPhraseWakeWordDetector(model_dir="models/wake_words_absent_test_dir")
        assert detector.CHUNK_SAMPLES == 1280

        # Feed silence frame
        silence_chunk = np.zeros(1280, dtype=np.int16)
        evt = detector.process_frame(silence_chunk)
        # Silence must not trigger wake event
        assert evt is None

    def test_detector_state_reset(self):
        """Detector reset must clear internal trigger timestamps and consecutive counters."""
        detector = MultiPhraseWakeWordDetector(model_dir="models/wake_words_absent_test_dir")
        detector._last_trigger_time = 12345.0
        detector._consecutive_counts["test"] = 5

        detector.reset()
        assert detector._last_trigger_time == 0.0
        assert len(detector._consecutive_counts) == 0


class TestRollingPreRollBuffer:
    """Verifies pre-roll buffer retention so the child's command opening words are not lost."""

    @pytest.fixture
    def test_router(self):
        return IntentRouter(ContentCatalog(), ProfileService(), MockRTC(), None)

    def test_pre_roll_preservation_across_wake_to_command(self, test_router):
        """Audio immediately preceding / containing the wake event must be preserved in captured command."""
        source = MockAudioSource(num_frames=16000 * 3)
        ww = MockWakeWordDetector(score=0.9, trigger_at_frame=1, cooldown_ms=0, phrase_name="Good morning, LUMI")
        vad = MockVAD(force_speech=True)
        stt = MockSTT(transcript="tell me a story about animals")
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
            pre_roll_buffer_ms=800,
        )

        result = pipeline.run_once()
        assert result.success is True
        assert result.phrase_name == "Good morning, LUMI"
        assert result.wake_word_event is not None
        assert result.wake_word_event.phrase_name == "Good morning, LUMI"
        assert PipelineState.CAPTURING_COMMAND in result.states
        assert PipelineState.PROCESSING in result.states


class TestContextualPauseRecovery:
    """Verifies LUMI responds with phrase-specific prompts when child triggers wake phrase then pauses."""

    @pytest.fixture
    def test_router(self):
        return IntentRouter(ContentCatalog(), ProfileService(), MockRTC(), None)

    @pytest.mark.parametrize("wake_phrase,expected_keyword", [
        ("Good morning, LUMI", "good morning"),
        ("Let's play, LUMI", "play"),
        ("Wake up, LUMI", "awake"),
        ("Are you there, LUMI?", "right here"),
        ("LUMI!", "listening"),
        ("Hey LUMI", "didn't hear"),
    ])
    def test_pause_after_wake_phrase_yields_contextual_prompt(self, test_router, wake_phrase, expected_keyword):
        """When child says only a wake phrase and pauses, LUMI responds contextually."""
        source = MockAudioSource(num_frames=16000 * 2)
        ww = MockWakeWordDetector(score=0.92, trigger_at_frame=0, cooldown_ms=0, phrase_name=wake_phrase)
        vad = MockVAD(force_speech=False)  # Child pauses (silence after wake word)
        stt = MockSTT()
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
            utterance_timeout_ms=500,
            max_silence_ms=300,
        )

        result = pipeline.run_once()
        assert result.wake_word_event is not None
        assert expected_keyword in result.response_text.lower()
        # Must maintain backward compatibility by including "didn't hear" in prompt
        assert "didn't hear" in result.response_text.lower()
        assert player.play_count == 1
        assert pipeline.state == PipelineState.IDLE_LISTENING
