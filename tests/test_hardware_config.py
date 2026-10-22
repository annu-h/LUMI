"""
Unit tests for LUMI hardware configuration, pin mapping validation, and safety checks.
"""

import pytest
from src.config import LumiConfig, HardwareConfig, KeypadHardwareConfig
from src.intent_router import IntentRouter, KeypadMode
from src.intent_classifier import Intent
from src.content_catalog import ContentCatalog
from src.child_profile import ProfileService
from src.rtc_service import MockRTC


def test_hardware_config_defaults():
    """Verify authoritative pin mappings match the hardware wiring checklist."""
    cfg = LumiConfig.load()
    hw = cfg.hardware

    # Keypad
    assert hw.keypad.rows == [14, 27, 16, 12]
    assert hw.keypad.columns == [35, 13, 15]
    assert hw.keypad.debounce_ms == 20
    assert hw.keypad.default_mode == "shortcut"

    # Status LED
    assert hw.led.green_gpio == 32
    assert hw.led.active_high is True

    # I2S Audio
    assert hw.i2s.bclk_gpio == 26
    assert hw.i2s.ws_lrclk_gpio == 25
    assert hw.i2s.mic_data_in_gpio == 34
    assert hw.i2s.amp_data_out_gpio == 33
    assert hw.i2s.sample_rate == 16000
    assert hw.i2s.full_duplex is True

    # SD Card & TFT SPI
    assert hw.spi.sck_gpio == 18
    assert hw.spi.mosi_gpio == 23
    assert hw.spi.miso_gpio == 19
    assert hw.spi.sd_cs_gpio == 17
    assert hw.spi.tft_cs_gpio == 5

    # TFT Control
    assert hw.tft.cs_gpio == 5
    assert hw.tft.dc_gpio == 2
    assert hw.tft.reset_gpio == 4
    assert hw.tft.header == "main_14pin"

    # RTC I2C
    assert hw.i2c.sda_gpio == 21
    assert hw.i2c.scl_gpio == 22


def test_hardware_safety_validation_flags():
    """Verify that validate() flags strapping pins and input-only GPIO 35 for manual review."""
    cfg = LumiConfig.load()
    warnings = cfg.validate()

    # Must flag GPIO 12 strapping pin
    assert any("GPIO 12" in w and "MTDI" in w for w in warnings)

    # Must flag GPIO 15 strapping pin
    assert any("GPIO 15" in w and "MTDO" in w for w in warnings)

    # Must flag GPIO 2 strapping pin
    assert any("GPIO 2" in w and "Boot mode" in w for w in warnings)

    # Must flag GPIO 35 input-only requirement for external pull-down
    assert any("GPIO 35" in w and "Input-Only" in w for w in warnings)


def test_keypad_shortcut_mode_routing():
    """Verify that keypad keys trigger identical intent handlers as voice commands."""
    router = IntentRouter(ContentCatalog(), ProfileService(), MockRTC(), None)
    assert router.keypad_mode == KeypadMode.SHORTCUT

    # Digit 1 -> STORY
    res1 = router.route_keypad("1")
    assert res1.intent == Intent.STORY
    assert len(res1.response_text) > 0

    # Digit 2 -> LEARN
    res2 = router.route_keypad("2")
    assert res2.intent == Intent.LEARN
    assert len(res2.response_text) > 0

    # Digit 3 -> MUSIC
    res3 = router.route_keypad("3")
    assert res3.intent == Intent.MUSIC

    # Digit 0 -> HELLO
    res0 = router.route_keypad("0")
    assert res0.intent == Intent.HELLO

    # Star (*) -> BACK
    res_star = router.route_keypad("*")
    assert res_star.intent == Intent.BACK

    # Hash (#) -> NEXT
    res_hash = router.route_keypad("#")
    assert res_hash.intent == Intent.NEXT


def test_keypad_numeric_entry_mode():
    """Verify that keypad numeric-entry mode accumulates digits and handles * clear / # submit."""
    router = IntentRouter(ContentCatalog(), ProfileService(), MockRTC(), None)
    router.set_keypad_mode(KeypadMode.NUMERIC)
    assert router.keypad_mode == KeypadMode.NUMERIC
    assert router.get_numeric_buffer() == ""

    # Enter '4', '2'
    r1 = router.route_keypad("4")
    assert router.get_numeric_buffer() == "4"
    assert "Entered 4" in r1.response_text

    r2 = router.route_keypad("2")
    assert router.get_numeric_buffer() == "42"
    assert "Current number: 42" in r2.response_text

    # Backspace with '*'
    r_back = router.route_keypad("*")
    assert router.get_numeric_buffer() == "4"
    assert "Cleared 2" in r_back.response_text

    # Add '7' -> '47'
    router.route_keypad("7")
    assert router.get_numeric_buffer() == "47"

    # Submit with '#'
    r_sub = router.route_keypad("#")
    assert "You entered the number 47" in r_sub.response_text
    assert router.get_numeric_buffer() == ""  # Buffer cleared after submit

    # Switch back to shortcut mode
    router.set_keypad_mode(KeypadMode.SHORTCUT)
    res_shortcut = router.route_keypad("1")
    assert res_shortcut.intent == Intent.STORY
