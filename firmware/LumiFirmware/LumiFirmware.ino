/**
 * @file LumiFirmware.ino
 * @brief Main entry point for Project LUMI ESP32 firmware.
 *
 * Hardware: ESP32 DevKit V1 / ESP32-WROOM-32
 * Architecture: Arduino framework over ESP-IDF
 *
 * Peripherals:
 *   - I2S0: INMP441 microphone + MAX98357A amplifier (full-duplex)
 *   - SPI: ILI9341 TFT display + MicroSD card
 *   - I2C: DS3231 RTC
 *   - GPIO: 4x3 keypad matrix, status LED
 *   - USB: Serial protocol for Python voice stack communication
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
#define LUMI_FW_VERSION_MINOR  0
#define LUMI_FW_VERSION_PATCH  0

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

// System state
lumi_system_state_t current_state = STATE_BOOT;
bool capture_active = false;
bool playback_active = false;
uint32_t last_heartbeat_ms = 0;
uint8_t mic_seq = 0;

// LED blink pattern state
unsigned long last_led_toggle = 0;
bool led_state = false;

// Forward declarations
void handle_rx_packet(const lumi_packet_t &pkt);
void handle_command(lumi_command_t cmd);
void handle_keypad_press(KeyCode key);

void setup() {
    // 1. Set safe GPIO states
    pinMode(LUMI_PIN_LED_GREEN, OUTPUT);
    digitalWrite(LUMI_PIN_LED_GREEN, LOW);

    // 2. Initialize USB serial and protocol
    serial_proto.begin(115200);
    delay(500);  // Allow USB CDC to stabilize
    serial_proto.send_log("LUMI firmware starting...");

    // 3. Initialize I2C and check RTC
    rtc_initialized = rtc.begin(LUMI_PIN_I2C_SDA, LUMI_PIN_I2C_SCL, LUMI_I2C_FREQ_HZ);
    if (rtc_initialized) {
        lumi_rtc_time_t t;
        if (rtc.read_time(&t)) {
            char buf[64];
            snprintf(buf, sizeof(buf), "RTC OK: %04d-%02d-%02d %02d:%02d:%02d",
                     t.year, t.month, t.date, t.hours, t.minutes, t.seconds);
            serial_proto.send_log(buf);
        } else {
            serial_proto.send_log("RTC: read failed");
        }
    } else {
        serial_proto.send_log("RTC: not detected");
    }

    // 4. Initialize SPI and SD card
    SPI.begin(LUMI_PIN_SPI_SCK, LUMI_PIN_SPI_MISO, LUMI_PIN_SPI_MOSI, -1);
    sd_initialized = SD.begin(LUMI_PIN_SD_CS, SPI);
    if (sd_initialized) {
        serial_proto.send_log("SD card: initialized");
    } else {
        serial_proto.send_log("SD card: not detected or init failed");
    }

    // 5. Initialize keypad
    keypad.begin();
    serial_proto.send_log("Keypad: initialized");

    // 6. Initialize TFT display
    ui.begin();
    tft_initialized = true;
    ui.setScreenState(ScreenState::HOME);
    ui.setLumiFace(LumiFaceState::IDLE);
    serial_proto.send_log("TFT: initialized (ILI9341 320x240)");

    // 7. Initialize I2S audio
    lumi_audio_config_t audio_cfg = lumi_get_default_i2s_config();
    audio_mgr = new AudioManager(audio_cfg);
    i2s_initialized = audio_mgr->begin();
    if (i2s_initialized) {
        serial_proto.send_log("I2S audio: initialized");
    } else {
        char err_buf[48];
        snprintf(err_buf, sizeof(err_buf), "I2S init failed: %d", audio_mgr->last_error());
        serial_proto.send_log(err_buf);
    }

    // 8. Send device info packet
    lumi_audio_format_t audio_fmt = audio_mgr->audio_format();
    serial_proto.send_device_info(
        LUMI_FW_VERSION_MAJOR, LUMI_FW_VERSION_MINOR, LUMI_FW_VERSION_PATCH,
        LUMI_TARGET_BOARD, LUMI_TARGET_MCU, &audio_fmt
    );

    // 9. Send peripheral status
    serial_proto.send_peripheral_status(sd_initialized, rtc_initialized, tft_initialized, i2s_initialized);

    // 10. Transition to READY
    current_state = STATE_READY;
    serial_proto.send_system_state(current_state);
    serial_proto.send_log("LUMI ready");
    digitalWrite(LUMI_PIN_LED_GREEN, HIGH);

    last_heartbeat_ms = millis();
}

void loop() {
    unsigned long now = millis();

    // Poll serial protocol for incoming packets
    serial_proto.poll_rx();
    rx_result_t rx;
    while (serial_proto.get_packet(&rx)) {
        handle_rx_packet(rx.packet);
    }

    // Poll keypad
    KeyCode key = keypad.update();
    if (key != KeyCode::NONE) {
        handle_keypad_press(key);
    }

    // Update UI animations
    ui.updateAnimation();

    // Audio capture: send mic chunks if capturing
    if (capture_active && i2s_initialized) {
        int16_t mic_buf[LUMI_AUDIO_CHUNK_SAMPLES];
        uint16_t samples_read = audio_mgr->read_mic(mic_buf, LUMI_AUDIO_CHUNK_SAMPLES);
        if (samples_read > 0) {
            serial_proto.send_mic_chunk(mic_buf, samples_read, mic_seq++);
        }
    }

    // Audio playback: drain speaker ring buffer
    if (playback_active && i2s_initialized) {
        audio_mgr->update_playback();
        if (!audio_mgr->is_playing()) {
            playback_active = false;
            serial_proto.send_audio_play_done();
            ui.setLumiFace(LumiFaceState::IDLE);
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

    // Small yield to allow FreeRTOS idle task to run
    delay(1);
}

void handle_rx_packet(const lumi_packet_t &pkt) {
    switch (pkt.type) {
        case PKT_HOST_READY:
            serial_proto.send_log("Host handshake received");
            current_state = STATE_IDLE;
            serial_proto.send_system_state(current_state);
            ui.setLumiFace(LumiFaceState::IDLE);
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
                ui.setLumiFace(LumiFaceState::SPEAKING);
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
            if (playback_active) {
                // Playback will stop naturally when buffer drains
            }
            break;

        case PKT_UTTERANCE_END:
            // Python host finished speaking; return to idle listening
            current_state = STATE_IDLE;
            serial_proto.send_system_state(current_state);
            ui.setLumiFace(LumiFaceState::IDLE);
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
                ui.setLumiFace(LumiFaceState::LISTENING);
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
                ui.setLumiFace(LumiFaceState::IDLE);
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
                ui.setLumiFace(LumiFaceState::IDLE);
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
    // Convert KeyCode to character
    char key_char = '?';
    uint8_t flags = LUMI_KEY_FLAG_PRESS;

    switch (key) {
        case KeyCode::NUM_0: key_char = '0'; break;
        case KeyCode::NUM_1: key_char = '1'; break;
        case KeyCode::NUM_2: key_char = '2'; break;
        case KeyCode::NUM_3: key_char = '3'; break;
        case KeyCode::NUM_4: key_char = '4'; break;
        case KeyCode::NUM_5: key_char = '5'; break;
        case KeyCode::NUM_6: key_char = '6'; break;
        case KeyCode::NUM_7: key_char = '7'; break;
        case KeyCode::NUM_8: key_char = '8'; break;
        case KeyCode::NUM_9: key_char = '9'; break;
        case KeyCode::BTN_BACKWARD: key_char = '*'; break;
        case KeyCode::BTN_FORWARD: key_char = '#'; break;
        default: return;
    }

    // Send to Python host
    serial_proto.send_keypad_event(key_char, flags);

    // Update local UI
    ui.handleInput(key);
}
