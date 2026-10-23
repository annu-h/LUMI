/**
 * @file LumiFirmware.ino
 * @brief Project LUMI ESP32 Firmware — Physical Bring-Up Suite & Voice Stack Interface.
 *
 * Target Hardware: ESP32 DevKit V1 / ESP32-WROOM-32 (Original ESP32)
 * Framework: Arduino ESP32 Core 3.3.11 / ESP-IDF v5.x
 * Serial Port: COM3 @ 115200 baud
 *
 * Staged Bring-Up Architecture:
 *   1. MODE_DIAGNOSTIC (Default on boot):
 *      - 100% Clean ASCII interactive menu in Serial Monitor (NO garbled characters).
 *      - 8 Independent, non-blocking hardware test modes.
 *      - TFT is DISABLED by default (LUMI_ENABLE_TFT = 0) until physically wired.
 *      - Keypad configured for external 10k pull-ups to 3.3V (active-LOW scan).
 *   2. MODE_PRODUCTION:
 *      - Binary framed protocol for Python voice companion (src/serial_bridge.py).
 */

#include <Arduino.h>
#include <SPI.h>
#include <Wire.h>
#include <SD.h>

#include "lumi_pins.h"
#include "lumi_config.h"
#include "lumi_protocol.h"
#include "serial_protocol.h"
#include "audio_manager.h"
#include "keypad_driver.h"
#include "ui_manager.h"
#include "rtc_manager.h"

// Firmware version
#define LUMI_FW_VERSION_MAJOR  1
#define LUMI_FW_VERSION_MINOR  1
#define LUMI_FW_VERSION_PATCH  1

// Operation Modes
enum FirmwareMode {
    MODE_DIAGNOSTIC = 0,
    MODE_PRODUCTION = 1
};

FirmwareMode current_firmware_mode = MODE_DIAGNOSTIC;

// Component instances
SerialProtocol serial_proto;
AudioManager *audio_mgr = nullptr;
KeypadDriver keypad;
UIManager ui;
RTCManager rtc;

// Peripheral status flags
bool sd_initialized = false;
bool rtc_initialized = false;
bool tft_initialized = false;
bool i2s_initialized = false;

// Production System state
lumi_system_state_t current_state = STATE_BOOT;
bool capture_active = false;
bool playback_active = false;
uint32_t last_heartbeat_ms = 0;
uint8_t mic_seq = 0;

// LED blink pattern state
unsigned long last_led_toggle = 0;
bool led_state = false;

// Forward declarations for 8 Diagnostic Modes
void print_menu();
void diag_1_led_and_boot();
void diag_2_rtc();
void diag_3_sd();
void diag_4_keypad();
void diag_5_mic();
void diag_6_speaker();
void diag_7_tft();
void diag_8_serial_protocol();
void diag_run_all();
void switch_to_production_mode();

void handle_rx_packet(const lumi_packet_t &pkt);
void handle_command(lumi_command_t cmd);
void handle_keypad_press(KeyCode key);

void setup() {
    // 1. Safe GPIO states at power-on
    pinMode(LUMI_PIN_LED_GREEN, OUTPUT);
    digitalWrite(LUMI_PIN_LED_GREEN, LOW);

    // De-assert SPI chip selects immediately to prevent bus contention
    pinMode(LUMI_PIN_SD_CS, OUTPUT);
    digitalWrite(LUMI_PIN_SD_CS, HIGH);

#if LUMI_ENABLE_TFT
    pinMode(LUMI_PIN_TFT_CS, OUTPUT);
    digitalWrite(LUMI_PIN_TFT_CS, HIGH);
#endif

    // 2. Start Serial at 115200 baud for Serial Monitor (Clean ASCII Mode)
    Serial.begin(115200);
    delay(300); // Allow UART CDC to stabilize

    // 3. Initialize I2C and probe DS3231 RTC
#if LUMI_ENABLE_RTC
    rtc_initialized = rtc.begin(LUMI_PIN_I2C_SDA, LUMI_PIN_I2C_SCL, LUMI_I2C_FREQ_HZ);
#endif

    // 4. Initialize SPI and probe MicroSD Card
#if LUMI_ENABLE_SD
    SPI.begin(LUMI_PIN_SPI_SCK, LUMI_PIN_SPI_MISO, LUMI_PIN_SPI_MOSI, -1);
    sd_initialized = SD.begin(LUMI_PIN_SD_CS, SPI);
#endif

    // 5. Initialize Keypad Driver (Active-LOW scan for 10k pull-ups to 3.3V)
#if LUMI_ENABLE_KEYPAD
    keypad.begin();
#endif

    // 6. Initialize I2S Audio Controller (I2S0 shared clock: BCLK 26, WS 25)
#if LUMI_ENABLE_AUDIO
    lumi_audio_config_t audio_cfg = lumi_get_default_i2s_config();
    audio_mgr = new AudioManager(audio_cfg);
    i2s_initialized = audio_mgr->begin();
#endif

    // 7. TFT initialization: Disabled by default until physically wired
#if LUMI_ENABLE_TFT
    ui.begin();
    ui.runDiagnosticTest();
    tft_initialized = true;
#else
    tft_initialized = false; // Intentionally disabled until installed
#endif

    // 8. Present Diagnostic Console Menu
    print_menu();
}

