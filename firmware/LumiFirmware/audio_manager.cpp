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

#include <math.h>

uint16_t AudioManager::read_mic(int16_t *out, uint16_t max_samples) {
    if (!_i2s_initialized || _capture_state != AUDIO_CAPTURE_RUNNING || out == nullptr || max_samples == 0) {
        return 0;
    }

    // Limit chunk size per read
    uint16_t to_read = (max_samples > 128) ? 128 : max_samples;
    int32_t rx_stereo[256]; // 128 stereo pairs (32-bit slot width)
    size_t bytes_read = 0;

    esp_err_t err = i2s_read((i2s_port_t)_cfg.port_num, (void*)rx_stereo,
                             to_read * 2 * sizeof(int32_t), &bytes_read, 0);

    if (err == ESP_OK && bytes_read > 0) {
        uint16_t frames = (uint16_t)(bytes_read / (2 * sizeof(int32_t)));
        for (uint16_t i = 0; i < frames; i++) {
            // INMP441 L/R tied to GND: Left channel data is at index [2*i].
            // Data is 24-bit MSB-aligned in 32-bit slot.
            // Arithmetic right shift by 14 provides +12dB digital gain with saturation clamping.
            int32_t raw_left = rx_stereo[2 * i];
            int32_t s = raw_left >> 14;
            if (s > 32767) s = 32767;
            else if (s < -32768) s = -32768;
            out[i] = (int16_t)s;
        }
        _mic_chunk_count++;
        return frames;
    } else if (err != ESP_OK) {
        _last_error = (int)err;
    }
    return 0;
}

uint16_t AudioManager::push_spk(const int16_t *in, uint16_t num_samples) {
    if (!_i2s_initialized || _play_state != AUDIO_PLAY_RUNNING) {
        return 0;
    }
    uint16_t pushed = 0;
    for (uint16_t i = 0; i < num_samples; i++) {
        if (_spk_ring_fill >= LUMI_SPK_RING_SIZE) {
            break; // ring full
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

    // Transmit speaker playback via I2S TX
    if (_spk_ring_fill > 0 && _spk_remaining > 0) {
        int32_t tx_stereo[256]; // 128 stereo pairs
        uint16_t to_send = (uint16_t)((_spk_ring_fill > 128) ? 128 : _spk_ring_fill);
        uint16_t samples_read = 0;

        for (uint16_t i = 0; i < to_send; i++) {
            int16_t sample16 = _spk_ring[_spk_tail];
            _spk_tail = (_spk_tail + 1) % LUMI_SPK_RING_SIZE;
            samples_read++;

            // Shift 16-bit audio into top 16 bits of 32-bit slot for MAX98357A.
            // Duplicate to both Left and Right channels for mono speaker output.
            int32_t out_word = ((int32_t)sample16) << 16;
            tx_stereo[2 * i]     = out_word;
            tx_stereo[2 * i + 1] = out_word;
        }
        _spk_ring_fill -= samples_read;

        size_t bytes_written = 0;
        esp_err_t tx_err = i2s_write((i2s_port_t)_cfg.port_num, (void*)tx_stereo,
                                     samples_read * 2 * sizeof(int32_t), &bytes_written, 0);
        if (tx_err != ESP_OK) {
            _last_error = (int)tx_err;
        }
    } else if (_spk_remaining > 0 && _spk_ring_fill == 0) {
        _spk_underrun_count++;
    }

    // Check playback complete condition
    if (_play_state == AUDIO_PLAY_RUNNING && _spk_remaining == 0 && _spk_ring_fill == 0) {
        _play_state = AUDIO_PLAY_STOPPING;
        _play_state = AUDIO_PLAY_STOPPED;
    }
}

bool AudioManager::run_mic_diagnostic(uint32_t duration_ms, mic_diagnostic_stats_t &stats) {
    if (!_i2s_initialized) return false;

    stats.total_samples = 0;
    stats.min_sample = 32767;
    stats.max_sample = -32768;
    stats.clipping_count = 0;
    int64_t sum = 0;
    double sum_sq = 0.0;

    start_capture();

    unsigned long start_time = millis();
    int16_t buf[128];

    while (millis() - start_time < duration_ms) {
        uint16_t n = read_mic(buf, 128);
        if (n > 0) {
            for (uint16_t i = 0; i < n; i++) {
                int16_t s = buf[i];
                stats.total_samples++;
                if (s < stats.min_sample) stats.min_sample = s;
                if (s > stats.max_sample) stats.max_sample = s;
                if (s == 32767 || s == -32768) stats.clipping_count++;
                sum += s;
                sum_sq += ((double)s * (double)s);
            }
        } else {
            delay(1);
        }
    }

    stop_capture();

    if (stats.total_samples > 0) {
        stats.peak_to_peak = (int32_t)stats.max_sample - (int32_t)stats.min_sample;
        stats.dc_offset = (int32_t)(sum / (int64_t)stats.total_samples);
        stats.rms = (float)sqrt(sum_sq / (double)stats.total_samples);
        stats.is_all_zeros = (stats.min_sample == 0 && stats.max_sample == 0);
        stats.is_silent = (stats.rms < 120.0f);
        stats.is_voice = (stats.rms >= 220.0f);
        return true;
    }

    return false;
}

bool AudioManager::play_test_tone(float freq_hz, uint32_t duration_ms, float volume_pct) {
    if (!_i2s_initialized) return false;

    // Constrain volume to safe range (5% to 30%)
    if (volume_pct < 5.0f) volume_pct = 5.0f;
    if (volume_pct > 30.0f) volume_pct = 30.0f;

    float amplitude = 32767.0f * (volume_pct / 100.0f);
    float sample_rate = (float)_cfg.sample_rate_hz;
    float phase_step = 2.0f * (float)M_PI * freq_hz / sample_rate;
    float phase = 0.0f;

    unsigned long start_time = millis();
    int32_t tx_chunk[256]; // 128 stereo pairs

    while (millis() - start_time < duration_ms) {
        for (int i = 0; i < 128; i++) {
            float val = sinf(phase) * amplitude;
            phase += phase_step;
            if (phase >= 2.0f * (float)M_PI) phase -= 2.0f * (float)M_PI;

            int32_t out_word = ((int32_t)(int16_t)val) << 16;
            tx_chunk[2 * i]     = out_word;
            tx_chunk[2 * i + 1] = out_word;
        }

        size_t written = 0;
        i2s_write((i2s_port_t)_cfg.port_num, (void*)tx_chunk, sizeof(tx_chunk), &written, pdMS_TO_TICKS(50));
    }

    // Flush with silence to avoid click/pop
    memset(tx_chunk, 0, sizeof(tx_chunk));
    size_t written = 0;
    i2s_write((i2s_port_t)_cfg.port_num, (void*)tx_chunk, sizeof(tx_chunk), &written, pdMS_TO_TICKS(50));

    return true;
}

lumi_audio_format_t AudioManager::audio_format() const {
    lumi_audio_format_t fmt;
    fmt.sample_rate_hz_div_1000 = 16;  // 16 = 16000 Hz
    fmt.channels = 1;
    fmt.bits_per_sample = 16;
    fmt.format = LUMI_AUDIO_FORMAT_LE16;
    return fmt;
}

