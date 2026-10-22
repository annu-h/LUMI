/**
 * @file lumi_protocol.h
 * @brief Binary USB-Serial Protocol definitions for Project LUMI.
 *
 * Wire format (little-endian):
 *
 *   [0xAA] [0x56] [TYPE:1B] [LEN:1B] [PAYLOAD...up to 255B] [CHECKSUM:1B]
 *
 *   - SOF:      0xAA56 (start of frame marker)
 *   - TYPE:     packet type enum (see lumi_packet_type_t)
 *   - LEN:      payload length in bytes (0-255)
 *   - PAYLOAD:  type-dependent data
 *   - CHECKSUM: XOR of all preceding bytes (SOF bytes excluded)
 *
 * Framing notes:
 *   - Audio payloads larger than max frame size are sent as a sequence of
 *     PKT_AUDIO_MIC_CHUNK frames. Firmware uses a rolling sequence number
 *     (mod 256) embedded as the first payload byte to allow gap detection.
 *   - A PKT_AUDIO_MIC_END frame signals end-of-utterance with no payload
 *     (LEN=0).
 *   - Diagnostic text uses PKT_LOG (separate channel from binary audio).
 */

#ifndef LUMI_PROTOCOL_H
#define LUMI_PROTOCOL_H

#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Protocol constants */
#define LUMI_SOF            0x56AA        /* Start-of-frame marker (little-endian on wire) */
#define LUMI_PROTOCOL_VERSION_MAJOR  1
#define LUMI_PROTOCOL_VERSION_MINOR  0
#define LUMI_PROTOCOL_VERSION_PATCH  0

/** Max payload per packet (fits in 1-byte length field) */
#define LUMI_MAX_PAYLOAD    255

/** Max audio samples per chunk packet (16-bit = 2 bytes each) */
#define LUMI_AUDIO_CHUNK_SAMPLES  192   /* 12 ms at 16 kHz */

/** Handshake timeout for initial version exchange (ms) */
#define LUMI_HANDSHAKE_TIMEOUT_MS  2000

/**
 * Packet type enum — identifies the command or telemetry message.
 * Values fit in a single byte.
 */
typedef enum {
    /* --- Device → Host (device is ESP32) --- */
    PKT_DEVICE_INFO        = 0x01, /* Capabilities, versions, pin map summary     */
    PKT_PERIPHERAL_STATUS  = 0x02, /* Per-peripheral init status                   */
    PKT_LOG                = 0x03, /* Diagnostic text log line                     */
    PKT_AUDIO_MIC_CHUNK    = 0x04, /* Microphone PCM chunk (16-bit LE int samples)   */
    PKT_AUDIO_MIC_END      = 0x05, /* End-of-utterance marker                      */
    PKT_KEYPAD_EVENT       = 0x06, /* Keypad key press/release                     */
    PKT_SYSTEM_STATE       = 0x07, /* System state change (IDLE, LISTENING, etc.)  */
    PKT_AUDIO_PLAY_DONE    = 0x08, /* Speaker playback completed                   */
    PKT_RTC_TIME           = 0x09, /* RTC date/time snapshot                        */

    /* --- Host → Device (host is Python) --- */
    PKT_HOST_READY         = 0x10, /* Host handshake / ready to receive            */
    PKT_AUDIO_SPK_START    = 0x11, /* Begin speaker playback (header: sample count) */
    PKT_AUDIO_SPK_CHUNK    = 0x12, /* Speaker PCM chunk                            */
    PKT_AUDIO_SPK_END      = 0x13, /* End speaker playback                         */
    PKT_COMMAND            = 0x14, /* Generic command (e.g. START_CAPTURE)         */
    PKT_UTTERANCE_END      = 0x15, /* Tell ESP32 the Python side has spoken        */
    PKT_LED_CONTROL        = 0x16, /* Override LED state                            */

    /* Reserved range */
    PKT_RESERVED_0 = 0xE0,
} lumi_packet_type_t;

/**
 * Command opcodes for PKT_COMMAND payload byte 0.
 */
typedef enum {
    CMD_NOOP           = 0x00,
    CMD_START_CAPTURE  = 0x01,  /* Begin microphone capture                   */
    CMD_STOP_CAPTURE   = 0x02,  /* Stop microphone capture immediately        */
    CMD_CANCEL_PLAYBACK = 0x03,  /* Abort current speaker playback             */
    CMD_GET_STATUS     = 0x04,  /* Request fresh PERIPHERAL_STATUS from device */
    CMD_SET_MODE       =0x05,  /* Set capture mode (0=half-duplex, 1=wake-stream) */
} lumi_command_t;

/**
 * System states reported in PKT_SYSTEM_STATE.
 */
typedef enum {
    STATE_BOOT         = 0x00,
    STATE_READY        = 0x01,
    STATE_IDLE         = 0x02,
    STATE_LISTENING    = 0x03,
    STATE_PROCESSING   = 0x04,
    STATE_SPEAKING     = 0x05,
    STATE_ERROR        = 0x06,
} lumi_system_state_t;

/**
 * Keypad flags byte for PKT_KEYPAD_EVENT payload.
 */
#define LUMI_KEY_FLAG_PRESS   0x00
#define LUMI_KEY_FLAG_RELEASE 0x01

/**
 * Audio format descriptor used in PKT_DEVICE_INFO and
 * PKT_AUDIO_SPK_START.  Packed for compact wire representation.
 */
typedef struct {
    uint8_t  sample_rate_hz_div_1000;  /* 16 = 16000 Hz                              */
    uint8_t  channels;                  /* 1 = mono                                   */
    uint8_t  bits_per_sample;           /* 16                                         */
    uint8_t  format;                    /* 0 = signed 16-bit LE PCM                   */
} lumi_audio_format_t;

/**
 * Full wire-frame packet buffer.
 * The payload is stored inline so the whole buffer can be transmitted
 * in a single write() call.
 */
typedef struct {
    uint16_t sof;          /* 0x56AA                                            */
    uint8_t  type;         /* lumi_packet_type_t                                */
    uint8_t  length;       /* payload bytes following                           */
    uint8_t  payload[LUMI_MAX_PAYLOAD + 4]; /* +4 for alignment of audio chunks */
    uint8_t  checksum;     /* XOR of bytes [1..(3+length)]                      */
} lumi_packet_t;

/** Compute XOR checksum over a raw byte buffer (excludes SOF). */
static inline uint8_t lumi_checksum(const uint8_t *buf, size_t len) {
    uint8_t sum = 0;
    for (size_t i = 0; i < len; i++) {
        sum ^= buf[i];
    }
    return sum;
}

/**
 * Convenience: serialize a packet into a byte buffer ready for write().
 * Returns total wire length (sof_hi, sof_lo, type, len, payload..., checksum).
 */
static inline uint16_t lumi_serialize(lumi_packet_t *pkt, uint8_t *out) {
    out[0] = 0x56;  /* SOF low byte */
    out[1] = 0xAA;  /* SOF high byte */
    out[2] = pkt->type;
    out[3] = pkt->length;
    if (pkt->length && pkt->payload) {
        memcpy(out + 4, pkt->payload, pkt->length);
    }
    out[4 + pkt->length] = lumi_checksum(&out[2], 2 + pkt->length);
    return (uint16_t)(5 + pkt->length);
}

#ifdef __cplusplus
}
#endif

#endif /* LUMI_PROTOCOL_H */
