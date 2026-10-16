"""
LUMI — Voice Pipeline State Machine

Implements the end-to-end voice-processing flow:

  WAITING → LISTENING → PROCESSING → RESPONDING → WAITING

Flow:
  1. Receive audio frames from the audio source.
  2. Feed frames to the wake-word detector (always, before VAD).
  3. On wake-word event → LISTENING: capture utterance frames.
  4. VAD: identify speech region and detect end-of-utterance silence.
  5. Transcribe with STT.
  6. Normalize transcript.
  7. Classify intent.
  8. Route intent → response text.
  9. Synthesize response with TTS.
  10. Play response via audio player.
  11. Return to WAITING.

Safe handling:
  - Wake-word false positives → timeout returns to WAITING.
  - Empty speech / silence → friendly "I didn't hear you" response.
  - Transcription failure → unknown-intent fallback.
  - Unknown intent → catalog fallback response.
  - Repeated triggers → cooldown in wake-word detector.
"""

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

import numpy as np

from .audio_source import AudioSource
from .wake_word import WakeWordDetector, WakeWordEvent
from .vad import VAD
from .stt import STT
from .tts import TTS
from .text_normalizer import normalize_text
from .intent_classifier import classify_intent, Intent
from .intent_router import IntentRouter, RoutingResult
from .playback import AudioPlayer

logger = logging.getLogger(__name__)

# Audio constants
SAMPLE_RATE = 16000
WAKE_WORD_CHUNK = 1280   # 80 ms at 16 kHz (openWakeWord default)
LISTEN_CHUNK = 512       # 32 ms at 16 kHz (Silero VAD chunk)


class PipelineState(Enum):
    WAITING = "WAITING"
    LISTENING = "LISTENING"
    PROCESSING = "PROCESSING"
    RESPONDING = "RESPONDING"
    STOPPED = "STOPPED"


@dataclass
class PipelineResult:
    """Full result of one voice interaction cycle."""
    state_history: list[str] = field(default_factory=list)
    wake_word_event: Optional[WakeWordEvent] = None
    transcript: str = ""
    intent: Optional[Intent] = None
    response_text: str = ""
    success: bool = False
    error: Optional[str] = None


