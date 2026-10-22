#pragma once
#include <Arduino.h>

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
    static const uint8_t ROWS = 4;
    static const uint8_t COLS = 3;
    static const uint8_t ROW_PINS[ROWS];
    static const uint8_t COL_PINS[COLS];
    static const KeyCode KEY_MAP[ROWS][COLS];
    unsigned long lastDebounceTime;
    KeyCode lastKeyState;
};