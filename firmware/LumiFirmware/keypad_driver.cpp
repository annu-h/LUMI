#include "keypad_driver.h"

// Authoritative hardware pin mapping from lumi_pins.h
const uint8_t KeypadDriver::ROW_PINS[KeypadDriver::ROWS] = {
    LUMI_PIN_KEYPAD_ROW_0, // GPIO 14
    LUMI_PIN_KEYPAD_ROW_1, // GPIO 27
    LUMI_PIN_KEYPAD_ROW_2, // GPIO 16
    LUMI_PIN_KEYPAD_ROW_3  // GPIO 12 [STRAPPING PIN: MTDI]
};

const uint8_t KeypadDriver::COL_PINS[KeypadDriver::COLS] = {
    LUMI_PIN_KEYPAD_COL_0, // GPIO 35 [INPUT-ONLY: Requires external pull-down]
    LUMI_PIN_KEYPAD_COL_1, // GPIO 13
    LUMI_PIN_KEYPAD_COL_2  // GPIO 15 [STRAPPING PIN: MTDO]
};

// 4x3 Keypad layout mapping
const KeyCode KeypadDriver::KEY_MAP[KeypadDriver::ROWS][KeypadDriver::COLS] = {
    { KeyCode::NUM_1,        KeyCode::NUM_2, KeyCode::NUM_3       },
    { KeyCode::NUM_4,        KeyCode::NUM_5, KeyCode::NUM_6       },
    { KeyCode::NUM_7,        KeyCode::NUM_8, KeyCode::NUM_9       },
    { KeyCode::BTN_BACKWARD, KeyCode::NUM_0, KeyCode::BTN_FORWARD }
};

KeypadDriver::KeypadDriver() : lastDebounceTime(0), lastKeyState(KeyCode::NONE) {}

void KeypadDriver::begin() {
    // Rows set as high-impedance inputs initially with internal pullup
    // NOTE: GPIO 12 (MTDI) idles high-impedance so it doesn't violate 3.3V flash boot strapping
    for (uint8_t r = 0; r < ROWS; r++) {
        pinMode(ROW_PINS[r], INPUT_PULLUP);
    }
    
    // Columns are pulled UP via external 10k resistors (required for GPIO 35 input-only pin)
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
            // Button press connects column to LOW (active-low via external pull-up)
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

    // Debounce logic
    unsigned long now = millis();
    if (currentKey != lastKeyState) {
        lastDebounceTime = now;
        lastKeyState = currentKey;
        return KeyCode::NONE;
    }

    if ((now - lastDebounceTime) > DEBOUNCE_DELAY) {
        return currentKey;
    }

    return KeyCode::NONE;
}
