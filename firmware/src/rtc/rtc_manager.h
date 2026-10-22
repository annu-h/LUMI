/**
 * @file rtc_manager.h
 * @brief DS3231 RTC management for Project LUMI.
 *
 * Reads date/time over I2C. Never overwrites a valid RTC time with
 * a build timestamp.
 */

#pragma once

#include <Arduino.h>
#include <Wire.h>

#define DS3231_I2C_ADDR 0x68

/** Snapshot of the DS3231 time registers */
typedef struct {
    uint8_t  seconds;   // 0-59
    uint8_t  minutes;   // 0-59
    uint8_t  hours;     // 0-23 (24h mode)
    uint8_t  day;       // 1-7 (day of week)
    uint8_t  date;      // 1-31
    uint8_t  month;     // 1-12
    uint16_t year;      // 2000+
    bool     valid;     // RTC responded and values are plausible
    bool     power_lost; // OSF (oscillator stop flag) was set
} lumi_rtc_time_t;

class RTCManager {
public:
    RTCManager();

    bool begin(int sda = 21, int scl = 22, uint32_t freq_hz = 100000);

    bool is_available() const { return _available; }

    /** Read current time into out. Returns false if RTC is unreachable. */
    bool read_time(lumi_rtc_time_t *out);

    /**
     * Set the time ONLY when the caller has independently verified the new
     * time is correct (e.g. received a validated timestamp from the Python host
     * over serial). Never called automatically in the startup path.
     */
    bool set_time(const lumi_rtc_time_t &t);

    /** Get temperature (0.25°C resolution). Returns INT16_MIN on error. */
    int16_t read_temp_quarter_celsius();

    int last_error() const { return _last_error; }

private:
    bool _available;
    int  _last_error;

    uint8_t _bcd_to_bin(uint8_t bcd);
    uint8_t _bin_to_bcd(uint8_t bin);
    bool _plausible(const lumi_rtc_time_t &t);
};
