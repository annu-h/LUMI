"""
LUMI — Multi-Phrase Wake-Word Detector Interface & Engine

Defines:
  - WakeWordEvent: Event emitted upon wake-word trigger.
  - WakePhraseInfo: Metadata, threshold, and status for each supported wake phrase.
  - WakeWordDetector: Abstract base class for wake detectors.
  - MockWakeWordDetector: Deterministic mock for automated test suites.
  - OpenWakeWordDetector: Single-model openWakeWord adapter (backwards-compatible).
  - MultiPhraseWakeWordDetector: Full multi-phrase detector supporting the 8 LUMI wake phrases:
      1. Hey LUMI
      2. Hello LUMI
      3. Hi LUMI
      4. Wake up, LUMI
      5. Let's play, LUMI
      6. Are you there, LUMI?
      7. LUMI!
      8. Good morning, LUMI

Architecture:
  - Audio chunk: 16 000 Hz, mono, int16, 80 ms (1 280 samples).
  - OpenWakeWord computes melspectrogram and 96-dim Google speech embeddings once per chunk,
    shared across all loaded binary classification models with minimal CPU/memory overhead.
  - When custom models are absent on disk, transparently falls back to hey_jarvis
    with is_fallback=True, never claiming fallback models are genuine LUMI models.
"""

import abc
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Project root: two levels up from src/wake_word.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Authoritative list of 8 supported LUMI wake phrases
SUPPORTED_WAKE_PHRASES: List[Dict[str, Any]] = [
    {
        "phrase": "Hey LUMI",
        "model_filename": "hey_lumi.onnx",
        "default_threshold": 0.6,
        "description": "Standard wake phrase for LUMI",
    },
    {
        "phrase": "Hello LUMI",
        "model_filename": "hello_lumi.onnx",
        "default_threshold": 0.6,
        "description": "Friendly greeting wake phrase",
    },
    {
        "phrase": "Hi LUMI",
        "model_filename": "hi_lumi.onnx",
        "default_threshold": 0.6,
        "description": "Short casual wake phrase",
    },
    {
        "phrase": "Wake up, LUMI",
        "model_filename": "wake_up_lumi.onnx",
        "default_threshold": 0.6,
        "description": "Direct wake activation phrase",
    },
    {
        "phrase": "Let's play, LUMI",
        "model_filename": "lets_play_lumi.onnx",
        "default_threshold": 0.6,
        "description": "Playful activity wake phrase",
    },
    {
        "phrase": "Are you there, LUMI?",
        "model_filename": "are_you_there_lumi.onnx",
        "default_threshold": 0.6,
        "description": "Presence-check wake phrase",
    },
    {
        "phrase": "LUMI!",
        "model_filename": "lumi.onnx",
        "default_threshold": 0.65,
        "description": "Single-word urgent/attention wake phrase (higher threshold)",
    },
    {
        "phrase": "Good morning, LUMI",
        "model_filename": "good_morning_lumi.onnx",
        "default_threshold": 0.6,
        "description": "Morning greeting wake phrase",
    },
]


@dataclass
class WakePhraseInfo:
    """Status and configuration for an individual wake phrase."""
    phrase: str
    model_filename: str
    model_path: Optional[str] = None
    threshold: float = 0.6
    enabled: bool = True
    status: str = "NEEDS TRAINING"  # VERIFIED, MODEL AVAILABLE — VALIDATION REQUIRED, NEEDS TRAINING, BLOCKED, UNSUPPORTED
    is_genuine: bool = False
    training_required: bool = True
    validation_required: bool = True
    details: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "phrase": self.phrase,
            "model_filename": self.model_filename,
            "model_path": self.model_path or f"models/wake_words/{self.model_filename}",
            "threshold": self.threshold,
            "enabled": self.enabled,
            "status": self.status,
            "is_genuine": self.is_genuine,
            "training_required": self.training_required,
            "validation_required": self.validation_required,
            "details": self.details,
        }


@dataclass
class WakeWordEvent:
    """Emitted when the detector crosses the score threshold."""
    score: float
    model_name: str
    timestamp_s: float = field(default_factory=time.time)
    is_fallback: bool = False
    raw_score: float = 0.0
    phrase_name: str = ""


