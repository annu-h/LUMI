#include "serial_protocol.h"

SerialProtocol::SerialProtocol()
    : _rx_state(RX_STATE_WAIT_SOF0), _rx_payload_pos(0), _rx_start_time(0),
      _tx_head(0), _tx_tail(0), _tx_count(0), _tx_overflows(0),
      _rx_head(0), _rx_tail(0), _rx_count(0), _rx_overflows(0),
      _rx_packets(0), _rx_errors(0), _tx_packets(0),
      _checksum_errors(0), _framing_errors(0), _valid(false) {
    memset(&_rx_packer, 0, sizeof(_rx_packer));
    memset(&_decoded_packet, 0, sizeof(_decoded_packet));
}

SerialProtocol::~SerialProtocol() {
    end();
}

void SerialProtocol::begin(uint32_t baud) {
    Serial.begin(baud);
    // Wait for USB CDC to connect (with short timeout)
    unsigned long start = millis();
    while (!Serial && (millis() - start < 1000)) {
        delay(10);
    }
    _rx_state = RX_STATE_WAIT_SOF0;
    _rx_payload_pos = 0;
    _rx_packets = 0;
    _rx_errors = 0;
    _tx_packets = 0;
}

void SerialProtocol::end() {
    Serial.end();
}

void SerialProtocol::poll_rx() {
    while (Serial.available() > 0) {
        int b = Serial.read();
        if (b < 0) break;
        _parse_rx_byte((uint8_t)b);
    }

    // Flush any pending TX bytes
    flush_tx();
}

void SerialProtocol::_parse_rx_byte(uint8_t b) {
    switch (_rx_state) {
        case RX_STATE_WAIT_SOF0:
            if (b == 0x56) {
                _rx_start_time = micros();
                _rx_state = RX_STATE_WAIT_SOF1;
            }
            break;

        case RX_STATE_WAIT_SOF1:
            if (b == 0xAA) {
                _rx_state = RX_STATE_WAIT_TYPE;
            } else if (b == 0x56) {
                // Stay in SOF1 check
                _rx_state = RX_STATE_WAIT_SOF1;
            } else {
                _rx_state = RX_STATE_WAIT_SOF0;
                _framing_errors++;
            }
            break;

        case RX_STATE_WAIT_TYPE:
            _rx_packer.type = b;
            _rx_state = RX_STATE_WAIT_LEN;
            break;

        case RX_STATE_WAIT_LEN:
            _rx_packer.length = b;
            _rx_payload_pos = 0;
            if (_rx_packer.length == 0) {
                _rx_state = RX_STATE_WAIT_CHECKSUM;
            } else {
                _rx_state = RX_STATE_WAIT_PAYLOAD;
            }
            break;

        case RX_STATE_WAIT_PAYLOAD:
            _rx_packer.payload[_rx_payload_pos++] = b;
            if (_rx_payload_pos >= _rx_packer.length) {
                _rx_state = RX_STATE_WAIT_CHECKSUM;
            }
            break;

        case RX_STATE_WAIT_CHECKSUM: {
            uint8_t expected_cs = lumi_compute_checksum(
                _rx_packer.type, _rx_packer.length, _rx_packer.payload
            );
            if (b == expected_cs) {
                _rx_packer.checksum = b;
                _rx_packer.sof = LUMI_SOF;
                _decoded_packet = _rx_packer;
                _valid = true;
                _rx_packets++;
            } else {
                _checksum_errors++;
                _rx_errors++;
            }
            _rx_state = RX_STATE_WAIT_SOF0;
            break;
        }

        default:
            _rx_state = RX_STATE_WAIT_SOF0;
            break;
    }
}

bool SerialProtocol::get_packet(rx_result_t *result) {
    if (!_valid || result == nullptr) {
        return false;
    }
    result->valid = true;
    result->packet = _decoded_packet;
    result->parse_time_us = micros() - _rx_start_time;
    result->seq_gap = 0;
    _valid = false;
    return true;
}

bool SerialProtocol::queue_tx(const lumi_packet_t *packet) {
    if (packet == nullptr) return false;

    // Wire format: [0x56][0xAA][TYPE][LEN][PAYLOAD...][CHECKSUM]
    uint16_t frame_len = 2 + 1 + 1 + packet->length + 1;
    uint8_t frame[260];

    frame[0] = 0x56;
    frame[1] = 0xAA;
    frame[2] = packet->type;
    frame[3] = packet->length;
    if (packet->length > 0) {
        memcpy(&frame[4], packet->payload, packet->length);
    }
    frame[4 + packet->length] = lumi_compute_checksum(
        packet->type, packet->length, packet->payload
    );

    return _enqueue_tx(frame, frame_len);
}