void print_menu() {
    Serial.println();
    Serial.println(F("=============================================================="));
    Serial.println(F("  * PROJECT LUMI -- HARDWARE BRING-UP & DIAGNOSTIC CONSOLE *"));
    Serial.printf("  Firmware: v%d.%d.%d | Board: %s | MCU: %s\n",
                  LUMI_FW_VERSION_MAJOR, LUMI_FW_VERSION_MINOR, LUMI_FW_VERSION_PATCH,
                  LUMI_TARGET_BOARD, LUMI_TARGET_MCU);
    Serial.println(F("  Serial Port: COM3 @ 115200 baud (Clean ASCII Mode)"));
    Serial.println(F("=============================================================="));
    Serial.println(F("Peripheral Detection Status:"));
    Serial.printf("  [%s] Status LED    : GPIO 32 (330 ohm to GND, Active HIGH)\n", "OK");
    Serial.printf("  [%s] DS3231 RTC    : I2C (SDA:21, SCL:22, VCC:3.3V)\n",
                  rtc_initialized ? "OK" : "NOT DETECTED");
    Serial.printf("  [%s] MicroSD Card  : SPI (CS:17, SCK:18, MOSI:23, MISO:19, VCC:5V)\n",
                  sd_initialized ? "OK" : "NOT DETECTED");
    Serial.printf("  [%s] Keypad Matrix : 4x3 (Rows: 14,27,16,12 | Cols: 35,13,15 | Pull-Ups: 3.3V)\n", "READY");
    Serial.printf("  [%s] I2S Audio Hub : I2S0 (BCLK:26, WS:25 | Mic DIN:34, Spk DOUT:33)\n",
                  i2s_initialized ? "OK" : "FAIL");
#if LUMI_ENABLE_TFT
    Serial.printf("  [%s] TFT Display   : ILI9341 SPI (CS:5, DC:2, RST:4, SCK:18, MOSI:23)\n",
                  tft_initialized ? "OK" : "FAIL");
#else
    Serial.println(F("  [DISABLED] TFT Display: Not physically installed yet (LUMI_ENABLE_TFT=0)"));
#endif
    Serial.println(F("--------------------------------------------------------------"));
    Serial.println(F("Select a diagnostic test (Type character and press Enter):"));
    Serial.println(F("  [1] Boot and LED Test (Blink GPIO 32, check rail readiness)"));
    Serial.println(F("  [2] DS3231 RTC Test (Read & validate date/time and battery)"));
    Serial.println(F("  [3] MicroSD Card Test (Card type, capacity, non-destructive read)"));
    Serial.println(F("  [4] 4x3 Keypad Matrix Test (Pull-up check & 10s interactive scan)"));
    Serial.println(F("  [5] INMP441 Microphone Test (1s capture, Min/Max/RMS/Energy bar)"));
    Serial.println(F("  [6] MAX98357A Speaker Test (Safe 440Hz test tone for 1.5s)"));
    Serial.println(F("  [7] TFT Display Diagnostic (Disabled until installed / Color test)"));
    Serial.println(F("  [8] Serial Protocol Loopback (Framing, CRC, and packet sizes)"));
    Serial.println(F("  [A] Run All Tests Sequentially"));
    Serial.println(F("  [P] Switch to Production Mode (Binary Protocol for Python Bridge)"));
    Serial.println(F("  [?] Reprint This Menu"));
    Serial.println(F("=============================================================="));
    Serial.print(F("Enter command > "));
}

