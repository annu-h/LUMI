/**
 * @file lumi_pins.h
 * @brief Authoritative ESP32 Hardware Pin Mapping & Power Safety Definitions for Project LUMI.
 *
 * Target Hardware:
 *   - Board: ESP32 DevKit V1 / ESP32-WROOM-32 (Standard 30-pin or 38-pin module)
 *   - Framework: Arduino ESP32 Core 3.3.11 / ESP-IDF v5.x
 *
 * Power Rail Architecture:
 *   - Left Positive Rail:  3.3 V (fed from ESP32 3V3 pin)
 *   - Left Negative Rail:  GND (fed from ESP32 GND pin)
 *   - Right Positive Rail: 5.0 V (fed from ESP32 VIN / 5V pin via USB)
 *   - Right Negative Rail: GND (tied to Left Negative Rail for common ground)
 *   - SAFETY: The 3.3 V and 5.0 V positive rails MUST NEVER be connected together!
 *
 * Final Peripheral Pin Allocations:
 *   - Status LED: GPIO 32 (330 ohm resistor in series to GND, active HIGH)
 *   - 12-Button Keypad (4x3 Matrix):
 *       Rows (Outputs):    Row 1: GPIO 14, Row 2: GPIO 27, Row 3: GPIO 16, Row 4: GPIO 12 [MTDI]
 *       Columns (Inputs):  Col 1: GPIO 35, Col 2: GPIO 13, Col 3: GPIO 15 [MTDO]
 *       Pull-ups: 10k ohm resistors pull Columns to the 3.3 V rail (NEVER 5 V rail).
 *   - I2S Audio Hub (Full-Duplex Shared Clock):
 *       BCLK (Bit Clock):     GPIO 26 (Shared Mic SCK & Amp BCLK)
 *       WS / LRCLK:           GPIO 25 (Shared Mic WS & Amp LRC)
 *       Mic Data (INMP441):   GPIO 34 (Input-only GPI, L/R pin tied to GND for Left Channel)
 *       Amp Data (MAX98357A): GPIO 33 (Data Out to Amp DIN, powered by 5 V rail)
 *   - MicroSD Module (SPI Bus):
 *       SCK: GPIO 18, MOSI: GPIO 23, MISO: GPIO 19, CS: GPIO 17
 *       VCC: 5 V rail (breakout board with onboard 3.3V LDO regulator)
 *   - DS3231 RTC (I2C Bus):
 *       SDA: GPIO 21, SCL: GPIO 22, VCC: 3.3 V rail
 *   - ILI9341 TFT Display (SPI Bus):
 *       PLANNED FOR LATER / NOT INSTALLED YET. Disabled by default in firmware.
 *       CS: GPIO 5, DC: GPIO 2, RST: GPIO 4, SCK: GPIO 18, MOSI: GPIO 23, MISO: GPIO 19
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
/* 12-Button Keypad Matrix (4 Rows x 3 Columns)                               */
/* ========================================================================== */
#define LUMI_PIN_KEYPAD_ROW_0          14  /* Keypad Row 1 (Keys: 1, 2, 3)    */
#define LUMI_PIN_KEYPAD_ROW_1          27  /* Keypad Row 2 (Keys: 4, 5, 6)    */
#define LUMI_PIN_KEYPAD_ROW_2          16  /* Keypad Row 3 (Keys: 7, 8, 9)    */
#define LUMI_PIN_KEYPAD_ROW_3          12  /* Keypad Row 4 (Keys: *, 0, #) [STRAPPING PIN: MTDI] */

#define LUMI_PIN_KEYPAD_COL_0          35  /* Keypad Col 1 (Keys: 1, 4, 7, *) [INPUT-ONLY: External 10k pull-up to 3.3V] */
#define LUMI_PIN_KEYPAD_COL_1          13  /* Keypad Col 2 (Keys: 2, 5, 8, 0) [External 10k pull-up to 3.3V] */
#define LUMI_PIN_KEYPAD_COL_2          15  /* Keypad Col 3 (Keys: 3, 6, 9, #) [STRAPPING PIN: MTDO, External 10k pull-up to 3.3V] */

#define LUMI_KEYPAD_NUM_ROWS           4
#define LUMI_KEYPAD_NUM_COLS           3
#define LUMI_KEYPAD_DEBOUNCE_MS        20

/* ========================================================================== */
/* Status LED                                                                 */
/* ========================================================================== */
#define LUMI_PIN_LED_GREEN             32  /* Green Status LED (330 ohm to GND) */
#define LUMI_LED_ACTIVE_LEVEL          1   /* 1 = Active HIGH (HIGH means ON) */

/* ========================================================================== */
/* I2S Full-Duplex Audio (Shared Clock: INMP441 Mic + MAX98357A Amp)          */
/* ========================================================================== */
#define LUMI_PIN_I2S_BCLK              26  /* I2S Bit Clock (Shared Mic SCK & Amp BCLK) */
#define LUMI_PIN_I2S_WS                25  /* I2S Word Select / LRCLK (Shared Mic WS & Amp LRC) */
#define LUMI_PIN_I2S_MIC_DIN           34  /* INMP441 Microphone Data Out (ESP32 DIN, Input-only GPI) */
#define LUMI_PIN_I2S_AMP_DOUT          33  /* MAX98357A Amplifier Data In (ESP32 DOUT) */

#define LUMI_I2S_PORT_NUM              0   /* I2S Controller 0 */
#define LUMI_I2S_SAMPLE_RATE_HZ        16000
#define LUMI_I2S_BITS_PER_SAMPLE       32  /* 32-bit slot width for INMP441/MAX98357A */

/* ========================================================================== */
/* MicroSD Card (SPI Bus)                                                     */
/* ========================================================================== */
#define LUMI_PIN_SPI_SCK               18  /* SPI Clock (Shared)              */
#define LUMI_PIN_SPI_MOSI              23  /* SPI MOSI (Shared)               */
#define LUMI_PIN_SPI_MISO              19  /* SPI MISO (Shared)               */
#define LUMI_PIN_SD_CS                 17  /* MicroSD Dedicated Chip Select   */

/* ========================================================================== */
/* ILI9341 TFT Display (SPI Bus - PLANNED FOR LATER / NOT INSTALLED YET)       */
/* ========================================================================== */
#define LUMI_PIN_TFT_CS                5   /* TFT Dedicated Chip Select       */
#define LUMI_PIN_TFT_DC                2   /* TFT Data/Command Select [STRAPPING PIN: Boot Mode] */
#define LUMI_PIN_TFT_RST               4   /* TFT Hardware Reset              */

/* ========================================================================== */
/* DS3231 RTC (I2C Bus)                                                       */
/* ========================================================================== */
#define LUMI_PIN_I2C_SDA               21  /* I2C Data (SDA) (3.3V rail pull-up) */
#define LUMI_PIN_I2C_SCL               22  /* I2C Clock (SCL) (3.3V rail pull-up) */
#define LUMI_I2C_FREQ_HZ               100000 /* Standard 100 kHz I2C Clock  */

/* ========================================================================== */
/* Power Architecture Documentation Constants                                 */
/* ========================================================================== */
#define LUMI_RAIL_LEFT_VOLTS           3.3f /* Left rail: 3.3V (ESP32 3V3 pin) */
#define LUMI_RAIL_RIGHT_VOLTS          5.0f /* Right rail: 5.0V (ESP32 VIN pin)*/

#ifdef __cplusplus
}
#endif

#endif /* LUMI_PINS_H */
