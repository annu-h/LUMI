#include "audio_manager.h"

AudioManager::AudioManager(const lumi_audio_config_t &cfg)
    : _cfg(cfg), _capture_state(AUDIO_CAPTURE_STOPPED),
      _play_state(AUDIO_PLAY_STOPPED), _mic_head(0), _mic_tail(0),
      _mic_ring_fill(0), _spk_head(0), _spk_tail(0), _spk_ring_fill(0),
      _spk_remaining(0), _mic_seq(0), _mic_chunk_count(0),
      _mic_gap_count(0), _spk_underrun_count(0),
      _i2s_initialized(false), _last_error(0) {
}

AudioManager::~AudioManager() {
    end();
}

bool AudioManager::begin() {
    _last_error = 0;
    _capture_state = AUDIO_CAPTURE_STOPPED;
    _play_state = AUDIO_PLAY_STOPPED;
    flush_all();

    memset(&_i2s_cfg, 0, sizeof(_i2s_cfg));

    // I2S configuration for ESP32 Arduino core
    _i2s_cfg.sample_rate = _cfg.sample_rate_hz;
    _i2s_cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;
    _i2s_cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT; // standard I2S
    _i2s_cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
    _i2s_cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX | I2S_MODE_TX);
    _i2s_cfg.intr_alloc_flags = ESP_INTR_FLAG_LEVEL1;
    _i2s_cfg.dma_buf_count = _cfg.dma_buf_count;
    _i2s_cfg.dma_buf_len = _cfg.dma_buf_len;
    _i2s_cfg.use_apll = false;
    _i2s_cfg.tx_desc_auto_clear = true;
    _i2s_cfg.fixed_mclk = 0;

    esp_err_t err = i2s_driver_install((i2s_port_t)_cfg.port_num, &_i2s_cfg, 0, NULL);
    if (err != ESP_OK) {
        _last_error = (int)err;
        return false;
    }

    // Configure I2S pins using i2s_pin_config_t (ESP-IDF-style for Arduino ESP32 core)
    i2s_pin_config_t pin_cfg;
    memset(&pin_cfg, 0, sizeof(pin_cfg));
    pin_cfg.bck_io_num = _cfg.bclk_pin;
    pin_cfg.ws_io_num = _cfg.ws_pin;
    pin_cfg.data_out_num = _cfg.dout_pin;
    pin_cfg.data_in_num = _cfg.din_pin;
    i2s_set_pin((i2s_port_t)_cfg.port_num, &pin_cfg);

    err = i2s_start((i2s_port_t)_cfg.port_num);
    if (err != ESP_OK) {
        _last_error = (int)err;
        i2s_driver_uninstall((i2s_port_t)_cfg.port_num);
        return false;
    }

    _i2s_initialized = true;
    return true;
}

void AudioManager::end() {
    if (_i2s_initialized) {
        i2s_stop((i2s_port_t)_cfg.port_num);
        i2s_driver_uninstall((i2s_port_t)_cfg.port_num);
        _i2s_initialized = false;
    }
    flush_all();
    _last_error = 0;
}

void AudioManager::start_capture() {
    if (!_i2s_initialized) return;
    _capture_state = AUDIO_CAPTURE_STARTING;
    flush_all();
    // The I2S driver runs continuously; capture just clears buffers and resets state.
    _mic_chunk_count = 0;
    _mic_gap_count = 0;
    _capture_state = AUDIO_CAPTURE_RUNNING;
}

void AudioManager::stop_capture() {
    if (!_i2s_initialized) return;
    _capture_state = AUDIO_CAPTURE_STOPPING;
    // Allow any pending DMA transfers to finish; do not flush I2S.
    _capture_state = AUDIO_CAPTURE_STOPPED;
}

void AudioManager::start_playback(uint32_t total_samples) {
    if (!_i2s_initialized) return;
    _spk_remaining = total_samples;
    _spk_underrun_count = 0;
    _play_state = AUDIO_PLAY_STARTING;
    flush_all();
    _play_state = AUDIO_PLAY_RUNNING;
}

void AudioManager::stop_playback() {
    if (!_i2s_initialized) return;
    _play_state = AUDIO_PLAY_STOPPING;
    _spk_remaining = 0;
    flush_all();
    _play_state = AUDIO_PLAY_STOPPED;
}

void AudioManager::flush_all() {
    _mic_head = 0; _mic_tail = 0; _mic_ring_fill = 0;
    _spk_head = 0; _spk_tail = 0; _spk_ring_fill = 0;
    memset(_mic_ring, 0, sizeof(_mic_ring));
    memset(_spk_ring, 0, sizeof(_spk_ring));
}