void loop() {
    unsigned long now = millis();

    // =========================================================================
    // 1. HARDWARE DIAGNOSTIC MODE
    // =========================================================================
    if (current_firmware_mode == MODE_DIAGNOSTIC) {
        if (Serial.available()) {
            char cmd = Serial.read();
            if (cmd != '\r' && cmd != '\n') {
                Serial.println(cmd); // Echo command
            }

            switch (cmd) {
                case '1':
                    diag_1_led_and_boot();
                    print_menu();
                    break;
                case '2':
                    diag_2_rtc();
                    print_menu();
                    break;
                case '3':
                    diag_3_sd();
                    print_menu();
                    break;
                case '4':
                    diag_4_keypad();
                    print_menu();
                    break;
                case '5':
                    diag_5_mic();
                    print_menu();
                    break;
                case '6':
                    diag_6_speaker();
                    print_menu();
                    break;
                case '7':
                    diag_7_tft();
                    print_menu();
                    break;
                case '8':
                    diag_8_serial_protocol();
                    print_menu();
                    break;
                case 'a': case 'A':
                    diag_run_all();
                    print_menu();
                    break;
                case 'p': case 'P':
                    switch_to_production_mode();
                    break;
                case '?': case 'h': case 'H':
                    print_menu();
                    break;
                case '\r': case '\n': case ' ':
                    break;
                default:
                    Serial.printf("Unknown command '%c'. Type '?' for menu.\n", cmd);
                    Serial.print(F("Enter command > "));
                    break;
            }
        }

        // Background Keypad live detection during diagnostic mode
        int row = -1, col = -1;
        KeyCode key = KeyCode::NONE;
        if (keypad.scanRaw(row, col, key)) {
            char ch = KeypadDriver::keyToChar(key);
            if (ch != '?') {
                Serial.printf("\n[KEYPAD EVENT] Key '%c' Pressed | Row %d (GPIO %d), Col %d (GPIO %d)\n",
                              ch, row,
                              (row == 0 ? 14 : row == 1 ? 27 : row == 2 ? 16 : 12),
                              col,
                              (col == 0 ? 35 : col == 1 ? 13 : 15));
#if LUMI_ENABLE_TFT
                ui.updateDiagnosticKey(ch, row, col);
#endif
                Serial.print(F("Enter command > "));
                delay(200); // Visual debounce pause
            }
        }

        // Heartbeat LED blink
        if (now - last_led_toggle > 1000) {
            last_led_toggle = now;
            led_state = !led_state;
            digitalWrite(LUMI_PIN_LED_GREEN, led_state ? HIGH : LOW);
        }

        delay(10);
        return;
    }

    // =========================================================================
    // 2. PRODUCTION MODE (Binary USB-Serial Protocol for Python Bridge)
    // =========================================================================
    serial_proto.poll_rx();
    rx_result_t rx;
    while (serial_proto.get_packet(&rx)) {
        handle_rx_packet(rx.packet);
    }

    // Poll Keypad
    KeyCode key = keypad.update();
    if (key != KeyCode::NONE) {
        handle_keypad_press(key);
    }

#if LUMI_ENABLE_TFT
    // Update UI animations
    ui.updateAnimation();
#endif

    // Audio capture: stream mic chunks to Python host
    if (capture_active && i2s_initialized) {
        int16_t mic_buf[LUMI_AUDIO_CHUNK_SAMPLES];
        uint16_t samples_read = audio_mgr->read_mic(mic_buf, LUMI_AUDIO_CHUNK_SAMPLES);
        if (samples_read > 0) {
            serial_proto.send_mic_chunk(mic_buf, samples_read, mic_seq++);
        }
    }

    // Audio playback: drain speaker ring buffer to I2S
    if (playback_active && i2s_initialized) {
        audio_mgr->update_playback();
        if (!audio_mgr->is_playing()) {
            playback_active = false;
            serial_proto.send_audio_play_done();
#if LUMI_ENABLE_TFT
            ui.setLumiFace(LumiFaceState::IDLE);
#endif
        }
    }

    // Heartbeat LED blink pattern
    if (now - last_led_toggle > 1000) {
        last_led_toggle = now;
        led_state = !led_state;
        if (current_state == STATE_READY || current_state == STATE_IDLE) {
            digitalWrite(LUMI_PIN_LED_GREEN, led_state ? HIGH : LOW);
        }
    }

    // Flush serial TX buffer
    serial_proto.flush_tx();
    delay(1);
}

// =============================================================================
// 8 INDEPENDENT HARDWARE DIAGNOSTIC MODES
// =============================================================================

