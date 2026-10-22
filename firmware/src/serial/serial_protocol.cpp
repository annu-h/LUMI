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
                _framing_errors++;
                _rx_state = RX_STATE_WAIT_SOF0;
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
            } else if (_rx_packer.length > LUMI_MAX_PAYLOAD) {
                _rx_errors++;
                _rx_state = RX_STATE_WAIT_SOF0; // payload too large
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
            // Checksum computed over type, length, and payload
            uint8_t check_buf[2 + LUMI_MAX_PAYLOAD];
            check_buf[0] = _rx_packer.type;
            check_buf[1] = _rx_packer.length;
            if (_rx_packer.length > 0) {
                memcpy(&check_buf[2], _rx_packer.payload, _rx_packer.length);
            }
            uint8_t expected = lumi_checksum(check_buf, 2 + _rx_packer.length);

            if (b == expected) {
                _rx_packer.sof = 0x56AA;
                _rx_packer.checksum = b;
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
    }
}

bool SerialProtocol::get_packet(rx_result_t *result) {
    if (!_valid) return false;
    if (result != nullptr) {
        result->valid = true;
        result->packet = _decoded_packet;
        result->parse_time_us = micros();
        result->seq_gap = 0;
    }
    _valid = false;
    return true;
}

bool SerialProtocol::queue_tx(const lumi_packet_t *packet) {
    uint8_t raw[LUMI_MAX_PAYLOAD + 8];
    raw[0] = 0x56;
    raw[1] = 0xAA;
    raw[2] = packet->type;
    raw[3] = packet->length;
    if (packet->length > 0) {
        memcpy(&raw[4], packet->payload, packet->length);
    }
    // Checksum over type, length, payload
    raw[4 + packet->length] = lumi_checksum(&raw[2], 2 + packet->length);
    uint16_t total_len = 5 + packet->length;

    return _enqueue_tx(raw, total_len);
}

void SerialProtocol::flush_tx() {
    // Write out all queued TX bytes to hardware Serial non-blocking
    uint8_t chunk[64];
    uint16_t len = 0;
    while (_dequeue_tx(chunk, sizeof(chunk), &len) && len > 0) {
        Serial.write(chunk, len);
        _tx_packets++;
    }
    Serial.flush();
}

bool SerialProtocol::_enqueue_tx(const void *data, uint16_t len) {
    const uint8_t *bytes = (const uint8_t*)data;
    for (uint16_t i = 0; i < len; i++) {
        uint16_t next_head = (_tx_head + 1) % LUMI_TX_BUF_SIZE;
        if (next_head == _tx_tail) {
            _tx_overflows++;
            return false; // buffer full
        }
        _tx_buf[_tx_head] = bytes[i];
        _tx_head = next_head;
        _tx_count++;
    }
    return true;
}

bool SerialProtocol::_dequeue_tx(void *out, uint16_t maxlen, uint16_t *outlen) {
    if (_tx_head == _tx_tail) {
        *outlen = 0;
        return false;
    }
    uint8_t *bytes = (uint8_t*)out;
    uint16_t count = 0;
    while (_tx_head != _tx_tail && count < maxlen) {
        bytes[count++] = _tx_buf[_tx_tail];
        _tx_tail = (_tx_tail + 1) % LUMI_TX_BUF_SIZE;
        _tx_count--;
    }
    *outlen = count;
    return true;
}

/* Convenience helpers */

void SerialProtocol::send_device_info(uint8_t fw_major, uint8_t fw_minor, uint8_t fw_patch,
                                      const char *board_name, const char *mcu_name,
                                      const lumi_audio_format_t *audio_fmt) {
    lumi_packet_t pkt;
    pkt.type = PKT_DEVICE_INFO;
    uint8_t *p = pkt.payload;
    p[0] = fw_major;
    p[1] = fw_minor;
    p[2] = fw_patch;

    // Copy board name (max 20 chars)
    size_t b_len = strlen(board_name);
    if (b_len > 19) b_len = 19;
    p[3] = (uint8_t)b_len;
    memcpy(&p[4], board_name, b_len);
    size_t offset = 4 + b_len;

    // Copy MCU name
    size_t m_len = strlen(mcu_name);
    if (m_len > 19) m_len = 19;
    p[offset++] = (uint8_t)m_len;
    memcpy(&p[offset], mcu_name, m_len);
    offset += m_len;

    // Copy audio format
    if (audio_fmt != nullptr) {
        memcpy(&p[offset], audio_fmt, sizeof(lumi_audio_format_t));
        offset += sizeof(lumi_audio_format_t);
    }

    pkt.length = (uint8_t)offset;
    queue_tx(&pkt);
}

void SerialProtocol::send_peripheral_status(bool sd_ok, bool rtc_ok, bool tft_ok, bool i2s_ok) {
    lumi_packet_t pkt;
    pkt.type = PKT_PERIPHERAL_STATUS;
    pkt.length = 4;
    pkt.payload[0] = sd_ok ? 1 : 0;
    pkt.payload[1] = rtc_ok ? 1 : 0;
    pkt.payload[2] = tft_ok ? 1 : 0;
    pkt.payload[3] = i2s_ok ? 1 : 0;
    queue_tx(&pkt);
}

void SerialProtocol::send_log(const char *text) {
    lumi_packet_t pkt;
    pkt.type = PKT_LOG;
    size_t len = strlen(text);
    if (len > LUMI_MAX_PAYLOAD) len = LUMI_MAX_PAYLOAD;
    pkt.length = (uint8_t)len;
    memcpy(pkt.payload, text, len);
    queue_tx(&pkt);
}

void SerialProtocol::send_mic_chunk(const int16_t *samples, uint16_t count, uint8_t seq) {
    lumi_packet_t pkt;
    pkt.type = PKT_AUDIO_MIC_CHUNK;
    // Payload: [seq_number:1B] [pcm_data...]
    pkt.payload[0] = seq;
    uint16_t byte_len = count * sizeof(int16_t);
    if (byte_len > (LUMI_MAX_PAYLOAD - 1)) {
        byte_len = LUMI_MAX_PAYLOAD - 1;
        count = byte_len / 2;
    }
    memcpy(&pkt.payload[1], samples, byte_len);
    pkt.length = (uint8_t)(1 + byte_len);
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
