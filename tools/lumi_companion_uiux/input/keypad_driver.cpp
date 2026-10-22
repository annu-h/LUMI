#include "keypad_driver.h"

// Hardware pin mapping according to the updated 12-button breadboard wiring
const uint8_t KeypadDriver::ROW_PINS[KeypadDriver::ROWS] = {14, 27, 16, 12};
const uint8_t KeypadDriver::COL_PINS[KeypadDriver::COLS] = {35, 13, 15};

const KeyCode KeypadDriver::KEY_MAP[KeypadDriver::ROWS][KeypadDriver::COLS] = {
    { KeyCode::NUM_1,        KeyCode::NUM_2, KeyCode::NUM_3       },
    { KeyCode::NUM_4,        KeyCode::NUM_5, KeyCode::NUM_6       },
    { KeyCode::NUM_7,        KeyCode::NUM_8, KeyCode::NUM_9       },
    { KeyCode::BTN_BACKWARD, KeyCode::NUM_0, KeyCode::BTN_FORWARD }
};

KeypadDriver::KeypadDriver() : lastDebounceTime(0), lastKeyState(KeyCode::NONE) {}

void KeypadDriver::begin() {
    // Rows set as high-impedance inputs initially
    for (uint8_t r = 0; r < ROWS; r++) {
        pinMode(ROW_PINS[r], INPUT_PULLUP);
    }
    // Columns are pulled UP to 3.3V via external 10k resistors
    // Note: GPIO 35 is input-only on the ESP32
    for (uint8_t c = 0; c < COLS; c++) {
        pinMode(COL_PINS[c], INPUT);
    }
}

KeyCode KeypadDriver::update() {
    KeyCode currentKey = KeyCode::NONE;

    for (uint8_t r = 0; r < ROWS; r++) {
        // Drive active row LOW
        pinMode(ROW_PINS[r], OUTPUT);
        digitalWrite(ROW_PINS[r], LOW);
        delayMicroseconds(10);

        for (uint8_t c = 0; c < COLS; c++) {
            // Button press connects column to LOW (active-low via external 10k pull-up)
            if (digitalRead(COL_PINS[c]) == LOW) {
                currentKey = KEY_MAP[r][c];
                break;
            }
        }

        // Return row to high-impedance input
        pinMode(ROW_PINS[r], INPUT_PULLUP);

        if (currentKey != KeyCode::NONE) {
            break;
        }
    }

    // Debounce state transition
    if (currentKey != lastKeyState) {
        lastDebounceTime = millis();
        lastKeyState = currentKey;
        return KeyCode::NONE;
    }

    if ((millis() - lastDebounceTime) > 30) {
        return currentKey;
    }

    return KeyCode::NONE;
}