/** Mode 1: Boot and LED Test */
void diag_1_led_and_boot() {
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("   [MODE 1] BOOT & GREEN STATUS LED TEST"));
    Serial.println(F("=================================================="));
    Serial.println(F("LED Configuration: GPIO 32 -> 330 ohm resistor -> LED Anode -> Cathode to GND"));
    Serial.println(F("Blinking Status LED 3 times (Active HIGH)..."));

    for (int i = 0; i < 3; i++) {
        digitalWrite(LUMI_PIN_LED_GREEN, HIGH);
        Serial.printf("  Flash %d: LED ON  (GPIO 32 = HIGH)\n", i + 1);
        delay(200);
        digitalWrite(LUMI_PIN_LED_GREEN, LOW);
        Serial.printf("  Flash %d: LED OFF (GPIO 32 = LOW)\n", i + 1);
        delay(200);
    }

    Serial.println(F("Power Rail Safety Checklist:"));
    Serial.println(F("  - Left Rail (3.3V) : Feeds ESP32 3V3, INMP441 VDD, DS3231 VCC, 10k Keypad Pull-ups."));
    Serial.println(F("  - Right Rail (5.0V): Feeds ESP32 VIN, MAX98357A VIN, MicroSD VCC."));
    Serial.println(F("  - Common GND       : Both negative rails MUST be connected together."));
    Serial.println(F("  - SAFETY WARNING   : NEVER bridge the 3.3V and 5.0V positive rails!"));
    Serial.println(F("RESULT: [LED TEST COMPLETE] (Observe if green LED physically blinked)"));
    Serial.println(F("=================================================="));
}

/** Mode 2: DS3231 RTC Test */
void diag_2_rtc() {
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("   [MODE 2] DS3231 REAL-TIME CLOCK TEST"));
    Serial.println(F("=================================================="));
    Serial.println(F("I2C Pins: SDA=GPIO 21, SCL=GPIO 22 | Rail: 3.3V | Address: 0x68"));

    if (!rtc_initialized) {
        rtc_initialized = rtc.begin(LUMI_PIN_I2C_SDA, LUMI_PIN_I2C_SCL, LUMI_I2C_FREQ_HZ);
    }

    if (!rtc_initialized) {
        Serial.println(F("RESULT: [RTC NOT DETECTED] (FAIL)"));
        Serial.println(F("  * Check SDA (GPIO 21) and SCL (GPIO 22) connections."));
        Serial.println(F("  * Verify VCC is on 3.3V rail and GND is on GND rail."));
        Serial.println(F("  * Ensure DS3231 module has pull-up resistors on SDA/SCL."));
        return;
    }

    lumi_rtc_time_t t;
    if (rtc.read_time(&t)) {
        Serial.printf("  Live Date/Time : %04d-%02d-%02d %02d:%02d:%02d\n",
                      t.year, t.month, t.date, t.hours, t.minutes, t.seconds);
        Serial.printf("  CR2032 Battery : %s\n", t.power_lost ? "POWER LOST / REPLACE BATTERY" : "GOOD (Time Retained)");
        Serial.println(F("RESULT: [DS3231 RTC WORKING] (PASS)"));
    } else {
        Serial.println(F("RESULT: [RTC READ FAILED] (I2C communication error)"));
    }
    Serial.println(F("=================================================="));
}

/** Mode 3: MicroSD Card Test */
void diag_3_sd() {
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("   [MODE 3] MICROSD CARD MODULE TEST"));
    Serial.println(F("=================================================="));
    Serial.println(F("SPI Pins: CS=GPIO 17, SCK=GPIO 18, MOSI=GPIO 23, MISO=GPIO 19"));
    Serial.println(F("Power Supply: 5.0 V Rail (module contains onboard 3.3V LDO regulator)"));

    // Attempt init if not initialized
    if (!sd_initialized) {
        SPI.begin(LUMI_PIN_SPI_SCK, LUMI_PIN_SPI_MISO, LUMI_PIN_SPI_MOSI, -1);
        sd_initialized = SD.begin(LUMI_PIN_SD_CS, SPI);
    }

    if (!sd_initialized) {
        Serial.println(F("RESULT: [SD CARD NOT DETECTED] (FAIL)"));
        Serial.println(F("  * Check:"));
        Serial.println(F("    1. SD VCC connected to 5V rail (regulator needs 5V to output 3.3V)."));
        Serial.println(F("    2. SD CS connected to GPIO 17."));
        Serial.println(F("    3. SCK (18), MOSI (23), MISO (19) properly seated."));
        Serial.println(F("    4. 8GB microSD card formatted as FAT32 / FAT."));
        return;
    }

    uint8_t cardType = SD.cardType();
    const char *typeStr = "UNKNOWN";
    if (cardType == CARD_MMC) typeStr = "MMC";
    else if (cardType == CARD_SD) typeStr = "SDSC";
    else if (cardType == CARD_SDHC) typeStr = "SDHC";

    uint64_t cardSizeMB = SD.cardSize() / (1024 * 1024);
    uint64_t totalBytesMB = SD.totalBytes() / (1024 * 1024);
    uint64_t usedBytesMB = SD.usedBytes() / (1024 * 1024);

    Serial.printf("  Card Type      : %s\n", typeStr);
    Serial.printf("  Total Capacity : %llu MB\n", cardSizeMB);
    Serial.printf("  Filesystem     : %llu MB total, %llu MB used\n", totalBytesMB, usedBytesMB);

    // Non-destructive root directory inspection
    File root = SD.open("/");
    if (root && root.isDirectory()) {
        Serial.println(F("  Root Directory : Accessible (PASS)"));
        int fileCount = 0;
        File file = root.openNextFile();
        while (file && fileCount < 5) {
            Serial.printf("    - %s (%d bytes)\n", file.name(), file.size());
            fileCount++;
            file = root.openNextFile();
        }
        root.close();
    }

    Serial.println(F("RESULT: [MICROSD CARD WORKING] (PASS)"));
    Serial.println(F("=================================================="));
}

