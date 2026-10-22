"""
LUMI — Voice Pipeline State Machine

Implements the end-to-end voice-processing flow with explicit states:

  1. IDLE_LISTENING      — Continuously process microphone audio locally and search for "Hey LUMI"
  2. WAKE_DETECTED       — Confirm wake-word detection using configurable threshold and debounce
  3. CAPTURING_COMMAND   — Capture child's command after wake phrase using VAD and silence detection
  4. PROCESSING          — Transcribe captured command with local Faster-Whisper and route intent
  5. SPEAKING            — Speak response using local Piper TTS and audio player
  6. RETURN_TO_LISTENING — Purge residual playback audio (echo suppression) and resume listening

Includes:
  - Playback-aware echo suppression to prevent self-activation from LUMI's speaker output.
  - Transparent tracking of genuine Hey LUMI detector vs fallback models (e.g. hey_jarvis).
  - Graceful handling of empty speech, timeouts, noise, and audio stream interruptions.
  - Backwards-compatible aliases (WAITING, LISTENING, RESPONDING).
"""

import collections
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

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
WAKE_WORD_CHUNK = 1280   # 80 ms at 16 kHz (openWakeWord frame size)
LISTEN_CHUNK = 512       # 32 ms at 16 kHz (Silero VAD frame size)


class PipelineState(Enum):
    """Authoritative states of the LUMI voice pipeline."""
    IDLE_LISTENING = "IDLE_LISTENING"
    WAKE_DETECTED = "WAKE_DETECTED"
    CAPTURING_COMMAND = "CAPTURING_COMMAND"
    PROCESSING = "PROCESSING"
    SPEAKING = "SPEAKING"
    RETURN_TO_LISTENING = "RETURN_TO_LISTENING"
    STOPPED = "STOPPED"

    # Backwards-compatible aliases
    WAITING = "IDLE_LISTENING"
    LISTENING = "CAPTURING_COMMAND"
    RESPONDING = "SPEAKING"


@dataclass
class PipelineResult:
    """Full result of one voice interaction cycle."""
    state_history: List[str] = field(default_factory=list)
    states: List[PipelineState] = field(default_factory=list)
    wake_word_event: Optional[WakeWordEvent] = None
    phrase_name: str = ""
    transcript: str = ""
    intent: Optional[Intent] = None
    response_text: str = ""
    success: bool = False
    error: Optional[str] = None
    is_fallback: bool = False
    is_genuine_lumi: bool = False
    details: Dict[str, Any] = field(default_factory=dict)


