/**
 * @file lumi_pins.h
 * @brief Authoritative ESP32 Hardware Pin Mapping & Safety Definitions for Project LUMI.
 *
 * Target Hardware:
 *   - Board: ESP32 DevKit V1 / ESP32-WROOM-32 (Standard 30-pin or 38-pin module)
 *   - No external GPIO expander is used. All peripherals connect directly to the ESP32.
 *
 * Wiring Checklist Specification:
 *   - Keypad: 4 Rows (GPIO 14, 27, 16, 12), 3 Columns (GPIO 35, 13, 15)
 *   - Status LED: Green LED on GPIO 32 (Active HIGH: HIGH = ON, LOW = OFF)
 *   - I2S Audio: Shared Clock full-duplex arrangement
 *       BCLK: GPIO 26
 *       WS / LRCLK: GPIO 25
 *       Mic Data (INMP441 SD): GPIO 34 (Input-only GPI)
 *       Amp Data (MAX98357A DIN): GPIO 33
 *   - SD Card (SPI):
 *       SCK: GPIO 18, MOSI: GPIO 23, MISO: GPIO 19, CS: GPIO 17
 *   - Real-Time Clock (RTC, DS3231 over I2C):
 *       SDA: GPIO 21, SCL: GPIO 22
 *   - TFT Display (ILI9341 SPI control):
 *       CS: GPIO 5, DC: GPIO 2, RESET: GPIO 4
 *       (Shares SPI bus: SCK 18, MOSI 23, MISO 19)
 *       NOTE: Only use main 14-pin header. Do NOT use aux 4-pin header for SD!
 *
 * HARDWARE SAFETY AND STRAPPING PIN REVIEWS:
 * ==========================================
 * 1. Strapping Pins (Boot Behavior Critical):
 *    - GPIO 12 (MTDI): Flash Voltage Selection (3.3V vs 1.8V).
 *      * Connected to Keypad Row 3.
 *      * MUST NOT be pulled HIGH during boot/reset! If pulled HIGH, flash voltage
 *        switches to 1.8V, preventing boot from 3.3V SPI flash (causes bootloop).
 *      * Firmware matrix scan MUST idle rows LOW or High-Z, and ensure Keypad
 *        Row 3 is never held HIGH during power-on reset.
 *    - GPIO 15 (MTDO): Boot Log Output & JTAG.
 *      * Connected to Keypad Column 2.
 *      * Must be HIGH during boot for normal UART ROM boot logging.
 *    - GPIO 2: Download Boot Mode.
 *      * Connected to TFT DC (Data/Command).
 *      * Must be LOW or floating during download boot. If held HIGH, prevents
 *        UART flashing mode.
 *
 * 2. Input-Only Pin (GPI 34-39):
 *    - GPIO 35 is an input-only pin without internal pull-up or pull-down resistors!
 *    - Connected to Keypad Column 0.
 *    - An EXTERNAL 10k ohm physical pull-down resistor to GND is MANDATORY on GPIO 35.
 *    - GPIO 34 is also input-only, which is completely valid for I2S Mic Data In.
 *
 * 3. SPI Bus Sharing & TFT MISO Troubleshooting:
 *    - SD Card and TFT share SCK (18), MOSI (23), and MISO (19).
 *    - Dedicated Chip Selects: SD Card uses GPIO 17, TFT uses GPIO 5.
 *    - TROUBLESHOOTING STEP: Many ILI9341 displays fail to tri-state MISO when CS
 *      is HIGH, disrupting SD card SPI communication. If SD card initialization fails,
 *      disconnect the TFT MISO wire (TFT is write-only in LUMI firmware).
 *
 * 4. Full-Duplex Shared Clock I2S:
 *    - INMP441 and MAX98357A share BCLK (26) and WS (25).
 *    - Both peripherals operate at 16,000 Hz, 32-bit slot width, standard Philips I2S.
 */

#ifndef LUMI_PINS_H
#define LUMI_PINS_H

#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ========================================================================== */
/* Target Architecture Definition                                             */
/* ========================================================================== */
#define LUMI_TARGET_BOARD              "ESP32-DevKit-V1"
#define LUMI_TARGET_MCU                "ESP32-WROOM-32"

/* ========================================================================== */
/* Keypad Matrix (4 Rows x 3 Columns)                                         */
/* ========================================================================== */
#define LUMI_PIN_KEYPAD_ROW_0          14  /* Keypad Row 0 (Keys: 1, 2, 3)    */
#define LUMI_PIN_KEYPAD_ROW_1          27  /* Keypad Row 1 (Keys: 4, 5, 6)    */
#define LUMI_PIN_KEYPAD_ROW_2          16  /* Keypad Row 2 (Keys: 7, 8, 9)    */
#define LUMI_PIN_KEYPAD_ROW_3          12  /* Keypad Row 3 (Keys: *, 0, #) [STRAPPING PIN: MTDI] */

