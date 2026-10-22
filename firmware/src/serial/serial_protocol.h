/**
 * @file serial_protocol.h
 * @brief USB serial protocol encoder/decoder for Project LUMI.
 *
 * This module handles framing, CRC validation, and packet queuing for
 * reliable binary communication with the Python voice stack.
 *
 * Design goals:
 *   - Non-blocking: all operations return immediately.
 *   - Bounded: uses fixed-size ring buffers for TX/RX.
 *   - Recovery: detects framing errors and resynchronizes.
 */

#pragma once

#include <Arduino.h>
#include "../../include/lumi_protocol.h"

/** RX buffer size (multiple of max packet: 7 bytes SOF+TYPE+LEN+1 payload+CHECKSUM) */
#define LUMI_RX_BUF_SIZE  4096

/** TX buffer size */
#define LUMI_TX_BUF_SIZE  8192

/** RX parsing state */
typedef enum {
    RX_STATE_WAIT_SOF0 = 0,
    RX_STATE_WAIT_SOF1,
    RX_STATE_WAIT_TYPE,
    RX_STATE_WAIT_LEN,
    RX_STATE_WAIT_PAYLOAD,
    RX_STATE_WAIT_CHECKSUM,
} rx_state_t;

/** Parsed packet result */
typedef struct {
    bool valid;
    lumi_packet_t packet;
    uint32_t parse_time_us;  // timestamp of successful parse
    uint32_t seq_gap;        // mic sequence gap (for timing analysis)
} rx_result_t;

/** Available RX packet types after parsing */
typedef enum {
    PACKET_TYPE_UNKNOWN = 0,
    PACKET_TYPE_HOST_READY,
    PACKET_TYPE_AUDIO_SPK_START,
    PACKET_TYPE_AUDIO_SPK_CHUNK,
    PACKET_TYPE_AUDIO_SPK_END,
    PACKET_TYPE_COMMAND,
    PACKET_TYPE_UTTERANCE_END,
    PACKET_TYPE_LED_CONTROL,
} packet_type_t;

class SerialProtocol {
public:
    SerialProtocol();
    ~SerialProtocol();

    void begin(uint32_t baud = 115200);
    void end();

    /** Poll for incoming bytes and decode packets. Thread-safe. */
    void poll_rx();

    /** Get a successfully decoded packet (non-blocking). Returns true if packet available. */
    bool get_packet(rx_result_t *result);

    /** Queue a packet for transmission. Returns true if accepted. */
    bool queue_tx(const lumi_packet_t *packet);

    /** Flush TX buffer to serial (call in loop or after queue). */
    void flush_tx();

    /** Convenience: send device info packet */
    void send_device_info(uint8_t fw_major, uint8_t fw_minor, uint8_t fw_patch,
                          const char *board_name, const char *mcu_name,
                          const lumi_audio_format_t *audio_fmt);

    /** Convenience: send peripheral status */
    void send_peripheral_status(bool sd_ok, bool rtc_ok, bool tft_ok, bool i2s_ok);

    /** Convenience: send log line (short text, max 64 chars) */
    void send_log(const char *text);

    /** Convenience: send microphone audio chunk */
    void send_mic_chunk(const int16_t *samples, uint16_t count, uint8_t seq);

    /** Convenience: send audio end marker */
    void send_audio_end();

    /** Convenience: send keypad event */
    void send_keypad_event(char key, uint8_t flags);

    /** Convenience: send system state change */
    void send_system_state(lumi_system_state_t state);

    /** Convenience: send playback complete */
    void send_audio_play_done();

    /** Get statistics */
    uint32_t rx_packets() const { return _rx_packets; }
    uint32_t rx_errors() const { return _rx_errors; }
    uint32_t tx_packets() const { return _tx_packets; }
    uint32_t buffer_overflows() const { return _rx_overflows + _tx_overflows; }

private:
    rx_state_t _rx_state;
    lumi_packet_t _rx_packer;
    uint8_t _rx_payload_pos;
    uint32_t _rx_start_time;

    // Circular buffers using fixed-size arrays
    uint8_t  _tx_buf[LUMI_TX_BUF_SIZE];
    uint16_t _tx_head, _tx_tail;
    volatile uint16_t _tx_count;
    volatile uint16_t _tx_overflows;

    uint8_t  _rx_buf[LUMI_RX_BUF_SIZE];
    volatile uint16_t _rx_head, _rx_tail;
    volatile uint16_t _rx_count;
    volatile uint16_t _rx_overflows;

    uint32_t _rx_packets;
    uint32_t _rx_errors;
    uint32_t _tx_packets;
    uint32_t _checksum_errors;
    uint32_t _framing_errors;

    bool _valid;
    lumi_packet_t _decoded_packet;

    void _parse_rx_byte(uint8_t b);
    bool _enqueue_tx(const void *data, uint16_t len);
    bool _dequeue_tx(void *out, uint16_t maxlen, uint16_t *outlen);
};