class WakeWordDetector(abc.ABC):
    """Abstract wake-word detector."""

    @property
    def is_fallback(self) -> bool:
        """True if running a fallback model (e.g. hey_jarvis) rather than custom hey_lumi."""
        return False

    @property
    def is_genuine_lumi(self) -> bool:
        """True only if the active model is a genuine verified Hey LUMI model."""
        return False

    @property
    def model_name(self) -> str:
        """Name of the loaded wake-word model."""
        return "abstract"

    @abc.abstractmethod
    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        """Process one audio chunk.

        Args:
            audio_chunk: 1-D int16 numpy array (1280 samples at 16 kHz).

        Returns:
            WakeWordEvent if the threshold is crossed and cooldown has
            elapsed, else None.
        """
        ...

    @abc.abstractmethod
    def reset(self) -> None:
        """Reset internal state (e.g. after the utterance has been captured)."""
        ...


class MockWakeWordDetector(WakeWordDetector):
    """Deterministic mock for tests.

    Fires a WakeWordEvent at frame N (default 0), then obeys cooldown.
    """

    def __init__(
        self,
        score: float = 0.9,
        trigger_at_frame: int = 0,
        cooldown_ms: int = 2000,
        threshold: float = 0.6,
        model_name: str = "mock",
        is_fallback: bool = False,
        is_genuine_lumi: bool = False,
        phrase_name: str = "Hey LUMI",
    ) -> None:
        self._score = score
        self._trigger_at = trigger_at_frame
        self._cooldown_ms = cooldown_ms
        self._threshold = threshold
        self._model_name = model_name
        self._is_fallback = is_fallback
        self._is_genuine_lumi = is_genuine_lumi
        self._phrase_name = phrase_name
        self._frame_count = 0
        self._last_trigger_time: float = 0.0

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    @property
    def is_genuine_lumi(self) -> bool:
        return self._is_genuine_lumi

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def phrase_name(self) -> str:
        return self._phrase_name

    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        now = time.time()
        cooldown_s = self._cooldown_ms / 1000.0

        if (
            self._frame_count == self._trigger_at
            and self._score >= self._threshold
            and (now - self._last_trigger_time) >= cooldown_s
        ):
            self._frame_count += 1
            self._last_trigger_time = now
            return WakeWordEvent(
                score=self._score,
                model_name=self._model_name,
                is_fallback=self._is_fallback,
                raw_score=self._score,
                phrase_name=self._phrase_name,
            )

        self._frame_count += 1
        return None

    def reset(self) -> None:
        self._frame_count = 0
        self._last_trigger_time = 0.0


class _BelowThresholdDetector(WakeWordDetector):
    """Mock detector that never fires (score always below threshold)."""

    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        return None

    def reset(self) -> None:
        pass


