#include "rtc_manager.h"

RTCManager::RTCManager() : _available(false), _last_error(0) {}

bool RTCManager::begin(int sda, int scl, uint32_t freq_hz) {
    Wire.begin(sda, scl);
    Wire.setClock(freq_hz);

    // Probe DS3231
    Wire.beginTransmission(DS3231_I2C_ADDR);
    uint8_t err = Wire.endTransmission();

    _available = (err == 0);
    _last_error = err;
    return _available;
}

bool RTCManager::read_time(lumi_rtc_time_t *out) {
    if (!_available || out == nullptr) return false;

    Wire.beginTransmission(DS3231_I2C_ADDR);
    Wire.write(0x00); // Start at register 0
    uint8_t err = Wire.endTransmission();
    if (err != 0) {
        _last_error = err;
        return false;
    }

    Wire.requestFrom(DS3231_I2C_ADDR, 7);
    if (Wire.available() < 7) {
        _last_error = -1;
        return false;
    }

    out->seconds = _bcd_to_bin(Wire.read() & 0x7F);
    out->minutes = _bcd_to_bin(Wire.read() & 0x7F);
    out->hours = _bcd_to_bin(Wire.read() & 0x3F); // 24h mode
    out->day = Wire.read() & 0x07;
    out->date = _bcd_to_bin(Wire.read() & 0x3F);
    uint8_t mon_cent = Wire.read();
    out->month = _bcd_to_bin(mon_cent & 0x1F);
    out->year = 2000 + _bcd_to_bin(Wire.read());

    out->valid = _plausible(*out);
    out->power_lost = false; // Check status register if needed
    return out->valid;
}

bool RTCManager::set_time(const lumi_rtc_time_t &t) {
    if (!_available || !_plausible(t)) return false;

    Wire.beginTransmission(DS3231_I2C_ADDR);
    Wire.write(0x00);
    Wire.write(_bin_to_bcd(t.seconds));
    Wire.write(_bin_to_bcd(t.minutes));
    Wire.write(_bin_to_bcd(t.hours));
    Wire.write(t.day);
    Wire.write(_bin_to_bcd(t.date));
    Wire.write(_bin_to_bcd(t.month));
    Wire.write(_bin_to_bcd(t.year - 2000));

    uint8_t err = Wire.endTransmission();
    _last_error = err;
    return (err == 0);
}

int16_t RTCManager::read_temp_quarter_celsius() {
    if (!_available) return INT16_MIN;

    Wire.beginTransmission(DS3231_I2C_ADDR);
    Wire.write(0x11);
    if (Wire.endTransmission() != 0) return INT16_MIN;

    Wire.requestFrom(DS3231_I2C_ADDR, 2);
    if (Wire.available() < 2) return INT16_MIN;

    int8_t temp_msb = Wire.read();
    uint8_t temp_lsb = Wire.read();

    return (int16_t)((temp_msb << 2) | (temp_lsb >> 6));
}

uint8_t RTCManager::_bcd_to_bin(uint8_t bcd) {
    return ((bcd >> 4) * 10) + (bcd & 0x0F);
}

uint8_t RTCManager::_bin_to_bcd(uint8_t bin) {
    return ((bin / 10) << 4) | (bin % 10);
}

bool RTCManager::_plausible(const lumi_rtc_time_t &t) {
    return (t.seconds < 60 && t.minutes < 60 && t.hours < 24 &&
            t.day >= 1 && t.day <= 7 &&
            t.date >= 1 && t.date <= 31 &&
            t.month >= 1 && t.month <= 12 &&
            t.year >= 2020 && t.year < 2100);
}
