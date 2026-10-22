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

    uint8_t bytes_read = Wire.requestFrom(DS3231_I2C_ADDR, 7);
    if (bytes_read < 7) {
        _last_error = -1;
        return false;
    }

    out->seconds = _bcd2bin(Wire.read() & 0x7F);
    out->minutes = _bcd2bin(Wire.read() & 0x7F);
    out->hours   = _bcd2bin(Wire.read() & 0x3F); // 24h mode
    out->day     = Wire.read() & 0x07;
    out->date    = _bcd2bin(Wire.read() & 0x3F);
    out->month   = _bcd2bin(Wire.read() & 0x1F);
    out->year    = 2000 + _bcd2bin(Wire.read());

    // Basic validity check
    out->valid = (out->seconds < 60 && out->minutes < 60 && out->hours < 24 &&
                  out->date >= 1 && out->date <= 31 &&
                  out->month >= 1 && out->month <= 12 &&
                  out->year >= 2024 && out->year <= 2099);

    out->power_lost = power_lost();
    return out->valid;
}

bool RTCManager::set_time(uint16_t year, uint8_t month, uint8_t date,
                          uint8_t hours, uint8_t minutes, uint8_t seconds) {
    if (!_available) return false;

    Wire.beginTransmission(DS3231_I2C_ADDR);
    Wire.write(0x00); // Start at register 0
    Wire.write(_bin2bcd(seconds));
    Wire.write(_bin2bcd(minutes));
    Wire.write(_bin2bcd(hours));
    Wire.write(1); // Day of week (arbitrary 1)
    Wire.write(_bin2bcd(date));
    Wire.write(_bin2bcd(month));
    Wire.write(_bin2bcd(year >= 2000 ? year - 2000 : year));
    uint8_t err = Wire.endTransmission();
    if (err != 0) {
        _last_error = err;
        return false;
    }

    // Clear oscillator stop flag (OSF in control/status register 0x0F)
    Wire.beginTransmission(DS3231_I2C_ADDR);
    Wire.write(0x0F);
    err = Wire.endTransmission();
    if (err == 0 && Wire.requestFrom(DS3231_I2C_ADDR, 1) == 1) {
        uint8_t status = Wire.read();
        status &= ~0x80; // Clear bit 7 (OSF)
        Wire.beginTransmission(DS3231_I2C_ADDR);
        Wire.write(0x0F);
        Wire.write(status);
        Wire.endTransmission();
    }

    return true;
}

bool RTCManager::power_lost() {
    if (!_available) return false;
    Wire.beginTransmission(DS3231_I2C_ADDR);
    Wire.write(0x0F); // Control/Status register
    if (Wire.endTransmission() != 0) return false;
    if (Wire.requestFrom(DS3231_I2C_ADDR, 1) != 1) return false;
    return (Wire.read() & 0x80) != 0; // Bit 7 = OSF
}

uint8_t RTCManager::_bcd2bin(uint8_t bcd) {
    return bcd - 6 * (bcd >> 4);
}

uint8_t RTCManager::_bin2bcd(uint8_t bin) {
    return bin + 6 * (bin / 10);
}
