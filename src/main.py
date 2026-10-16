"""
LUMI — Entry point for the voice pipeline.

Provides two CLI modes:
- run_once(): Runs a single mocked interaction for tests and demos.
- run_cli(): Blocks waiting for real audio (if mocked hardware).
"""

import logging

from .audio_source import MockAudioSource
from .wake_word import make_wake_word_detector
from .vad import make_vad
from .stt import make_stt
from .tts import make_tts
from .playback import MockAudioPlayer
from .config import LumiConfig
from .content_catalog import ContentCatalog
from .child_profile import ProfileService
from .rtc_service import MockRTC
from .intent_router import IntentRouter
from .state_machine import VoicePipeline


def run_cli():
    """Run a single mocked interaction (for CLI testing)."""
    print("LUMI - Starting voice pipeline (mocked)...")

    config = LumiConfig.load()

    # Configure logging
    logging.basicConfig(level=getattr(logging, config.pipeline.log_level))
    logger = logging.getLogger(__name__)

    # Initialize components with mocks for missing assets
    audio_source = MockAudioSource.sine_wave(freq_hz=440, duration_s=1.0)

    wake_word = make_wake_word_detector(config)
    vad = make_vad(config)
    stt = make_stt(config)
    tts = make_tts(config)
    player = MockAudioPlayer()

    router = IntentRouter(
        catalog=ContentCatalog(),
        profile_service=ProfileService(),
        rtc=MockRTC(),
        last_response=None,
    )

    pipeline = VoicePipeline(
        audio_source=audio_source,
        wake_word=wake_word,
        vad=vad,
        stt=stt,
        tts=tts,
        router=router,
        player=player,
        utterance_timeout_ms=config.pipeline.utterance_timeout_ms,
        max_silence_ms=1500,
    )

    result = pipeline.run_once()

    print("\n=== Pipeline Result ===")
    print(f"Wake-word event: {result.wake_word_event}")
    print(f"Transcript: {result.transcript}")
    print(f"Intent: {result.intent}")
    print(f"Response: {result.response_text}")
    print(f"Success: {result.success}")
    if result.error:
        print(f"Error: {result.error}")

    logger.info("Pipeline execution completed: success=%s", result.success)

    # Print warnings about missing assets for user awareness
    warnings = config.validate()
    if warnings:
        print("\nWarnings (may affect functionality):")
        for w in warnings:
            print(f"  - {w}")


def make_components(config: LumiConfig):
    """Create all components for a pipeline.

    Returned dict includes the audio_source (mocked for development)
    and real adapters when assets are present.
    """
    audio_source = MockAudioSource(MockAudioSource.sine_wave(freq_hz=440, duration_s=2.0))

    wake_word = make_wake_word_detector(config)
    vad = make_vad(config)
    stt = make_stt(config)
    tts = make_tts(config)
    player = MockAudioPlayer()

    return {
        "audio_source": audio_source,
        "wake_word": wake_word,
        "vad": vad,
        "stt": stt,
        "tts": tts,
        "player": player,
    }