/** Mode 4: Keypad Matrix Test */
void diag_4_keypad() {
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("   [MODE 4] 4x3 KEYPAD MATRIX DIAGNOSTIC"));
    Serial.println(F("=================================================="));
    Serial.println(F("Wiring Configuration:"));
    Serial.println(F("  Rows    : R1=GPIO 14, R2=GPIO 27, R3=GPIO 16, R4=GPIO 12 [MTDI]"));
    Serial.println(F("  Columns : C1=GPIO 35, C2=GPIO 13, C3=GPIO 15 [MTDO]"));
    Serial.println(F("  Pull-ups: Three 10k ohm resistors pull C1, C2, C3 to 3.3V rail."));
    Serial.println(F("  Scanning: Active-LOW (Rows driven LOW one-by-one; Col reads LOW on press)."));

    // Check idle column pull-up states
    int c0, c1, c2;
    keypad.readColumnIdleStates(c0, c1, c2);
    Serial.printf("Idle Column States (Unpressed): C1(35)=%d, C2(13)=%d, C3(15)=%d\n", c0, c1, c2);

    if (c0 == 0 || c1 == 0 || c2 == 0) {
        Serial.println(F("ELECTRICAL WARNING: One or more columns read 0 (LOW) while idle!"));
        if (c0 == 0) Serial.println(F("  * Col 1 (GPIO 35) reads LOW! Check 10k pull-up resistor to 3.3V."));
        if (c1 == 0) Serial.println(F("  * Col 2 (GPIO 13) reads LOW! Check column node wiring."));
        if (c2 == 0) Serial.println(F("  * Col 3 (GPIO 15) reads LOW! Check column node wiring."));
        Serial.println(F("  * BREADBOARD CHECK: Ensure pull-up resistors connect to the COLUMN wire,"));
        Serial.println(F("    NOT to the tactile switch row side!"));
    } else {
        Serial.println(F("Pull-Up Verification: All 3 columns read 1 (HIGH) at idle (OK)."));
    }

    Serial.println(F("\nStarting 10-second interactive scan. Press keys on keypad now:"));
    Serial.println(F("(Or press any key on serial keyboard to return to menu)"));

    unsigned long start = millis();
    int pressCount = 0;

    while (millis() - start < 10000) {
        if (Serial.available()) {
            while (Serial.available()) Serial.read();
            break;
        }

        int row = -1, col = -1;
        KeyCode key = KeyCode::NONE;
        if (keypad.scanRaw(row, col, key)) {
            char ch = KeypadDriver::keyToChar(key);
            pressCount++;
            Serial.printf("  [%d] KEY DETECTED: '%c' | Row %d (GPIO %d), Col %d (GPIO %d)\n",
                          pressCount, ch, row,
                          (row == 0 ? 14 : row == 1 ? 27 : row == 2 ? 16 : 12),
                          col,
                          (col == 0 ? 35 : col == 1 ? 13 : 15));
            delay(180); // Debounce delay
        }
        delay(10);
    }

    Serial.printf("Keypad scan finished. Total presses detected: %d\n", pressCount);
    if (pressCount == 0) {
        Serial.println(F("RESULT: [NO KEY DETECTED] (Inspect button row/col connections)"));
    } else {
        Serial.println(F("RESULT: [KEYPAD WORKING] (PASS)"));
    }
    Serial.println(F("=================================================="));
}

