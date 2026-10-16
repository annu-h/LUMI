"""
LUMI — Centralized Configuration

Loads settings from config/config.yaml with environment-variable overrides.
All voice-pipeline parameters are configurable and validated at startup.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)

# Project root: two levels up from src/config.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class WakeWordConfig:
    model_path: str = "models/wake_words/hey_lumi.onnx"
    fallback_model: str = "hey_jarvis"
    score_threshold: float = 0.6
    cooldown_ms: int = 2000

    def resolve_model_path(self) -> Path:
        p = Path(self.model_path)
        if not p.is_absolute():
            p = PROJECT_ROOT / p
        return p


@dataclass
class VADConfig:
    threshold: float = 0.5
    min_silence_duration_ms: int = 700
    sample_rate: int = 16000


@dataclass
class STTConfig:
    model: str = "base.en"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 1
    language: str = "en"


@dataclass
class TTSConfig:
    model_path: str = "models/tts/en_US-lessac-medium.onnx"
    config_path: str = "models/tts/en_US-lessac-medium.onnx.json"
    length_scale: float = 1.1
    output_dir: str = "audio/generated"


@dataclass
class PipelineConfig:
    utterance_timeout_ms: int = 10000
    max_recording_ms: int = 30000
    audio_dir: str = "audio"
    log_level: str = "INFO"
    retain_audio_for_debug: bool = False
    retain_transcripts_for_debug: bool = False


@dataclass
class LumiConfig:
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)

    @classmethod
    def load(cls, config_path: Optional[str] = None) -> "LumiConfig":
        """Load configuration from YAML file with env-var overrides."""
        cfg = cls()

        # Load YAML if available
        if config_path is None:
            config_path = os.environ.get(
                "LUMI_CONFIG", str(PROJECT_ROOT / "config" / "config.yaml")
            )

        path = Path(config_path)
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                raw = yaml.safe_load(f) or {}
            cfg._apply_dict(raw)
            logger.info("Loaded config from %s", path)
        else:
            logger.info("No config file at %s — using defaults", path)

        # Environment variable overrides
        cfg._apply_env_overrides()
        return cfg

    def _apply_dict(self, raw: dict) -> None:
        """Apply a nested dict to the config dataclasses."""
        for section_name, section_data in raw.items():
            section = getattr(self, section_name, None)
            if section is None or not isinstance(section_data, dict):
                continue
            for key, value in section_data.items():
                if hasattr(section, key):
                    expected_type = type(getattr(section, key))
                    try:
                        setattr(section, key, expected_type(value))
                    except (ValueError, TypeError) as exc:
                        logger.warning(
                            "Config: cannot set %s.%s=%r (%s)",
                            section_name, key, value, exc,
                        )

    def _apply_env_overrides(self) -> None:
        """Override specific settings from environment variables."""
        env_map = {
            "LUMI_WAKEWORD_THRESHOLD": ("wake_word", "score_threshold", float),
            "LUMI_VAD_THRESHOLD": ("vad", "threshold", float),
            "LUMI_VAD_SILENCE_MS": ("vad", "min_silence_duration_ms", int),
            "LUMI_STT_MODEL": ("stt", "model", str),
            "LUMI_STT_DEVICE": ("stt", "device", str),
            "LUMI_STT_COMPUTE_TYPE": ("stt", "compute_type", str),
            "LUMI_TTS_LENGTH_SCALE": ("tts", "length_scale", float),
            "LUMI_LOG_LEVEL": ("pipeline", "log_level", str),
            "LUMI_RETAIN_AUDIO": ("pipeline", "retain_audio_for_debug", _parse_bool),
        }
        for env_key, (section, attr, cast) in env_map.items():
            val = os.environ.get(env_key)
            if val is not None:
                try:
                    setattr(getattr(self, section), attr, cast(val))
                    logger.debug("Env override: %s → %s.%s", env_key, section, attr)
                except (ValueError, TypeError) as exc:
                    logger.warning("Env override %s=%r failed: %s", env_key, val, exc)

    def validate(self) -> list[str]:
        """Return a list of actionable warnings about missing assets."""
        warnings = []

        ww_path = self.wake_word.resolve_model_path()
        if not ww_path.exists():
            warnings.append(
                f"Wake-word model not found: {ww_path}. "
                "Wake-word detection will use mock/fallback."
            )

        tts_model = PROJECT_ROOT / self.tts.model_path
        if not tts_model.exists():
            warnings.append(
                f"TTS voice model not found: {tts_model}. "
                "TTS will use mock synthesis."
            )

        tts_cfg = PROJECT_ROOT / self.tts.config_path
        if not tts_cfg.exists():
            warnings.append(
                f"TTS config not found: {tts_cfg}. "
                "TTS will use mock synthesis."
            )

        if self.vad.threshold < 0.0 or self.vad.threshold > 1.0:
            warnings.append(
                f"VAD threshold {self.vad.threshold} is outside [0.0, 1.0]."
            )

        if self.wake_word.score_threshold < 0.0 or self.wake_word.score_threshold > 1.0:
            warnings.append(
                f"Wake-word threshold {self.wake_word.score_threshold} "
                "is outside [0.0, 1.0]."
            )

        return warnings


def _parse_bool(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes")