uint16_t AudioManager::read_mic(int16_t *out, uint16_t max_samples) {
    if (!_i2s_initialized || _capture_state != AUDIO_CAPTURE_RUNNING) {
        return 0;
    }
    uint16_t avail = (_mic_ring_fill > max_samples) ? max_samples : (uint16_t)_mic_ring_fill;
    if (avail > 0 && out != nullptr) {
        for (uint16_t i = 0; i < avail; i++) {
            out[i] = _mic_ring[_mic_tail];
            _mic_tail = (_mic_tail + 1) % LUMI_MIC_RING_SIZE;
        }
        _mic_ring_fill -= avail;
    }
    return avail;
}

uint16_t AudioManager::push_spk(const int16_t *in, uint16_t num_samples) {
    if (!_i2s_initialized || _play_state != AUDIO_PLAY_RUNNING) {
        return 0;
    }
    uint16_t pushed = 0;
    for (uint16_t i = 0; i < num_samples; i++) {
        if (_spk_ring_fill >= LUMI_SPK_RING_SIZE) {
            break; // ring full — drop (underrun indicator handled by count)
        }
        _spk_ring[_spk_head] = in[i];
        _spk_head = (_spk_head + 1) % LUMI_SPK_RING_SIZE;
        _spk_ring_fill++;
        pushed++;
    }
    _spk_remaining = (_spk_remaining > pushed) ? (_spk_remaining - pushed) : 0;
    return pushed;
}

void AudioManager::update_playback() {
    if (!_i2s_initialized || _play_state != AUDIO_PLAY_RUNNING) {
        return;
    }

    // Read microphone samples continuously via I2S RX.
    // We use a fixed-size buffer and push to the ring.
    int32_t rx_samples[128];
    size_t bytes_read = 0;
    esp_err_t err = i2s_read((i2s_port_t)_cfg.port_num, (void*)rx_samples,
                             sizeof(rx_samples), &bytes_read, 0);
    if (err == ESP_OK && bytes_read > 0) {
        uint16_t sample_count = (uint16_t)(bytes_read / 4); // 32-bit = 4 bytes per sample
        int16_t converted[128];
        for (uint16_t i = 0; i < sample_count && i < 128; i++) {
            // I2S 32-bit standard: left-aligned 24-bit or 32-bit data.
            // For INMP441, data is left-justified 24-bit PCM inside a 32-bit slot.
            // We extract the high 16 bits to get signed 16-bit PCM.
            int32_t value = rx_samples[i];
            if (value > 0x7FFF) value |= 0xFFFF0000; // sign-extend
            int16_t s16 = (int16_t)(value >> 8); // extract high 16 bits from 32-bit slot
            converted[i] = s16;
        }
        // Push to mic ring buffer (bounded)
        uint16_t to_push = sample_count;
        uint16_t available = (uint16_t)(LUMI_MIC_RING_SIZE - _mic_ring_fill);
        if (to_push > available) {
            to_push = available;
        }
        for (uint16_t i = 0; i < to_push; i++) {
            _mic_ring[_mic_head] = converted[i];
            _mic_head = (_mic_head + 1) % LUMI_MIC_RING_SIZE;
            _mic_ring_fill++;
        }
        // If overflow occurred, count as a gap (lost samples)
        if (to_push < sample_count) {
            _mic_gap_count++;
        }
    } else if (err != ESP_OK) {
        _last_error = (int)err;
    }

    // Transmit speaker playback via I2S TX.
    if (_spk_ring_fill > 0 && _spk_remaining > 0) {
        int32_t tx_samples[128];
        uint16_t to_send = (uint16_t)((_spk_ring_fill > 128) ? 128 : _spk_ring_fill);
        uint16_t samples_read = 0;
        for (uint16_t i = 0; i < to_send && samples_read < 128; i++) {
            tx_samples[i] = (int32_t)_spk_ring[_spk_tail];
            _spk_tail = (_spk_tail + 1) % LUMI_SPK_RING_SIZE;
            samples_read++;
        }
        _spk_ring_fill -= samples_read;

        size_t bytes_written = 0;
        esp_err_t tx_err = i2s_write((i2s_port_t)_cfg.port_num, (void*)tx_samples,
                                     samples_read * sizeof(int32_t), &bytes_written, 0);
        if (tx_err != ESP_OK) {
            _last_error = (int)tx_err;
        }
    } else if (_spk_remaining > 0 && _spk_ring_fill == 0) {
        // Speaker underrun: buffer empty but playback not finished.
        _spk_underrun_count++;
    }

    // Check playback complete condition.
    if (_play_state == AUDIO_PLAY_RUNNING && _spk_remaining == 0 && _spk_ring_fill == 0) {
        _play_state = AUDIO_PLAY_STOPPING;
        _play_state = AUDIO_PLAY_STOPPED;
    }
}

lumi_audio_format_t AudioManager::audio_format() const {
    lumi_audio_format_t fmt;
    fmt.sample_rate_hz_div_1000 = 16;  // 16 = 16000 Hz
    fmt.channels = 1;
    fmt.bits_per_sample = 16;
    fmt.format = LUMI_AUDIO_FORMAT_LE16;
    return fmt;
}