class VoicePipeline:
    """Modular, testable voice-processing state machine."""

    def __init__(
        self,
        audio_source: AudioSource,
        wake_word: WakeWordDetector,
        vad: VAD,
        stt: STT,
        tts: TTS,
        router: IntentRouter,
        player: AudioPlayer,
        utterance_timeout_ms: int = 10000,
        max_silence_ms: int = 1500,
    ) -> None:
        self._audio = audio_source
        self._ww = wake_word
        self._vad = vad
        self._stt = stt
        self._tts = tts
        self._router = router
        self._player = player
        self._utterance_timeout_ms = utterance_timeout_ms
        self._max_silence_ms = max_silence_ms
        self._state = PipelineState.WAITING

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self) -> PipelineResult:
        """Run one full interaction cycle (blocking).

        Returns after the response is played or an error occurs.
        Intended for tests; production use calls run_forever().
        """
        result = PipelineResult()
        self._state = PipelineState.WAITING

        # 1–2. Wait for wake-word
        ww_event = self._wait_for_wake_word()
        if ww_event is None:
            result.error = "Audio exhausted without wake-word"
            result.state_history.append("WAITING->exhausted")
            return result

        result.wake_word_event = ww_event
        result.state_history.append("WAITING->LISTENING")
        self._state = PipelineState.LISTENING

        # 3–4. Capture utterance with VAD
        audio = self._capture_utterance()
        if audio is None or len(audio) == 0:
            result.state_history.append("LISTENING->timeout/silence")
            audio_for_tts = self._empty_speech_response()
            result.response_text = audio_for_tts
            result.state_history.append("->RESPONDING")
            self._respond(audio_for_tts)
            result.state_history.append("->WAITING")
            return result

        result.state_history.append("LISTENING->PROCESSING")
        self._state = PipelineState.PROCESSING

        # 5. Transcribe
        stt_result = self._stt.transcribe(audio, sample_rate=SAMPLE_RATE)
        if stt_result.error:
            logger.warning("STT error: %s", stt_result.error)

        raw_text = stt_result.text

        # 6. Normalize
        normalized = normalize_text(raw_text)
        result.transcript = normalized

        # 7. Classify
        classification = classify_intent(normalized)
        result.intent = classification.intent
        logger.info(
            "Pipeline: transcript='%s' -> intent=%s (%.2f)",
            normalized, classification.intent.value, classification.confidence,
        )

        # 8. Route
        routing: RoutingResult = self._router.route(classification)
        result.response_text = routing.response_text

        result.state_history.append("PROCESSING->RESPONDING")
        self._state = PipelineState.RESPONDING

        # 9–10. Synthesize and play
        self._respond(routing.response_text)

        # 11. Return to WAITING
        self._state = PipelineState.WAITING
        self._ww.reset()
        result.state_history.append("RESPONDING->WAITING")
        result.success = True
        return result

    def run_forever(self) -> None:
        """Blocking loop — runs until STOP intent or KeyboardInterrupt."""
        logger.info("LUMI voice pipeline started. Say 'Hey Lumi' to begin.")
        try:
            with self._audio:
                while self._state != PipelineState.STOPPED:
                    result = self.run_once()
                    if result.intent == Intent.EXIT:
                        logger.info("EXIT intent received — stopping pipeline.")
                        self._state = PipelineState.STOPPED
        except KeyboardInterrupt:
            logger.info("Pipeline interrupted by user.")

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _wait_for_wake_word(self) -> Optional[WakeWordEvent]:
        """Read audio chunks and return the first WakeWordEvent, or None
        if the audio source is exhausted."""
        while True:
            chunk = self._audio.read_frames(WAKE_WORD_CHUNK)
            if len(chunk) == 0:
                return None  # Audio exhausted
            event = self._ww.process_frame(chunk)
            if event:
                logger.info(
                    "Wake-word detected: model=%s score=%.3f",
                    event.model_name, event.score,
                )
                return event

    def _capture_utterance(self) -> Optional[np.ndarray]:
        """Capture audio after a wake-word event.

        Records until:
          - VAD detects end-of-utterance silence, OR
          - utterance_timeout_ms has elapsed.

        Returns the VAD-trimmed audio, or None on timeout with no speech.
        """
        deadline = time.monotonic() + self._utterance_timeout_ms / 1000.0
        frames: list[np.ndarray] = []
        silence_start: Optional[float] = None

        while time.monotonic() < deadline:
            chunk = self._audio.read_frames(LISTEN_CHUNK)
            if len(chunk) == 0:
                break
            frames.append(chunk)

            # Quick energy-based end-of-utterance detection
            # (SileroVAD will do a full pass on the complete buffer below)
            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            is_silent = rms < 200

            if is_silent:
                if silence_start is None:
                    silence_start = time.monotonic()
                elif (time.monotonic() - silence_start) * 1000 >= self._max_silence_ms:
                    break
            else:
                silence_start = None

        if not frames:
            return None

        full_audio = np.concatenate(frames)

        # Apply VAD to trim and validate speech
        vad_result = self._vad.process(full_audio)

        if not vad_result.contains_speech:
            logger.info("VAD: no speech detected in captured audio.")
            return None

        return vad_result.speech_audio

    def _respond(self, text: str) -> None:
        """Synthesize and play a response."""
        tts_result = self._tts.synthesize(text)
        if tts_result.error:
            logger.warning("TTS error: %s", tts_result.error)

        if len(tts_result.audio) > 0:
            self._player.play(tts_result.audio, sample_rate=tts_result.sample_rate)

    def _empty_speech_response(self) -> str:
        return "I didn't hear anything. Please try again after saying Hey Lumi."
