"""
Mocked pipeline integration tests for the LUMI voice system.
No physical hardware, no live microphone, no speaker required.
"""

import time
from unittest.mock import Mock

import numpy as np

from src.audio_source import MockAudioSource
from src.wake_word import MockWakeWordDetector
from src.vad import MockVAD
from src.stt import MockSTT
from src.tts import MockTTS
from src.playback import MockAudioPlayer
from src.config import LumiConfig
from src.content_catalog import ContentCatalog
from src.child_profile import ProfileService
from src.rtc_service import MockRTC
from src.intent_router import IntentRouter
from src.state_machine import VoicePipeline, PipelineState
from src.intent_classifier import Intent


def test_mocked_pipeline_hello():
    """Full mocked pipeline: wake-word → listen → transcribe → route → play."""
    # Mock audio with silence, then a wake-word trigger after a short delay.
    # We'll inject the wake-word event manually by using MockWakeWordDetector.
    source = MockAudioSource(num_frames=16000 * 5)  # 5 seconds silence
    ww = MockWakeWordDetector(
        score=0.85, trigger_at_frame=3, cooldown_ms=2000, threshold=0.6
    )
    vad = MockVAD(force_speech=True)
    stt = MockSTT(transcript="hello")
    tts = MockTTS(duration_s=0.3, use_tone=True)
    player = MockAudioPlayer()
    config = LumiConfig.load()
    router = IntentRouter(
        ContentCatalog(), ProfileService(), MockRTC(), None
    )

    pipeline = VoicePipeline(
        audio_source=source,
        wake_word=ww,
        vad=vad,
        stt=stt,
        tts=tts,
        router=router,
        player=player,
        utterance_timeout_ms=5000,
        max_silence_ms=700,
    )

    result = pipeline.run_once()

    assert result.success
    assert result.intent == Intent.HELLO
    assert result.wake_word_event is not None
    assert result.wake_word_event.score >= 0.6
    assert result.transcript == "hello"
    assert result.state_history[-1].startswith("RESPONDING")
    assert player.play_count == 1


def test_mocked_pipeline_stop():
    """STOP intent should stop the pipeline."""
    source = MockAudioSource(num_frames=16000 * 3)
    ww = MockWakeWordDetector(score=0.9, trigger_at_frame=1, cooldown_ms=1000)
    vad = MockVAD(force_speech=True)
    stt = MockSTT(transcript="stop please")
    tts = MockTTS(duration_s=0.5)
    player = MockAudioPlayer()
    config = LumiConfig.load()
    router = IntentRouter(
        ContentCatalog(), ProfileService(), MockRTC(), None
    )

    pipeline = VoicePipeline(
        audio_source=source,
        wake_word=ww,
        vad=vad,
        stt=stt,
        tts=tts,
        router=router,
        player=player,
        utterance_timeout_ms=5000,
        max_silence_ms=700,
    )

    result = pipeline.run_once()
    assert result.success
    assert result.intent == Intent.STOP
    assert result.response_text is not None
    assert len(result.response_text) > 0


def test_empty_speech_handled():
    """When VAD returns no speech, the pipeline should return gracefully."""
    source = MockAudioSource(num_frames=16000)  # 1 second
    # Force a wake-word event so the pipeline enters LISTENING.
    # Then VAD returns no speech, so audio is None.
    ww = MockWakeWordDetector(score=0.9, trigger_at_frame=0, cooldown_ms=0)
    vad = MockVAD(force_speech=False)  # No speech detected
    stt = MockSTT()
    tts = MockTTS()
    player = MockAudioPlayer()
    router = IntentRouter(
        ContentCatalog(), ProfileService(), MockRTC(), None
    )

    pipeline = VoicePipeline(
        audio_source=source,
        wake_word=ww,
        vad=vad,
        stt=stt,
        tts=tts,
        router=router,
        player=player,
        utterance_timeout_ms=2000,
        max_silence_ms=300,
    )

    result = pipeline.run_once()
    # Should complete without raising.
    assert result.error is None or "timeout/silence" in (result.error or "")


def test_repeated_triggers_and_cooldown():
    """Wake-word detector should respect cooldown."""
    ww = MockWakeWordDetector(
        score=0.9, trigger_at_frame=0, cooldown_ms=2000, threshold=0.6
    )
    event_1 = ww.process_frame(np.zeros(1280, dtype=np.int16))
    event_2 = ww.process_frame(np.zeros(1280, dtype=np.int16))

    assert event_1 is not None
    # Second call within cooldown should return None.
    assert event_2 is None


def test_vad_preserves_speech():
    from src.vad import MockVAD
    vad = MockVAD(force_speech=True)
    audio = np.ones(16000, dtype=np.int16) * 100  # Non-zero = speech
    result = vad.process(audio)
    assert result.contains_speech
    assert result.frames_speech > 0
    assert len(result.speech_audio) > 0


def test_intent_router_keypad():
    from src.intent_router import IntentRouter
    router = IntentRouter(
        ContentCatalog(), ProfileService(), MockRTC(), None
    )
    result = router.route_keypad("1")  # STORY
    assert result.intent == Intent.STORY
    assert len(result.response_text) > 0


def test_hobby_aware_content_selection():
    from src.child_profile import ProfileService
    profile = ProfileService()
    catalog = ContentCatalog()
    # Profile has hobbies: ["animals", "drawing", "puzzles"]
    prefs = profile.get_profile().content_preferences()
    # Content preferences are category IDs derived from hobbies.
    # "animals" hobby maps to ["animal_stories", "animal_quiz"].
    assert "animal_stories" in prefs
    assert "animal_quiz" in prefs
    item = catalog.get_by_category("learn", prefer_tags=prefs)
    assert item is not None
    assert item.category == "learn"


def test_rtc_mock_fixed_time():
    from datetime import datetime, timezone
    from src.rtc_service import MockRTC
    # Use a naive datetime to avoid timezone conversion surprises.
    fixed = datetime(2026, 10, 13, 9, 0, 0)
    rtc = MockRTC(fixed_time=fixed)
    now = rtc.now()
    assert now.hour == 9
    time_str = rtc.time_string()
    assert "9" in time_str
