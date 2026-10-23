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

KeypadDriver::KeypadDriver() : lastDebounceTime(0), lastRawState(KeyCode::NONE), reportedKey(KeyCode::NONE) {}

void KeypadDriver::begin() {
    // 1. All rows idle in High-Z (INPUT mode) to prevent current draw and protect GPIO 12.
    // Crucial: GPIO 12 (MTDI) stays High-Z at boot, allowing its internal weak pull-down
    // to keep it at 0V so the internal 3.3V flash LDO is selected at boot.
    for (uint8_t r = 0; r < ROWS; r++) {
        pinMode(ROW_PINS[r], INPUT);
    }
    
    // 2. Columns configured as inputs with 10k pull-ups to 3.3V:
    // GPIO 35 is input-only without internal pull-up (relies on external 10k pull-up to 3.3V).
    pinMode(COL_PINS[0], INPUT);
    // GPIO 13 and 15 have internal pull-ups that supplement the external 10k pull-up.
    pinMode(COL_PINS[1], INPUT_PULLUP);
    pinMode(COL_PINS[2], INPUT_PULLUP);
}

void KeypadDriver::readColumnIdleStates(int &col0, int &col1, int &col2) {
    // Ensure all rows are High-Z (INPUT)
    for (uint8_t r = 0; r < ROWS; r++) {
        pinMode(ROW_PINS[r], INPUT);
    }
    delayMicroseconds(5);
    // With 10k pull-ups to 3.3V, unpressed columns MUST read HIGH (1).
    col0 = digitalRead(COL_PINS[0]);
    col1 = digitalRead(COL_PINS[1]);
    col2 = digitalRead(COL_PINS[2]);
}

bool KeypadDriver::scanRaw(int &outRow, int &outCol, KeyCode &outKey) {
    for (uint8_t r = 0; r < ROWS; r++) {
        // Drive active row LOW (Active-LOW matrix scan for pull-up columns)
        pinMode(ROW_PINS[r], OUTPUT);
        digitalWrite(ROW_PINS[r], LOW);
        delayMicroseconds(10); // Settle line capacitance

        for (uint8_t c = 0; c < COLS; c++) {
            // Button press connects column node to row (0V / LOW)
            if (digitalRead(COL_PINS[c]) == LOW) {
                outRow = r;
                outCol = c;
                outKey = KEY_MAP[r][c];
                // Return row to High-Z before returning
                pinMode(ROW_PINS[r], INPUT);
                return true;
            }
        }

        // Return row to High-Z (floating) immediately
        pinMode(ROW_PINS[r], INPUT);
    }

    outRow = -1;
    outCol = -1;
    outKey = KeyCode::NONE;
    return false;
}

KeyCode KeypadDriver::update() {
    int r = -1, c = -1;
    KeyCode rawKey = KeyCode::NONE;
    scanRaw(r, c, rawKey);

    unsigned long now = millis();

    // Raw state changed: restart debounce timer
    if (rawKey != lastRawState) {
        lastRawState = rawKey;
        lastDebounceTime = now;
    }

    // State stable for > DEBOUNCE_DELAY
    if ((now - lastDebounceTime) >= DEBOUNCE_DELAY) {
        if (rawKey != reportedKey) {
            reportedKey = rawKey;
            // Edge trigger: report key ONCE on initial press, return NONE while held
            if (reportedKey != KeyCode::NONE) {
                return reportedKey;
            }
        }
    }

    return KeyCode::NONE;
}

char KeypadDriver::keyToChar(KeyCode key) {
    switch (key) {
        case KeyCode::NUM_0: return '0';
        case KeyCode::NUM_1: return '1';
        case KeyCode::NUM_2: return '2';
        case KeyCode::NUM_3: return '3';
        case KeyCode::NUM_4: return '4';
        case KeyCode::NUM_5: return '5';
        case KeyCode::NUM_6: return '6';
        case KeyCode::NUM_7: return '7';
        case KeyCode::NUM_8: return '8';
        case KeyCode::NUM_9: return '9';
        case KeyCode::BTN_BACKWARD: return '*';
        case KeyCode::BTN_FORWARD:  return '#';
        default: return '?';
    }
}