bool SerialProtocol::_enqueue_tx(const void *data, uint16_t len) {
    const uint8_t *p = (const uint8_t *)data;
    uint16_t free_space = LUMI_TX_BUF_SIZE - _tx_count;
    if (free_space < len) {
        _tx_overflows++;
        return false; // drop packet
    }

    for (uint16_t i = 0; i < len; i++) {
        _tx_buf[_tx_head] = p[i];
        _tx_head = (_tx_head + 1) % LUMI_TX_BUF_SIZE;
    }
    _tx_count += len;
    _tx_packets++;
    return true;
}

void SerialProtocol::flush_tx() {
    while (_tx_count > 0 && Serial.availableForWrite() > 0) {
        uint8_t b = _tx_buf[_tx_tail];
        _tx_tail = (_tx_tail + 1) % LUMI_TX_BUF_SIZE;
        _tx_count--;
        Serial.write(b);
    }
}

void SerialProtocol::send_device_info(uint8_t fw_major, uint8_t fw_minor, uint8_t fw_patch,
                                      const char *board_name, const char *mcu_name,
                                      const lumi_audio_format_t *audio_fmt) {
    lumi_packet_t pkt;
    pkt.type = PKT_DEVICE_INFO;
    uint8_t *p = pkt.payload;

    *p++ = fw_major;
    *p++ = fw_minor;
    *p++ = fw_patch;

    uint8_t board_len = strlen(board_name);
    if (board_len > 31) board_len = 31;
    *p++ = board_len;
    memcpy(p, board_name, board_len);
    p += board_len;

    uint8_t mcu_len = strlen(mcu_name);
    if (mcu_len > 31) mcu_len = 31;
    *p++ = mcu_len;
    memcpy(p, mcu_name, mcu_len);
    p += mcu_len;

    if (audio_fmt) {
        memcpy(p, audio_fmt, sizeof(lumi_audio_format_t));
        p += sizeof(lumi_audio_format_t);
    }

    pkt.length = p - pkt.payload;
    queue_tx(&pkt);
}

void SerialProtocol::send_peripheral_status(bool sd_ok, bool rtc_ok, bool tft_ok, bool i2s_ok) {
    lumi_packet_t pkt;
    pkt.type = PKT_PERIPHERAL_STATUS;
    pkt.length = 4;
    pkt.payload[0] = sd_ok  ? 1 : 0;
    pkt.payload[1] = rtc_ok ? 1 : 0;
    pkt.payload[2] = tft_ok ? 1 : 0;
    pkt.payload[3] = i2s_ok ? 1 : 0;
    queue_tx(&pkt);
}

void SerialProtocol::send_log(const char *text) {
    if (!text) return;
    lumi_packet_t pkt;
    pkt.type = PKT_LOG;
    uint8_t len = strlen(text);
    if (len > 64) len = 64;
    pkt.length = len;
    memcpy(pkt.payload, text, len);
    queue_tx(&pkt);
}

void SerialProtocol::send_mic_chunk(const int16_t *samples, uint16_t count, uint8_t seq) {
    if (!samples || count == 0) return;
    lumi_packet_t pkt;
    pkt.type = PKT_AUDIO_MIC_CHUNK;

    // Payload: [SEQ:1B][SAMPLES:count*2 bytes]
    pkt.payload[0] = seq;
    uint16_t max_samples = (LUMI_MAX_PAYLOAD - 1) / 2;
    uint16_t n = (count > max_samples) ? max_samples : count;
    memcpy(&pkt.payload[1], samples, n * sizeof(int16_t));
    pkt.length = 1 + n * sizeof(int16_t);

    queue_tx(&pkt);
}

void SerialProtocol::send_audio_end() {
    lumi_packet_t pkt;
    pkt.type = PKT_AUDIO_MIC_END;
    pkt.length = 0;
    queue_tx(&pkt);
}

void SerialProtocol::send_keypad_event(char key, uint8_t flags) {
    lumi_packet_t pkt;
    pkt.type = PKT_KEYPAD_EVENT;
    pkt.length = 2;
    pkt.payload[0] = (uint8_t)key;
    pkt.payload[1] = flags;
    queue_tx(&pkt);
}

void SerialProtocol::send_system_state(lumi_system_state_t state) {
    lumi_packet_t pkt;
    pkt.type = PKT_SYSTEM_STATE;
    pkt.length = 1;
    pkt.payload[0] = (uint8_t)state;
    queue_tx(&pkt);
}

void SerialProtocol::send_audio_play_done() {
    lumi_packet_t pkt;
    pkt.type = PKT_AUDIO_PLAY_DONE;
    pkt.length = 0;
    queue_tx(&pkt);
}