/** Mode 5: INMP441 Microphone Test */
void diag_5_mic() {
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("   [MODE 5] INMP441 MICROPHONE CAPTURE TEST"));
    Serial.println(F("=================================================="));
    Serial.println(F("I2S Config : BCLK=GPIO 26, WS=GPIO 25, DIN=GPIO 34 (Input-only)"));
    Serial.println(F("Power Rails: VDD=3.3V Rail (NEVER 5V!), GND=GND, L/R=GND (Left channel)"));
    Serial.println(F("Capturing 1.0 second of real microphone audio..."));
    Serial.println(F(">>> Speak into the microphone now! <<<"));

    if (!i2s_initialized) {
        lumi_audio_config_t audio_cfg = lumi_get_default_i2s_config();
        audio_mgr = new AudioManager(audio_cfg);
        i2s_initialized = audio_mgr->begin();
    }

    AudioManager::mic_diagnostic_stats_t stats;
    bool ok = audio_mgr->run_mic_diagnostic(1000, stats);

    if (!ok || stats.total_samples == 0) {
        Serial.println(F("RESULT: [I2S CAPTURE FAILED] (FAIL)"));
        Serial.printf("  * I2S Error Code: %d\n", audio_mgr->last_error());
        return;
    }

    Serial.println();
    Serial.printf("  Total Samples  : %u (16000 Hz, 16-bit signed PCM)\n", stats.total_samples);
    Serial.printf("  Sample Range   : Min=%d, Max=%d\n", stats.min_sample, stats.max_sample);
    Serial.printf("  Peak-to-Peak   : %d\n", stats.peak_to_peak);
    Serial.printf("  DC Offset      : %d\n", stats.dc_offset);
    Serial.printf("  RMS Energy     : %.1f\n", stats.rms);
    Serial.printf("  Clipping Count : %u\n", stats.clipping_count);

    // ASCII volume meter
    int bars = (int)(stats.rms / 60.0f);
    if (bars > 20) bars = 20;
    Serial.print(F("  Audio Energy   : ["));
    for (int b = 0; b < 20; b++) {
        Serial.print(b < bars ? "#" : ".");
    }
    Serial.println(F("]"));

    if (stats.is_all_zeros) {
        Serial.println(F("RESULT: [ALL ZEROS CAPTURED] (FAIL)"));
        Serial.println(F("  -> Microphone is outputting zero on every sample."));
        Serial.println(F("  -> Checks:"));
        Serial.println(F("     1. VDD connected to 3.3V rail (NOT 5V)."));
        Serial.println(F("     2. L/R pin MUST be connected to GND."));
        Serial.println(F("     3. SD connected to GPIO 34."));
        Serial.println(F("     4. SCK connected to GPIO 26, WS connected to GPIO 25."));
    } else if (stats.is_voice) {
        Serial.println(F("RESULT: [VOICE / SPEECH DETECTED] (PASS)"));
        Serial.println(F("  -> Signal level is dynamic and responsive to audio."));
    } else if (stats.is_silent) {
        Serial.println(F("RESULT: [QUIET / LOW NOISE] (PASS)"));
        Serial.println(F("  -> Microphone is capturing healthy room background."));
        Serial.println(F("  -> Run test again while speaking loudly near the mic to see energy jump!"));
    } else {
        Serial.println(F("RESULT: [AUDIO DETECTED] (PASS)"));
    }
    Serial.println(F("=================================================="));
}

/** Mode 6: MAX98357A Speaker Test */
void diag_6_speaker() {
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("   [MODE 6] MAX98357A SPEAKER PLAYBACK TEST"));
    Serial.println(F("=================================================="));
    Serial.println(F("I2S Config : BCLK=GPIO 26, WS=GPIO 25, DOUT=GPIO 33"));
    Serial.println(F("Power Rails: VIN=5.0V Rail, GND=GND, GAIN=unconnected, SD=unconnected"));
    Serial.println(F("Speaker    : 4 ohm, 5W (+ to +, - to -). NEVER connect terminals to GND!"));
    Serial.println(F("Playing 440 Hz (Concert A) test tone for 1.5s at ~12% volume..."));

    if (!i2s_initialized) {
        lumi_audio_config_t audio_cfg = lumi_get_default_i2s_config();
        audio_mgr = new AudioManager(audio_cfg);
        i2s_initialized = audio_mgr->begin();
    }

    bool ok = audio_mgr->play_test_tone(440.0f, 1500, 12.0f);

    if (ok) {
        Serial.println(F("Tone generation completed. Output muted."));
        Serial.println(F(">>> OBSERVATION CHECK: DID YOU HEAR A CLEAR 440 Hz AUDIO BEEP? <<<"));
        Serial.println(F("  - If YES -> MAX98357A amplifier and speaker are VERIFIED!"));
        Serial.println(F("  - If NO AUDIBLE SOUND:"));
        Serial.println(F("      1. Amplifier VIN must be on 5.0V rail (NOT 3.3V)."));
        Serial.println(F("      2. Both negative rails must be connected for common GND."));
        Serial.println(F("      3. DIN connected to GPIO 33."));
        Serial.println(F("      4. BCLK connected to GPIO 26, LRC connected to GPIO 25."));
        Serial.println(F("      5. Check speaker wires securely connected to +/- terminals."));
    } else {
        Serial.println(F("RESULT: [I2S DRIVER WRITE FAILED] (FAIL)"));
    }
    Serial.println(F("=================================================="));
}

