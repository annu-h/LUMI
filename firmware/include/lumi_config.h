/**
 * @file lumi_config.h
 * @brief Implementation-ready hardware driver configuration structures for Project LUMI.
 *
 * Target: ESP32 DevKit V1 (ESP-IDF v5.x / Arduino ESP32 core compatible)
 *
 * This header defines implementation-ready configurations for:
 *   - Shared full-duplex I2S audio driver (INMP441 mic + MAX98357A amp)
 *   - Keypad 4x3 matrix driver with dual-mode support (shortcut vs numeric-entry)
 *   - Shared SPI bus driver for SD card and ILI9341 TFT display
 *   - I2C bus driver for DS3231 Real-Time Clock
 *   - GPIO status LED driver
 */

#ifndef LUMI_CONFIG_H
#define LUMI_CONFIG_H

#include "lumi_pins.h"

#ifdef __cplusplus
extern "C" {
#endif

/* ========================================================================== */
/* Staged Hardware Bring-Up Enable/Disable Flags                              */
/* ========================================================================== */
#define LUMI_ENABLE_TFT                0   /* 0 = TFT NOT PHYSICALLY INSTALLED YET (default: disabled) */
#define LUMI_ENABLE_SD                 1   /* 1 = MicroSD card enabled (SPI CS: GPIO 17)               */
#define LUMI_ENABLE_RTC                1   /* 1 = DS3231 RTC enabled (I2C SDA: 21, SCL: 22)           */
#define LUMI_ENABLE_KEYPAD             1   /* 1 = 4x3 Keypad enabled (Rows: 14,27,16,12 | Cols: 35,13,15) */
#define LUMI_ENABLE_AUDIO              1   /* 1 = I2S Audio enabled (Mic: 34, Amp: 33, BCLK: 26, WS: 25) */
#define LUMI_ENABLE_LED                1   /* 1 = Status LED enabled (GPIO 32, active HIGH)            */


/* ========================================================================== */
/* Hardware Safety Verification Flags                                         */
/* ========================================================================== */

/**
 * Compile-time sanity check to prevent pin overlaps across peripherals.
 */
#define LUMI_CHECK_PIN_CONFLICT(p1, p2) ((p1) == (p2))

/* Static validation assertions (will trigger compiler error if pins collide) */
#if (LUMI_PIN_KEYPAD_ROW_0 == LUMI_PIN_KEYPAD_COL_0) || \
    (LUMI_PIN_KEYPAD_ROW_3 == LUMI_PIN_I2S_BCLK)    || \
    (LUMI_PIN_SD_CS        == LUMI_PIN_TFT_CS)      || \
    (LUMI_PIN_I2S_MIC_DIN  == LUMI_PIN_I2S_AMP_DOUT)|| \
    (LUMI_PIN_LED_GREEN    == LUMI_PIN_SPI_SCK)
#error "FATAL: Detected pin conflict in LUMI hardware pin definition!"
#endif

/* ========================================================================== */
/* I2S Driver Configuration Specifications                                    */
/* ========================================================================== */

typedef struct {
    int port_num;                  /* 0 (I2S0 supports full duplex)           */
    int sample_rate_hz;            /* 16000 Hz                                */
    int bits_per_sample;           /* 32-bit slot width                       */
    int bclk_pin;                  /* GPIO 26                                 */
    int ws_pin;                    /* GPIO 25                                 */
    int din_pin;                   /* GPIO 34 (INMP441 Data Out)              */
    int dout_pin;                  /* GPIO 33 (MAX98357A Data In)             */
    bool full_duplex;              /* true: simultaneous TX and RX            */
    int dma_buf_count;             /* 8 buffers                               */
    int dma_buf_len;               /* 256 samples                             */
} lumi_i2s_hardware_config_t;

typedef lumi_i2s_hardware_config_t lumi_audio_config_t;

static inline lumi_i2s_hardware_config_t lumi_get_default_i2s_config(void) {
    lumi_i2s_hardware_config_t cfg = {
        .port_num         = LUMI_I2S_PORT_NUM,
        .sample_rate_hz   = LUMI_I2S_SAMPLE_RATE_HZ,
        .bits_per_sample  = LUMI_I2S_BITS_PER_SAMPLE,
        .bclk_pin         = LUMI_PIN_I2S_BCLK,
        .ws_pin           = LUMI_PIN_I2S_WS,
        .din_pin          = LUMI_PIN_I2S_MIC_DIN,
        .dout_pin         = LUMI_PIN_I2S_AMP_DOUT,
        .full_duplex      = true,
        .dma_buf_count    = 8,
        .dma_buf_len      = 256
    };
    return cfg;
}

/* ========================================================================== */
/* Keypad Matrix Configuration & State Structure                              */
/* ========================================================================== */

typedef struct {
    lumi_keypad_mode_t mode;       /* SHORTCUT vs NUMERIC                     */
    char numeric_buffer[32];       /* Buffer for numeric entry (e.g. math)    */
    uint8_t buffer_len;            /* Current length of entered numbers       */
    uint32_t last_scan_time_ms;    /* Debounce timer tracking                 */
    char last_key_pressed;         /* Key tracking for debouncing             */
} lumi_keypad_state_t;

/* ========================================================================== */
/* SPI Bus Configuration Specifications                                       */
/* ========================================================================== */

typedef struct {
    int sck_pin;                   /* GPIO 18                                 */
    int mosi_pin;                  /* GPIO 23                                 */
    int miso_pin;                  /* GPIO 19                                 */
    int sd_cs_pin;                 /* GPIO 17                                 */
    int tft_cs_pin;                /* GPIO 5                                  */
    int tft_dc_pin;                /* GPIO 2                                  */
    int tft_reset_pin;             /* GPIO 4                                  */
    int max_transfer_sz;           /* 4096 bytes                              */
} lumi_spi_hardware_config_t;

static inline lumi_spi_hardware_config_t lumi_get_default_spi_config(void) {
    lumi_spi_hardware_config_t cfg = {
        .sck_pin          = LUMI_PIN_SPI_SCK,
        .mosi_pin         = LUMI_PIN_SPI_MOSI,
        .miso_pin         = LUMI_PIN_SPI_MISO,
        .sd_cs_pin        = LUMI_PIN_SD_CS,
        .tft_cs_pin       = LUMI_PIN_TFT_CS,
        .tft_dc_pin       = LUMI_PIN_TFT_DC,
        .tft_reset_pin    = LUMI_PIN_TFT_RESET,
        .max_transfer_sz  = 4096
    };
    return cfg;
}

/* ========================================================================== */
/* I2C Configuration (DS3231 RTC)                                             */
/* ========================================================================== */

typedef struct {
    int port_num;                  /* I2C_NUM_0                               */
    int sda_pin;                   /* GPIO 21                                 */
    int scl_pin;                   /* GPIO 22                                 */
    int clk_speed_hz;              /* 100000 (100 kHz)                        */
} lumi_i2c_hardware_config_t;

static inline lumi_i2c_hardware_config_t lumi_get_default_i2c_config(void) {
    lumi_i2c_hardware_config_t cfg = {
        .port_num     = LUMI_I2C_PORT_NUM,
        .sda_pin      = LUMI_PIN_I2C_SDA,
        .scl_pin      = LUMI_PIN_I2C_SCL,
        .clk_speed_hz = LUMI_I2C_FREQ_HZ
    };
    return cfg;
}

#ifdef __cplusplus
}
#endif

#endif /* LUMI_CONFIG_H */
