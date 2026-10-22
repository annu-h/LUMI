/**
 * @file audio_manager.h
 * @brief Non-blocking I2S audio manager for Project LUMI.
 *
 * Handles INMP441 microphone capture and MAX98357A speaker playback
 * through the ESP32 I2S0 controller (full-duplex shared clock).
 *
 * Design constraints:
 *   - Half-duplex audio interaction initially.
 *   - Non-blocking: never blocks the main loop or FreeRTOS tasks.
 *   - Bounded buffers: no dynamic allocation in the hot path.
 *   - Designed so continuous wake-word streaming can be added later.
 */

#pragma once

#include <Arduino.h>
#include "driver/i2s.h"
#include "../../include/lumi_pins.h"
#include "../../include/lumi_config.h"
#include "../../include/lumi_protocol.h"

/** Number of DMA buffers for I2S */
#define LUMI_AUDIO_DMA_BUF_COUNT  8
/** DMA buffer length in samples (32-bit slot) */
#define LUMI_AUDIO_DMA_BUF_LEN    256

/** Number of 16-bit samples per audio chunk packet */
#define LUMI_AUDIO_CHUNK_SAMPLES  192

/** Ring buffer depth for microphone capture (in 16-bit samples) */
#define LUMI_MIC_RING_SIZE        4096

/** Ring buffer depth for speaker playback (in 16-bit samples) */
#define LUMI_SPK_RING_SIZE        8192

/** Audio format constant: signed 16-bit LE PCM */
#define LUMI_AUDIO_FORMAT_LE16     0

/** I2S mode constants */
#define LUMI_I2S_MODE_TX  0
#define LUMI_I2S_MODE_RX  1
#define LUMI_I2S_MODE_TXRX 2

/** Capture state machine */
typedef enum {
    AUDIO_CAPTURE_STOPPED = 0,
    AUDIO_CAPTURE_STARTING,
    AUDIO_CAPTURE_RUNNING,
    AUDIO_CAPTURE_STOPPING,
} audio_capture_state_t;

/** Playback state machine */
typedef enum {
    AUDIO_PLAY_STOPPED = 0,
    AUDIO_PLAY_STARTING,
    AUDIO_PLAY_RUNNING,
    AUDIO_PLAY_STOPPING,
} audio_play_state_t;

class AudioManager {
public:
    AudioManager(const lumi_audio_config_t &cfg);
    ~AudioManager();

    bool begin();
    void end();

    void start_capture();
    void stop_capture();
    bool is_capturing() const { return _capture_state == AUDIO_CAPTURE_RUNNING; }

    void start_playback(uint32_t total_samples);
    void stop_playback();
    bool is_playing() const { return _play_state == AUDIO_PLAY_RUNNING; }

    /** Poll for available microphone samples (non-blocking). Returns count written. */
    uint16_t read_mic(int16_t *out, uint16_t max_samples);

    /** Push samples into speaker ring buffer. Returns count actually pushed. */
    uint16_t push_spk(const int16_t *in, uint16_t num_samples);

    /** Drain speaker ring buffer to I2S TX (non-blocking, call periodically). */
    void update_playback();

    /** Flush all audio buffers (e.g. on cancellation). */
    void flush_all();

    /** Get current ring buffer fill levels (for diagnostics). */
    uint16_t mic_ring_fill() const { return _mic_ring_fill; }
    uint16_t spk_ring_fill() const { return _spk_ring_fill; }

    /** Returns the audio format descriptor for protocol framing. */
    lumi_audio_format_t audio_format() const;

    /** Returns the last I2S driver error code (0 = no error). */
    int last_error() const { return _last_error; }

    /** Returns the number of mic chunks sent since start. */
    uint32_t mic_chunk_count() const { return _mic_chunk_count; }

    /** Returns the number of mic sequence gaps detected. */
    uint32_t mic_gap_count() const { return _mic_gap_count; }

    /** Returns the number of speaker underruns. */
    uint32_t spk_underrun_count() const { return _spk_underrun_count; }

private:
    lumi_audio_config_t _cfg;
    i2s_config_t _i2s_cfg;

    audio_capture_state_t _capture_state;
    audio_play_state_t _play_state;

    /* Mic ring buffer */
    int16_t _mic_ring[LUMI_MIC_RING_SIZE];
    uint16_t _mic_head;
    uint16_t _mic_tail;
    uint16_t _mic_ring_fill;

    /* Speaker ring buffer */
    int16_t _spk_ring[LUMI_SPK_RING_SIZE];
    uint16_t _spk_head;
    uint16_t _spk_tail;
    uint16_t _spk_ring_fill;
    uint32_t _spk_remaining;  /* total samples still to play */

    /* Mic sequence tracking */
    uint8_t _mic_seq;        /* last sent sequence number */
    uint32_t _mic_chunk_count;
    uint32_t _mic_gap_count;

    /* Speaker tracking */
    uint32_t _spk_underrun_count;

    /* I2S driver state */
    bool _i2s_initialized;
    int _last_error;

    void _init_i2s_driver();
    void _mic_ring_push(const int16_t *data, uint16_t n);
    uint16_t _mic_ring_pop(int16_t *out, uint16_t max);
    void _spk_ring_push(const int16_t *data, uint16_t n);
    uint16_t _spk_ring_pop(int16_t *out, uint16_t max);
};