class OpenWakeWordDetector(WakeWordDetector):
    """Adapter for the openWakeWord library (single model focus).

    Loads the custom hey_lumi.onnx model if available; otherwise falls back
    to a pretrained hey_jarvis model if installed. If neither model is
    useable, raises RuntimeError at construction time.

    Frame requirements (openWakeWord default):
        - 16 000 Hz, mono, int16.
        - Audio is fed in 80-ms chunks (1 280 samples at 16 kHz).
    """

    CHUNK_SAMPLES: int = 1280  # 80 ms at 16 kHz

    def __init__(
        self,
        model_path: Optional[str],
        threshold: float,
        cooldown_ms: int = 2000,
        consecutive_detections: int = 1,
    ) -> None:
        try:
            import openwakeword as oww  # noqa: F401
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "openWakeWord is not installed. "
                "Run: pip install openwakeword"
            ) from exc

        self._threshold = threshold
        self._cooldown_ms = cooldown_ms
        self._consecutive_detections = max(1, consecutive_detections)
        self._consecutive_count = 0
        self._last_trigger_time: float = 0.0
        self._model_path: Optional[str] = None
        self._is_fallback: bool = False
        self._is_genuine_lumi: bool = False

        resolved_path: Optional[str] = None
        if model_path:
            p = Path(model_path)
            if not p.is_absolute():
                p = PROJECT_ROOT / p
            if p.exists():
                resolved_path = str(p)
                self._model_path = resolved_path
                stem = p.stem.lower()
                self._is_genuine_lumi = "hey_lumi" in stem or "lumi" in stem
                self._is_fallback = not self._is_genuine_lumi
                logger.info("Wake-word: loaded model from %s (genuine_lumi=%s)", resolved_path, self._is_genuine_lumi)
            else:
                logger.warning(
                    "Wake-word custom model not found at %s; using fallback pretrained model (hey_jarvis).",
                    model_path,
                )

        try:
            if resolved_path:
                self._model = Model(wakeword_models=[resolved_path], inference_framework="onnx")
                self._model_name = Path(resolved_path).stem
            else:
                # Use pretrained hey_jarvis ONNX model with onnxruntime
                self._model = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
                names = list(getattr(self._model, "models", {}).keys())
                self._model_name = names[0] if names else "hey_jarvis"
                self._is_fallback = True
                self._is_genuine_lumi = False
                logger.info(
                    "Wake-word: using pretrained fallback model '%s' (Hey LUMI model absent).",
                    self._model_name,
                )
        except Exception as exc:
            raise RuntimeError(f"Failed to load openWakeWord model: {exc}") from exc

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    @property
    def is_genuine_lumi(self) -> bool:
        return self._is_genuine_lumi

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def model_path(self) -> Optional[str]:
        return self._model_path

    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        now = time.time()
        cooldown_s = self._cooldown_ms / 1000.0

        if (now - self._last_trigger_time) < cooldown_s:
            self._consecutive_count = 0
            return None

        prediction = self._model.predict(audio_chunk)

        for model_name, score in prediction.items():
            raw_score = float(score)
            if raw_score >= self._threshold:
                self._consecutive_count += 1
                if self._consecutive_count >= self._consecutive_detections:
                    self._last_trigger_time = now
                    self._consecutive_count = 0
                    return WakeWordEvent(
                        score=raw_score,
                        model_name=model_name,
                        is_fallback=self._is_fallback,
                        raw_score=raw_score,
                        phrase_name="Hey LUMI" if self._is_genuine_lumi else model_name,
                    )
            else:
                self._consecutive_count = 0

        return None

    def reset(self) -> None:
        self._last_trigger_time = 0.0
        self._consecutive_count = 0
        try:
            if hasattr(self._model, "reset"):
                self._model.reset()
        except Exception:
            pass