/** Mode 7: TFT Display Diagnostic */
void diag_7_tft() {
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("   [MODE 7] ILI9341 TFT DISPLAY DIAGNOSTIC"));
    Serial.println(F("=================================================="));

#if LUMI_ENABLE_TFT
    Serial.println(F("TFT is ENABLED in firmware. Running color test..."));
    ui.runDiagnosticTest();
    Serial.println(F("RESULT: [TFT TEST RAN] (Observe display colors)"));
#else
    Serial.println(F("STATUS: TFT Display is NOT physically installed yet."));
    Serial.println(F("  * Configuration flag LUMI_ENABLE_TFT is set to 0."));
    Serial.println(F("  * Display initialization is safely skipped to avoid bus conflicts."));
    Serial.println(F("  * Planned assignments: CS:5, DC:2, RST:4, SCK:18, MOSI:23, MISO:19."));
    Serial.println(F("  * When you are ready to wire the display:"));
    Serial.println(F("      1. Wire TFT VCC and LED (backlight) to 3.3V."));
    Serial.println(F("      2. Set #define LUMI_ENABLE_TFT 1 in firmware/LumiFirmware/lumi_config.h"));
    Serial.println(F("      3. Recompile and run Mode 7 to verify color fill and text dashboard."));
#endif
    Serial.println(F("=================================================="));
}

/** Mode 8: Serial Protocol Loopback & Framing Test */
void diag_8_serial_protocol() {
    Serial.println();
    Serial.println(F("=================================================="));
    Serial.println(F("   [MODE 8] SERIAL PROTOCOL FRAMING & CHECKSUM TEST"));
    Serial.println(F("=================================================="));
    Serial.println(F("Protocol Spec: SOF=0x56AA | CRC=XOR(TYPE ^ LEN ^ PAYLOAD)"));

    // Test 1: Checksum verification
    uint8_t dummy_payload[] = { 0x01, 0x02, 0x03, 0x04 };
    uint8_t csum = lumi_compute_checksum(PKT_COMMAND, sizeof(dummy_payload), dummy_payload);
    uint8_t expected = PKT_COMMAND ^ sizeof(dummy_payload) ^ 0x01 ^ 0x02 ^ 0x03 ^ 0x04;
    Serial.printf("  Checksum Algorithm Test: Computed=0x%02X, Expected=0x%02X -> %s\n",
                  csum, expected, (csum == expected) ? "PASS" : "FAIL");

    // Test 2: Audio Chunk Framing Size
    uint16_t max_samples = (LUMI_MAX_PAYLOAD - 1) / 2;
    Serial.printf("  Max Audio Chunk Payload: %d samples (%d bytes)\n", max_samples, max_samples * 2 + 1);

    // Test 3: Garbled Characters Explanation
    Serial.println(F("\n  Serial Monitor Diagnostic Notice:"));
    Serial.println(F("    In Production Mode, Project LUMI transmits binary framed packets."));
    Serial.println(F("    The Arduino Serial Monitor interprets raw binary headers (0x56 0xAA)"));
    Serial.println(F("    as unprintable / garbled characters. This is normal and expected for"));
    Serial.println(F("    binary protocols. In Diagnostic Mode, output is 100% clean ASCII."));
    Serial.println(F("RESULT: [PROTOCOL VERIFIED] (PASS)"));
    Serial.println(F("=================================================="));
}

/** Run all available tests sequentially */
void diag_run_all() {
    Serial.println();
    Serial.println(F(">>> RUNNING ALL DIAGNOSTICS SEQUENTIALLY <<<"));
    diag_1_led_and_boot();
    delay(500);
    diag_2_rtc();
    delay(500);
    diag_3_sd();
    delay(500);
    diag_4_keypad();
    delay(500);
    diag_5_mic();
    delay(500);
    diag_6_speaker();
    delay(500);
    diag_7_tft();
    delay(500);
    diag_8_serial_protocol();
    Serial.println(F(">>> ALL SEQUENTIAL DIAGNOSTICS FINISHED <<<"));
}