class VoicePipeline:
    """Modular, testable, robust voice-processing state machine."""

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
        playback_suppression_ms: int = 800,
        consecutive_wake_detections: int = 1,
        pre_roll_buffer_ms: int = 800,
        on_state_change: Optional[Callable[[PipelineState, Dict[str, Any]], None]] = None,
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
        self._playback_suppression_ms = playback_suppression_ms
        self._consecutive_wake_detections = max(1, consecutive_wake_detections)
        self._pre_roll_buffer_ms = max(0, pre_roll_buffer_ms)
        self._on_state_change = on_state_change

        self._state = PipelineState.IDLE_LISTENING
        self._last_playback_end_time: float = 0.0
        self._last_pre_roll: Optional[np.ndarray] = None

    @property
    def state(self) -> PipelineState:
        return self._state

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self) -> PipelineResult:
        """Run one full interaction cycle (blocking).

        Returns after the response is played or an error/exhaustion occurs.
        Intended for tests and single-turn executions; production calls run_forever().
        """
        result = PipelineResult()
        result.is_fallback = getattr(self._ww, "is_fallback", False)
        result.is_genuine_lumi = getattr(self._ww, "is_genuine_lumi", False)

        # 1. State: IDLE_LISTENING
        self._set_state(PipelineState.IDLE_LISTENING, result, {"action": "listening_for_wake_phrase"})

        ww_event = self._wait_for_wake_word(result)
        if ww_event is None:
            result.error = "Audio exhausted without wake-word"
            result.state_history.append("WAITING->exhausted")
            return result

        result.wake_word_event = ww_event
        result.phrase_name = getattr(ww_event, "phrase_name", "") or ww_event.model_name
        result.is_fallback = ww_event.is_fallback

        # 2. State: WAKE_DETECTED
        self._set_state(
            PipelineState.WAKE_DETECTED,
            result,
            {
                "model": ww_event.model_name,
                "phrase": result.phrase_name,
                "score": ww_event.score,
                "is_fallback": ww_event.is_fallback,
            },
        )
        # Record backwards-compatible transition for existing test assertions
        result.state_history.append("WAITING->LISTENING")

        # 3. State: CAPTURING_COMMAND
        self._set_state(PipelineState.CAPTURING_COMMAND, result, {"action": "capturing_speech_command"})
        audio = self._capture_utterance()

        if audio is None or len(audio) == 0:
            result.state_history.append("LISTENING->timeout/silence")
            fallback_text = self._empty_speech_response(result.phrase_name)
            result.response_text = fallback_text

            # 4. State: SPEAKING (for the empty speech response)
            result.state_history.append("->RESPONDING")
            self._set_state(PipelineState.SPEAKING, result, {"text": fallback_text})
            self._respond(fallback_text)

            # 5. State: RETURN_TO_LISTENING
            self._return_to_listening(result)
            return result

        # 4. State: PROCESSING
        result.state_history.append("LISTENING->PROCESSING")
        self._set_state(PipelineState.PROCESSING, result, {"samples": len(audio)})

        # Transcribe
        stt_result = self._stt.transcribe(audio, sample_rate=SAMPLE_RATE)
        if stt_result.error:
            logger.warning("STT transcription notice: %s", stt_result.error)

        raw_text = stt_result.text
        normalized = normalize_text(raw_text)
        result.transcript = normalized

        # Classify & Route
        classification = classify_intent(normalized)
        result.intent = classification.intent
        logger.info(
            "Pipeline: transcript='%s' -> intent=%s (confidence=%.2f)",
            normalized, classification.intent.value, classification.confidence,
        )

        routing: RoutingResult = self._router.route(classification)
        result.response_text = routing.response_text

        # 5. State: SPEAKING
        result.state_history.append("PROCESSING->RESPONDING")
        self._set_state(PipelineState.SPEAKING, result, {"response": routing.response_text})

        # Synthesize & Play
        self._respond(routing.response_text)

        # 6. State: RETURN_TO_LISTENING
        self._return_to_listening(result)
        result.success = True
        return result

    def run_forever(self) -> None:
        """Blocking continuous loop — runs until STOP/EXIT intent or KeyboardInterrupt."""
        logger.info(
            "LUMI voice pipeline started. Continuously listening for '%s'.",
            "Hey LUMI" if getattr(self._ww, "is_genuine_lumi", False) else f"wake phrase (fallback: {getattr(self._ww, 'model_name', 'hey_jarvis')})",
        )
        try:
            with self._audio:
                while self._state != PipelineState.STOPPED:
                    result = self.run_once()
                    if result.intent in (Intent.STOP, Intent.EXIT):
                        logger.info("STOP/EXIT intent received — stopping pipeline.")
                        self._state = PipelineState.STOPPED
                        break
        except KeyboardInterrupt:
            logger.info("Pipeline interrupted by user.")
            self._state = PipelineState.STOPPED

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _set_state(self, state: PipelineState, result: Optional[PipelineResult] = None, details: Optional[Dict[str, Any]] = None) -> None:
        """Update internal state, notify callback, and log history."""
        old_state = self._state
        self._state = state
        transition = f"{old_state.name}->{state.name}"
        if result is not None:
            result.states.append(state)
            result.state_history.append(transition)
        if self._on_state_change:
            try:
                self._on_state_change(state, details or {})
            except Exception as exc:
                logger.debug("State callback error: %s", exc)

    def _wait_for_wake_word(self, result: PipelineResult) -> Optional[WakeWordEvent]:
        """Process frames continuously until wake word is confirmed or audio is exhausted.

        Maintains a rolling pre-roll buffer so the opening syllables of the child's
        subsequent command are preserved.
        """
        consecutive_hits = 0
        pre_roll_chunks = max(1, int(self._pre_roll_buffer_ms / 80))
        rolling_chunks: collections.deque = collections.deque(maxlen=pre_roll_chunks)

        while True:
            # Check playback suppression grace period
            now = time.monotonic()
            if (now - self._last_playback_end_time) < (self._playback_suppression_ms / 1000.0):
                # Discard frames during echo suppression window
                chunk = self._audio.read_frames(WAKE_WORD_CHUNK)
                if len(chunk) == 0:
                    return None
                continue

            chunk = self._audio.read_frames(WAKE_WORD_CHUNK)
            if len(chunk) == 0:
                return None  # Audio stream exhausted

            rolling_chunks.append(chunk)

            event = self._ww.process_frame(chunk)
            if event:
                consecutive_hits += 1
                if consecutive_hits >= self._consecutive_wake_detections:
                    logger.info(
                        "Wake-word confirmed: model=%s phrase='%s' score=%.3f (fallback=%s)",
                        event.model_name,
                        getattr(event, "phrase_name", ""),
                        event.score,
                        event.is_fallback,
                    )
                    # Preserve rolling audio buffer immediately preceding / containing the wake event
                    self._last_pre_roll = np.concatenate(list(rolling_chunks)) if rolling_chunks else None
                    return event
            else:
                consecutive_hits = 0

    def _capture_utterance(self) -> Optional[np.ndarray]:
        """Capture command audio after wake-word detection.

        Records until:
          - VAD and silence detection detect end-of-utterance silence, OR
          - utterance_timeout_ms has elapsed.

        Preserves pre-roll audio so early words in the utterance are not clipped.
        Returns VAD-trimmed speech audio, or None on silence/timeout.
        """
        deadline = time.monotonic() + self._utterance_timeout_ms / 1000.0
        frames: List[np.ndarray] = []
        silence_start: Optional[float] = None

        # Prepend pre-roll buffer if available
        if self._last_pre_roll is not None and len(self._last_pre_roll) > 0:
            frames.append(self._last_pre_roll)
            self._last_pre_roll = None

        while time.monotonic() < deadline:
            chunk = self._audio.read_frames(LISTEN_CHUNK)
            if len(chunk) == 0:
                break
            frames.append(chunk)

            # Energy check for silence tracking
            rms = float(np.sqrt(np.mean(chunk.astype(np.float64) ** 2)))
            is_silent = rms < 200.0

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

        # Apply VAD to trim leading/trailing silence and validate speech presence
        vad_result = self._vad.process(full_audio)
        if not vad_result.contains_speech:
            logger.info("VAD: no speech detected in captured audio.")
            return None

        return vad_result.speech_audio

    def _respond(self, text: str) -> None:
        """Synthesize and play response audio, updating playback timestamps."""
        tts_result = self._tts.synthesize(text)
        if tts_result.error:
            logger.warning("TTS notice: %s", tts_result.error)

        if len(tts_result.audio) > 0:
            self._player.play(tts_result.audio, sample_rate=tts_result.sample_rate)
            self._last_playback_end_time = time.monotonic()

    def _return_to_listening(self, result: PipelineResult) -> None:
        """Purge playback residual audio, reset wake detector, and return to IDLE_LISTENING."""
        self._set_state(PipelineState.RETURN_TO_LISTENING, result, {"action": "reset_detector_and_echo_suppression"})

        # Flush audio source queue to purge any reverberation captured while speaking
        self._audio.flush()

        # Reset wake detector internal cooldown and frame states
        self._ww.reset()

        # Update last playback end time to enforce playback suppression grace period
        self._last_playback_end_time = time.monotonic()

        self._state = PipelineState.IDLE_LISTENING
        result.states.append(PipelineState.IDLE_LISTENING)
        if self._on_state_change:
            try:
                self._on_state_change(PipelineState.IDLE_LISTENING, {"action": "resumed_idle_listening"})
            except Exception:
                pass
        result.state_history.append("RETURN_TO_LISTENING->IDLE_LISTENING")
        # Concluding backwards-compatible transition for existing test assertions
        result.state_history.append("RESPONDING->WAITING")

    def _empty_speech_response(self, phrase_name: str = "") -> str:
        """Generate a natural prompt when a child triggers a wake phrase but pauses without a question."""
        p_clean = phrase_name.strip().lower()
        if "morning" in p_clean:
            return "Good morning! I didn't hear a question yet. What would you like to learn?"
        elif "play" in p_clean:
            return "I'm ready to play! I didn't hear your question yet. What would you like to explore?"
        elif "wake" in p_clean:
            return "I'm awake and ready! I didn't hear anything. What should we explore?"
        elif "there" in p_clean:
            return "I'm right here! I didn't hear a question yet. How can I help you?"
        elif "lumi!" in p_clean:
            return "I'm listening! I didn't hear what you said. What can I do for you?"
        return "I didn't hear anything. Please try again after saying Hey Lumi."