#define LUMI_PIN_KEYPAD_COL_0          35  /* Keypad Col 0 [INPUT-ONLY: Requires ext 10k pull-down] */
#define LUMI_PIN_KEYPAD_COL_1          13  /* Keypad Col 1                    */
#define LUMI_PIN_KEYPAD_COL_2          15  /* Keypad Col 2 [STRAPPING PIN: MTDO] */

#define LUMI_KEYPAD_NUM_ROWS           4
#define LUMI_KEYPAD_NUM_COLS           3
#define LUMI_KEYPAD_DEBOUNCE_MS        20

/* ========================================================================== */
/* Status LED                                                                 */
/* ========================================================================== */
#define LUMI_PIN_LED_GREEN             32  /* Green Status LED                */
#define LUMI_LED_ACTIVE_LEVEL          1   /* 1 = Active HIGH (HIGH means ON) */

/* ========================================================================== */
/* I2S Full-Duplex Audio (Shared Clock)                                       */
/* ========================================================================== */
#define LUMI_PIN_I2S_BCLK              26  /* Shared Bit Clock (BCLK)         */
#define LUMI_PIN_I2S_WS                25  /* Shared Word Select / LRCLK      */
#define LUMI_PIN_I2S_MIC_DIN           34  /* INMP441 Microphone Data (Input) */
#define LUMI_PIN_I2S_AMP_DOUT          33  /* MAX98357A Amplifier Data (Out)  */

#define LUMI_I2S_SAMPLE_RATE_HZ        16000
#define LUMI_I2S_BITS_PER_SAMPLE       32  /* Standard 32-bit slot width      */
#define LUMI_I2S_PORT_NUM              0   /* ESP32 I2S Controller 0 (Full-Duplex) */

/* ========================================================================== */
/* Shared SPI Bus (SD Card & TFT Display)                                     */
/* ========================================================================== */
#define LUMI_PIN_SPI_SCK               18  /* Shared SPI Clock (SCK)          */
#define LUMI_PIN_SPI_MOSI              23  /* Shared SPI Master Out (MOSI)    */
#define LUMI_PIN_SPI_MISO              19  /* Shared SPI Master In (MISO)     */

/* SD Card SPI Control */
#define LUMI_PIN_SD_CS                 17  /* Dedicated SD Card Chip Select   */

/* TFT Display Control */
#define LUMI_PIN_TFT_CS                5   /* Dedicated TFT Display Chip Sel  */
#define LUMI_PIN_TFT_DC                2   /* TFT Data/Command [STRAPPING PIN]*/
#define LUMI_PIN_TFT_RESET             4   /* TFT Hardware Reset              */

/* ========================================================================== */
/* I2C Bus (DS3231 RTC)                                                       */
/* ========================================================================== */
#define LUMI_PIN_I2C_SDA               21  /* I2C Data (SDA)                  */
#define LUMI_PIN_I2C_SCL               22  /* I2C Clock (SCL)                 */
#define LUMI_I2C_FREQ_HZ               100000 /* 100 kHz standard mode        */
#define LUMI_I2C_PORT_NUM              0

/* ========================================================================== */
/* Keypad Matrix Configuration Arrays & Mode Enum                             */
/* ========================================================================== */
typedef enum {
    LUMI_KEYPAD_MODE_SHORTCUT = 0, /* Keys 0-6 trigger direct intents        */
    LUMI_KEYPAD_MODE_NUMERIC  = 1  /* Keys 0-9 enter numbers for educational quizzes */
} lumi_keypad_mode_t;

static const uint8_t LUMI_KEYPAD_ROW_PINS[LUMI_KEYPAD_NUM_ROWS] = {
    LUMI_PIN_KEYPAD_ROW_0,
    LUMI_PIN_KEYPAD_ROW_1,
    LUMI_PIN_KEYPAD_ROW_2,
    LUMI_PIN_KEYPAD_ROW_3
};

static const uint8_t LUMI_KEYPAD_COL_PINS[LUMI_KEYPAD_NUM_COLS] = {
    LUMI_PIN_KEYPAD_COL_0,
    LUMI_PIN_KEYPAD_COL_1,
    LUMI_PIN_KEYPAD_COL_2
};

static const char LUMI_KEYPAD_CHAR_MAP[LUMI_KEYPAD_NUM_ROWS][LUMI_KEYPAD_NUM_COLS] = {
    {'1', '2', '3'},
    {'4', '5', '6'},
    {'7', '8', '9'},
    {'*', '0', '#'}
};

#ifdef __cplusplus
}
#endif

#endif /* LUMI_PINS_H */