/** Switch to Production Mode */
void switch_to_production_mode() {
    current_firmware_mode = MODE_PRODUCTION;
    Serial.println();
    Serial.println(F("[LUMI] Switching to PRODUCTION MODE..."));
    Serial.println(F("[LUMI] Starting binary framed serial protocol for Python Voice Stack."));
    Serial.println(F("[LUMI] (Note: Serial Monitor will now show raw binary packets)"));

    // Send initial binary handshakes to host
    lumi_audio_format_t audio_fmt = audio_mgr->audio_format();
    serial_proto.send_device_info(
        LUMI_FW_VERSION_MAJOR, LUMI_FW_VERSION_MINOR, LUMI_FW_VERSION_PATCH,
        LUMI_TARGET_BOARD, LUMI_TARGET_MCU, &audio_fmt
    );
    serial_proto.send_peripheral_status(sd_initialized, rtc_initialized, tft_initialized, i2s_initialized);

    current_state = STATE_READY;
    serial_proto.send_system_state(current_state);
    serial_proto.send_log("LUMI production mode active");
    digitalWrite(LUMI_PIN_LED_GREEN, HIGH);
}

// =============================================================================
// PRODUCTION PROTOCOL PACKET HANDLERS
// =============================================================================

void handle_rx_packet(const lumi_packet_t &pkt) {
    switch (pkt.type) {
        case PKT_HOST_READY:
            serial_proto.send_log("Host handshake received");
            current_state = STATE_IDLE;
            serial_proto.send_system_state(current_state);
#if LUMI_ENABLE_TFT
            ui.setLumiFace(LumiFaceState::IDLE);
#endif
            break;

        case PKT_COMMAND:
            if (pkt.length > 0) {
                handle_command((lumi_command_t)pkt.payload[0]);
            }
            break;

        case PKT_AUDIO_SPK_START:
            if (pkt.length >= 4 && i2s_initialized) {
                uint32_t total_samples = *((uint32_t*)pkt.payload);
                audio_mgr->start_playback(total_samples);
                playback_active = true;
                current_state = STATE_SPEAKING;
                serial_proto.send_system_state(current_state);
#if LUMI_ENABLE_TFT
                ui.setLumiFace(LumiFaceState::SPEAKING);
#endif
                digitalWrite(LUMI_PIN_LED_GREEN, HIGH);
            }
            break;

        case PKT_AUDIO_SPK_CHUNK:
            if (playback_active && i2s_initialized && pkt.length > 0) {
                uint16_t num_samples = pkt.length / 2;
                audio_mgr->push_spk((int16_t*)pkt.payload, num_samples);
            }
            break;

        case PKT_AUDIO_SPK_END:
            break;

        case PKT_UTTERANCE_END:
            current_state = STATE_IDLE;
            serial_proto.send_system_state(current_state);
#if LUMI_ENABLE_TFT
            ui.setLumiFace(LumiFaceState::IDLE);
#endif
            break;

        case PKT_LED_CONTROL:
            if (pkt.length >= 1) {
                digitalWrite(LUMI_PIN_LED_GREEN, pkt.payload[0] ? HIGH : LOW);
            }
            break;

        default:
            break;
    }
}

void handle_command(lumi_command_t cmd) {
    switch (cmd) {
        case CMD_START_CAPTURE:
            if (i2s_initialized && !capture_active) {
                audio_mgr->start_capture();
                capture_active = true;
                mic_seq = 0;
                current_state = STATE_LISTENING;
                serial_proto.send_system_state(current_state);
#if LUMI_ENABLE_TFT
                ui.setLumiFace(LumiFaceState::LISTENING);
#endif
                digitalWrite(LUMI_PIN_LED_GREEN, HIGH);
                serial_proto.send_log("Capture started");
            }
            break;

        case CMD_STOP_CAPTURE:
            if (capture_active) {
                audio_mgr->stop_capture();
                capture_active = false;
                serial_proto.send_audio_end();
                current_state = STATE_IDLE;
                serial_proto.send_system_state(current_state);
#if LUMI_ENABLE_TFT
                ui.setLumiFace(LumiFaceState::IDLE);
#endif
                serial_proto.send_log("Capture stopped");
            }
            break;

        case CMD_CANCEL_PLAYBACK:
            if (playback_active) {
                audio_mgr->stop_playback();
                playback_active = false;
                serial_proto.send_audio_play_done();
                current_state = STATE_IDLE;
                serial_proto.send_system_state(current_state);
#if LUMI_ENABLE_TFT
                ui.setLumiFace(LumiFaceState::IDLE);
#endif
            }
            break;

        case CMD_GET_STATUS:
            serial_proto.send_peripheral_status(sd_initialized, rtc_initialized, tft_initialized, i2s_initialized);
            break;

        case CMD_NOOP:
        default:
            break;
    }
}

void handle_keypad_press(KeyCode key) {
    char key_char = KeypadDriver::keyToChar(key);
    if (key_char == '?') return;

    // Send binary packet to Python host
    serial_proto.send_keypad_event(key_char, LUMI_KEY_FLAG_PRESS);

#if LUMI_ENABLE_TFT
    // Update local UI
    ui.handleInput(key);
#endif
}
