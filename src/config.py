"""
LUMI — Centralized Configuration

Loads settings from config/config.yaml with environment-variable overrides.
All voice-pipeline parameters are configurable and validated at startup.
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)

# Project root: two levels up from src/config.py
PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass
class WakePhraseConfig:
    phrase: str
    model_filename: str
    threshold: float = 0.6
    enabled: bool = True


@dataclass
class WakeWordConfig:
    model_path: str = "models/wake_words/hey_lumi.onnx"
    fallback_model: str = "hey_jarvis"
    score_threshold: float = 0.6
    cooldown_ms: int = 2000
    pre_roll_buffer_ms: int = 800
    phrases: List[Dict[str, Any]] = field(default_factory=lambda: [
        {"phrase": "Hey LUMI", "model_filename": "hey_lumi.onnx", "threshold": 0.6, "enabled": True},
        {"phrase": "Hello LUMI", "model_filename": "hello_lumi.onnx", "threshold": 0.6, "enabled": True},
        {"phrase": "Hi LUMI", "model_filename": "hi_lumi.onnx", "threshold": 0.6, "enabled": True},
        {"phrase": "Wake up, LUMI", "model_filename": "wake_up_lumi.onnx", "threshold": 0.6, "enabled": True},
        {"phrase": "Let's play, LUMI", "model_filename": "lets_play_lumi.onnx", "threshold": 0.6, "enabled": True},
        {"phrase": "Are you there, LUMI?", "model_filename": "are_you_there_lumi.onnx", "threshold": 0.6, "enabled": True},
        {"phrase": "LUMI!", "model_filename": "lumi.onnx", "threshold": 0.65, "enabled": True},
        {"phrase": "Good morning, LUMI", "model_filename": "good_morning_lumi.onnx", "threshold": 0.6, "enabled": True},
    ])

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
class KeypadHardwareConfig:
    rows: list[int] = field(default_factory=lambda: [14, 27, 16, 12])
    columns: list[int] = field(default_factory=lambda: [35, 13, 15])
    debounce_ms: int = 20
    default_mode: str = "shortcut"  # "shortcut" or "numeric"


@dataclass
class LEDHardwareConfig:
    green_gpio: int = 32
    active_high: bool = True


@dataclass
class I2SHardwareConfig:
    bclk_gpio: int = 26
    ws_lrclk_gpio: int = 25
    mic_data_in_gpio: int = 34
    amp_data_out_gpio: int = 33
    sample_rate: int = 16000
    bits_per_sample: int = 32
    full_duplex: bool = True


@dataclass
class SPIHardwareConfig:
    sck_gpio: int = 18
    mosi_gpio: int = 23
    miso_gpio: int = 19
    sd_cs_gpio: int = 17
    tft_cs_gpio: int = 5


@dataclass
class I2CHardwareConfig:
    sda_gpio: int = 21
    scl_gpio: int = 22
    frequency_hz: int = 100000


@dataclass
class TFTHardwareConfig:
    cs_gpio: int = 5
    dc_gpio: int = 2
    reset_gpio: int = 4
    header: str = "main_14pin"
    miso_troubleshoot_note: str = "Disconnect TFT MISO if SPI contention occurs (write-only display)"


@dataclass
class SDCardHardwareConfig:
    cs_gpio: int = 17
    bus: str = "spi"
    power_voltage: str = "check_breakout"


@dataclass
class HardwareConfig:
    board: str = "ESP32 DevKit V1 / ESP32-WROOM-32"
    keypad: KeypadHardwareConfig = field(default_factory=KeypadHardwareConfig)
    led: LEDHardwareConfig = field(default_factory=LEDHardwareConfig)
    i2s: I2SHardwareConfig = field(default_factory=I2SHardwareConfig)
    spi: SPIHardwareConfig = field(default_factory=SPIHardwareConfig)
    i2c: I2CHardwareConfig = field(default_factory=I2CHardwareConfig)
    tft: TFTHardwareConfig = field(default_factory=TFTHardwareConfig)
    sd_card: SDCardHardwareConfig = field(default_factory=SDCardHardwareConfig)


@dataclass
class LumiConfig:
    wake_word: WakeWordConfig = field(default_factory=WakeWordConfig)
    vad: VADConfig = field(default_factory=VADConfig)
    stt: STTConfig = field(default_factory=STTConfig)
    tts: TTSConfig = field(default_factory=TTSConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    hardware: HardwareConfig = field(default_factory=HardwareConfig)

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
            self._apply_to_object(section, section_data, section_name)

    def _apply_to_object(self, target: Any, data: dict, path_prefix: str) -> None:
        for key, value in data.items():
            if not hasattr(target, key):
                continue
            current_attr = getattr(target, key)
            if hasattr(current_attr, "__dataclass_fields__") and isinstance(value, dict):
                self._apply_to_object(current_attr, value, f"{path_prefix}.{key}")
            else:
                expected_type = type(current_attr)
                try:
                    if isinstance(current_attr, list) and isinstance(value, list):
                        setattr(target, key, list(value))
                    elif isinstance(current_attr, bool) and isinstance(value, bool):
                        setattr(target, key, value)
                    else:
                        setattr(target, key, expected_type(value))
                except (ValueError, TypeError) as exc:
                    logger.warning(
                        "Config: cannot set %s.%s=%r (%s)",
                        path_prefix, key, value, exc,
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

        # Hardware safety and strapping pin reviews
        hw = self.hardware
        strapping_pins = {
            12: "GPIO 12 (MTDI flash voltage strapping pin - must NOT be pulled HIGH at boot)",
            15: "GPIO 15 (MTDO boot log output strapping pin - controls boot console logging)",
            2: "GPIO 2 (Boot mode strapping pin - must be LOW or floating during download boot)",
        }
        for pin, note in strapping_pins.items():
            if pin in hw.keypad.rows:
                warnings.append(f"Hardware Caution: Keypad Row uses {note}. Ensure row is not held HIGH during reset.")
            if pin in hw.keypad.columns:
                warnings.append(f"Hardware Caution: Keypad Column uses {note}. Ensure column line does not perturb boot.")
            if pin == hw.tft.dc_gpio:
                warnings.append(f"Hardware Caution: TFT DC uses {note}. Ensure display module does not prevent UART boot.")

        if 35 in hw.keypad.columns:
            warnings.append(
                "Hardware Note: Keypad Column uses GPIO 35 (Input-Only GPI). "
                "GPIO 35 lacks internal pull-up/pull-down resistors; external physical pull-down (10k) is REQUIRED."
            )

        # SPI CS conflict check
        if hw.spi.sd_cs_gpio == hw.spi.tft_cs_gpio:
            warnings.append(
                f"Hardware Conflict: SD Card and TFT share the same CS pin (GPIO {hw.spi.sd_cs_gpio}). "
                "Separate CS lines are required."
            )

        # Full-duplex I2S clock alignment check
        if hw.i2s.full_duplex and hw.i2s.bclk_gpio != 26:
            warnings.append(
                f"Hardware Review: I2S BCLK configured to GPIO {hw.i2s.bclk_gpio}. Expected GPIO 26."
            )

        return warnings


def _parse_bool(val: str) -> bool:
    return val.strip().lower() in ("1", "true", "yes")