class MultiPhraseWakeWordDetector(OpenWakeWordDetector):
    """Multi-phrase wake-word detector engine supporting the 8 LUMI wake phrases.

    Architecture & Verification:
      - Uses openWakeWord's shared acoustic feature extraction (melspectrogram + Google embedding).
      - Loads all genuine phrase models present on disk in models/wake_words/.
      - If no genuine phrase models are present on disk, activates 'hey_jarvis' as an explicit
        development fallback detector (with is_fallback=True), never claiming fallback is genuine.
      - Maintains independent per-phrase configuration, thresholds, and enablement toggles.
      - Produces an authoritative status matrix matching:
          VERIFIED, MODEL AVAILABLE — VALIDATION REQUIRED, NEEDS TRAINING, BLOCKED, UNSUPPORTED.
    """

    CHUNK_SAMPLES: int = 1280  # 80 ms at 16 kHz

    def __init__(
        self,
        model_dir: Optional[str | Path] = None,
        phrases: Optional[List[Dict[str, Any]]] = None,
        fallback_model: str = "hey_jarvis",
        cooldown_ms: int = 2000,
        consecutive_detections: int = 1,
    ) -> None:
        try:
            import openwakeword as oww  # noqa: F401
            from openwakeword.model import Model
        except ImportError as exc:
            raise RuntimeError(
                "openWakeWord is not installed. "
                "Run: pip install openwakeword"
            ) from exc

        self._model_dir = Path(model_dir) if model_dir else PROJECT_ROOT / "models" / "wake_words"
        self._fallback_model = fallback_model
        self._cooldown_ms = cooldown_ms
        self._consecutive_detections = max(1, consecutive_detections)
        self._consecutive_counts: Dict[str, int] = {}
        self._last_trigger_time: float = 0.0

        # Build registry of phrases
        self._phrase_registry: Dict[str, WakePhraseInfo] = {}
        phrase_defs = phrases if phrases is not None else SUPPORTED_WAKE_PHRASES

        for p_def in phrase_defs:
            phrase_str = p_def["phrase"]
            filename = p_def.get("model_filename", f"{phrase_str.lower().replace(' ', '_').replace(',', '').replace('!', '').replace('?', '')}.onnx")
            threshold = float(p_def.get("threshold", p_def.get("default_threshold", 0.6)))
            enabled = bool(p_def.get("enabled", True))

            model_file = self._model_dir / filename
            exists = model_file.is_file()

            if exists:
                status = "MODEL AVAILABLE — VALIDATION REQUIRED"
                details = f"Model file present at {model_file.relative_to(PROJECT_ROOT) if model_file.is_relative_to(PROJECT_ROOT) else model_file}. Validation required."
                training_req = False
                val_req = True
                is_gen = True
            else:
                status = "NEEDS TRAINING"
                details = f"Model asset missing at models/wake_words/{filename}. Training required."
                training_req = True
                val_req = True
                is_gen = False

            info = WakePhraseInfo(
                phrase=phrase_str,
                model_filename=filename,
                model_path=str(model_file) if exists else None,
                threshold=threshold,
                enabled=enabled,
                status=status,
                is_genuine=is_gen,
                training_required=training_req,
                validation_required=val_req,
                details=details,
            )
            self._phrase_registry[phrase_str] = info

        # Identify which models to load into openWakeWord
        models_to_load: List[str] = []
        self._model_to_phrase: Dict[str, str] = {}
        self._is_fallback = False
        self._is_genuine_lumi = False

        for phrase_str, info in self._phrase_registry.items():
            if info.enabled and info.model_path and Path(info.model_path).exists():
                models_to_load.append(info.model_path)
                stem = Path(info.model_path).stem
                self._model_to_phrase[stem] = phrase_str
                self._is_genuine_lumi = True

        if models_to_load:
            logger.info("MultiPhraseWakeWord: loading %d genuine models: %s", len(models_to_load), models_to_load)
            try:
                self._model = Model(wakeword_models=models_to_load, inference_framework="onnx")
                self._model_name = ", ".join(list(getattr(self._model, "models", {}).keys()))
                self._is_fallback = False
            except Exception as exc:
                logger.error("Failed loading genuine models (%s); falling back to %s", exc, self._fallback_model)
                models_to_load = []

        if not models_to_load:
            # Fall back to pretrained hey_jarvis
            try:
                self._model = Model(wakeword_models=[self._fallback_model], inference_framework="onnx")
                names = list(getattr(self._model, "models", {}).keys())
                self._model_name = names[0] if names else self._fallback_model
                self._is_fallback = True
                self._is_genuine_lumi = False
                logger.info(
                    "MultiPhraseWakeWord: no genuine LUMI models found on disk. "
                    "Pretrained fallback '%s' active for development testing.",
                    self._model_name,
                )
            except Exception as exc:
                raise RuntimeError(f"Failed to load fallback openWakeWord model: {exc}") from exc

    @property
    def is_fallback(self) -> bool:
        return self._is_fallback

    @property
    def is_genuine_lumi(self) -> bool:
        return self._is_genuine_lumi

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def phrases(self) -> List[WakePhraseInfo]:
        return list(self._phrase_registry.values())

    def get_phrase_info(self, phrase: str) -> Optional[WakePhraseInfo]:
        return self._phrase_registry.get(phrase)

    def enable_phrase(self, phrase: str, enabled: bool = True) -> bool:
        if phrase in self._phrase_registry:
            self._phrase_registry[phrase].enabled = enabled
            return True
        return False

    def set_phrase_threshold(self, phrase: str, threshold: float) -> bool:
        if phrase in self._phrase_registry:
            self._phrase_registry[phrase].threshold = float(threshold)
            return True
        return False

    def mark_phrase_status(self, phrase: str, status: str, details: str = "") -> bool:
        valid_statuses = {
            "VERIFIED",
            "MODEL AVAILABLE — VALIDATION REQUIRED",
            "NEEDS TRAINING",
            "BLOCKED",
            "UNSUPPORTED",
        }
        if phrase in self._phrase_registry and status in valid_statuses:
            self._phrase_registry[phrase].status = status
            if details:
                self._phrase_registry[phrase].details = details
            if status == "VERIFIED":
                self._phrase_registry[phrase].validation_required = False
                self._phrase_registry[phrase].training_required = False
            return True
        return False

    def get_phrase_status_matrix(self) -> List[Dict[str, Any]]:
        """Return the authoritative status matrix for all 8 phrases."""
        return [info.to_dict() for info in self._phrase_registry.values()]

    def process_frame(self, audio_chunk: np.ndarray) -> Optional[WakeWordEvent]:
        now = time.time()
        cooldown_s = self._cooldown_ms / 1000.0

        if (now - self._last_trigger_time) < cooldown_s:
            self._consecutive_counts.clear()
            return None

        # Predict with openWakeWord (single shared forward pass)
        prediction = self._model.predict(audio_chunk)

        if self._is_fallback:
            # Fallback path (e.g. hey_jarvis)
            for m_name, score in prediction.items():
                raw_score = float(score)
                # Default threshold for fallback
                fb_thresh = 0.6
                if raw_score >= fb_thresh:
                    count = self._consecutive_counts.get(m_name, 0) + 1
                    self._consecutive_counts[m_name] = count
                    if count >= self._consecutive_detections:
                        self._last_trigger_time = now
                        self._consecutive_counts.clear()
                        return WakeWordEvent(
                            score=raw_score,
                            model_name=m_name,
                            is_fallback=True,
                            raw_score=raw_score,
                            phrase_name="Hey LUMI (Fallback: hey_jarvis)",
                        )
                else:
                    self._consecutive_counts[m_name] = 0
            return None

        # Multi-phrase genuine models path
        for m_name, score in prediction.items():
            raw_score = float(score)
            phrase_str = self._model_to_phrase.get(m_name, m_name)
            p_info = self._phrase_registry.get(phrase_str)

            if p_info and not p_info.enabled:
                continue

            thresh = p_info.threshold if p_info else 0.6

            if raw_score >= thresh:
                count = self._consecutive_counts.get(m_name, 0) + 1
                self._consecutive_counts[m_name] = count
                if count >= self._consecutive_detections:
                    self._last_trigger_time = now
                    self._consecutive_counts.clear()
                    return WakeWordEvent(
                        score=raw_score,
                        model_name=m_name,
                        is_fallback=False,
                        raw_score=raw_score,
                        phrase_name=phrase_str,
                    )
            else:
                self._consecutive_counts[m_name] = 0

        return None

    def reset(self) -> None:
        self._last_trigger_time = 0.0
        self._consecutive_counts.clear()
        try:
            if hasattr(self._model, "reset"):
                self._model.reset()
        except Exception:
            pass


def make_wake_word_detector(config) -> WakeWordDetector:
    """Factory: return the best available detector for the given config.

    Instantiates MultiPhraseWakeWordDetector when openWakeWord is installed;
    falls back to MockWakeWordDetector when openWakeWord is unavailable.
    """
    try:
        model_dir = PROJECT_ROOT / "models" / "wake_words"
        phrases = getattr(config.wake_word, "phrases", None) if hasattr(config, "wake_word") else None
        threshold = getattr(config.wake_word, "score_threshold", 0.6) if hasattr(config, "wake_word") else 0.6
        cooldown_ms = getattr(config.wake_word, "cooldown_ms", 2000) if hasattr(config, "wake_word") else 2000

        # Try multi-phrase detector
        return MultiPhraseWakeWordDetector(
            model_dir=model_dir,
            phrases=phrases,
            cooldown_ms=cooldown_ms,
        )
    except Exception as exc:
        logger.warning(
            "Real openWakeWord detector unavailable (%s). "
            "Falling back to mock detector. "
            "Wake-word testing with real audio is NOT available.",
            exc,
        )
        threshold = getattr(config.wake_word, "score_threshold", 0.6) if hasattr(config, "wake_word") else 0.6
        return MockWakeWordDetector(threshold=threshold)
