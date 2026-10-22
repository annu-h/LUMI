#pragma once
#include <Arduino.h>
#include "../../include/lumi_pins.h"

/**
 * @file keypad_driver.h
 * @brief 4x3 Matrix Keypad driver for Project LUMI.
 *
 * Hardware Mapping (from lumi_pins.h):
 *   - Rows:    GPIO 14, 27, 16, 12
 *   - Columns: GPIO 35, 13, 15
 *
 * Safety Notes:
 *   - GPIO 35 is an input-only pin on the ESP32 (requires external 10k pull-down/pull-up).
 *   - GPIO 12 is a strapping pin (MTDI) - must NOT be pulled HIGH during boot.
 *   - GPIO 15 is a strapping pin (MTDO) - controls boot ROM UART output.
 */

enum class KeyCode {
    NONE = 0,
    NUM_0,
    NUM_1,
    NUM_2,
    NUM_3,
    NUM_4,
    NUM_5,
    NUM_6,
    NUM_7,
    NUM_8,
    NUM_9,
    BTN_BACKWARD,
    BTN_FORWARD
};

class KeypadDriver {
public:
    KeypadDriver();
    void begin();
    KeyCode update();

private:
    static const uint8_t ROWS = LUMI_KEYPAD_NUM_ROWS;
    static const uint8_t COLS = LUMI_KEYPAD_NUM_COLS;
    static const uint8_t ROW_PINS[ROWS];
    static const uint8_t COL_PINS[COLS];
    static const KeyCode KEY_MAP[ROWS][COLS];
    unsigned long lastDebounceTime;
    KeyCode lastKeyState;
};
