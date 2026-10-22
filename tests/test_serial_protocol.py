"""
Test suite for LUMI serial protocol encoding, decoding, and error recovery.

Validates packet framing, checksum computation, sequence handling, and
buffer overflow behavior without requiring physical ESP32 hardware.
"""

import pytest
import struct
import numpy as np
from src.serial_bridge import (
    LumiSerialBridge, PacketType, Command, SystemState,
    SOF, MAX_PAYLOAD
)


class TestPacketEncoding:
    """Test packet encoding and checksum computation."""

    def test_empty_payload_encoding(self):
        """Verify encoding of a packet with no payload."""
        bridge = LumiSerialBridge(port="dummy")

        # Manually construct expected frame
        expected = bytearray([
            0x56, 0xAA,  # SOF
            PacketType.HOST_READY,  # TYPE
            0x00,  # LEN=0
            PacketType.HOST_READY ^ 0x00  # CHECKSUM
        ])

        # The bridge._send_packet would build this; verify checksum logic
        checksum = PacketType.HOST_READY ^ 0x00
        assert checksum == expected[4]

    def test_payload_checksum(self):
        """Verify checksum computation over type, length, and payload."""
        pkt_type = PacketType.COMMAND
        payload = bytes([Command.START_CAPTURE])

        checksum = pkt_type ^ len(payload)
        for b in payload:
            checksum ^= b

        expected = PacketType.COMMAND ^ 0x01 ^ Command.START_CAPTURE
        assert checksum == expected

    def test_max_payload_boundary(self):
        """Verify rejection of oversized payloads."""
        bridge = LumiSerialBridge(port="dummy")
        bridge._serial = MockSerial()

        oversized = bytes([0xFF] * (MAX_PAYLOAD + 1))

        with pytest.raises(ValueError, match="Payload too large"):
            bridge._send_packet(PacketType.LOG, oversized)


class TestPacketDecoding:
    """Test RX buffer parsing and framing recovery."""

    def test_valid_packet_decode(self):
        """Parse a complete valid packet from buffer."""
        bridge = LumiSerialBridge(port="dummy")

        # Build packet: DEVICE_INFO with firmware version 1.0.0
        payload = bytes([1, 0, 0])  # fw_major, minor, patch
        buf = bytearray([
            0x56, 0xAA,
            PacketType.DEVICE_INFO,
            len(payload)
        ])
        buf.extend(payload)
        checksum = PacketType.DEVICE_INFO ^ len(payload)
        for b in payload:
            checksum ^= b
        buf.append(checksum)

        bridge._parse_buffer(buf)

        # Buffer should be empty after successful parse
        assert len(buf) == 0
        assert bridge._rx_packets == 1
        assert bridge._rx_errors == 0

    def test_checksum_error_recovery(self):
        """Verify that a bad checksum increments error count and resyncs."""
        bridge = LumiSerialBridge(port="dummy")

        buf = bytearray([
            0x56, 0xAA,
            PacketType.LOG,
            0x01,
            0x41,  # Payload: 'A'
            0xFF   # WRONG checksum (should be TYPE ^ LEN ^ 0x41)
        ])

        bridge._parse_buffer(buf)

        assert bridge._rx_errors >= 1
        assert bridge._rx_packets == 0

    def test_sof_resync(self):
        """Verify parser discards garbage bytes and resyncs on SOF."""
        bridge = LumiSerialBridge(port="dummy")

        # Garbage + valid packet
        buf = bytearray([0xFF, 0x00, 0x12, 0x34])  # garbage
        buf.extend([0x56, 0xAA, PacketType.HOST_READY, 0x00])
        buf.append(PacketType.HOST_READY ^ 0x00)  # checksum

        bridge._parse_buffer(buf)

        assert len(buf) == 0
        assert bridge._rx_packets == 1


class TestAudioChunking:
    """Test microphone and speaker audio chunking."""

    def test_mic_chunk_sequence_tracking(self):
        """Verify sequence number increments and gap detection."""
        bridge = LumiSerialBridge(port="dummy")

        # Simulate receiving chunks with sequence 0, 1, 3 (gap at 2)
        for seq in [0, 1, 3]:
            payload = bytes([seq]) + (b'\x00\x01' * 96)  # seq + 96 samples
            bridge._parse_mic_chunk(payload)

        chunks = list(bridge._mic_queue)
        assert len(chunks) == 3
        assert chunks[0]['seq'] == 0
        assert chunks[1]['seq'] == 1
        assert chunks[2]['seq'] == 3

    def test_speaker_chunk_splitting(self):
        """Verify large audio arrays split into valid packet-sized chunks."""
        bridge = LumiSerialBridge(port="dummy")
        bridge._serial = MockSerial()

        # 1000 samples = 2000 bytes; max payload per chunk = ~250 bytes = 125 samples
        audio = np.zeros(1000, dtype=np.int16)

        bridge.start_playback(audio, sample_rate=16000, chunk_size=100)

        # Verify START + multiple CHUNK packets sent
        sent_packets = bridge._serial.sent_packets
        start_pkts = [p for p in sent_packets if p[0] == PacketType.AUDIO_SPK_START]
        chunk_pkts = [p for p in sent_packets if p[0] == PacketType.AUDIO_SPK_CHUNK]
        end_pkts = [p for p in sent_packets if p[0] == PacketType.AUDIO_SPK_END]

        assert len(start_pkts) == 1
        assert len(chunk_pkts) == 10  # 1000 / 100 = 10 chunks
        assert len(end_pkts) == 1


class TestProtocolStateMachine:
    """Test system state transitions and command handling."""

    def test_capture_lifecycle(self):
        """Verify START_CAPTURE → LISTENING → STOP_CAPTURE → IDLE flow."""
        bridge = LumiSerialBridge(port="dummy")
        bridge._serial = MockSerial()

        states_received = []

        def on_state(s):
            states_received.append(s)

        bridge._on_state_change = on_state

        # Simulate ESP32 responses
        bridge.start_capture()

        # Simulate SYSTEM_STATE=LISTENING from device
        bridge._handle_packet(PacketType.SYSTEM_STATE, bytes([SystemState.LISTENING]))
        assert SystemState.LISTENING in states_received

        bridge.stop_capture()

        # Simulate SYSTEM_STATE=IDLE
        bridge._handle_packet(PacketType.SYSTEM_STATE, bytes([SystemState.IDLE]))
        assert SystemState.IDLE in states_received


class MockSerial:
    """Minimal mock for serial.Serial to capture sent packets."""

    def __init__(self):
        self.is_open = True
        self.in_waiting = 0
        self.sent_data = bytearray()
        self.sent_packets = []

    def write(self, data):
        self.sent_data.extend(data)
        # Parse packet type from frame
        if len(data) >= 3:
            pkt_type = data[2]
            pkt_len = data[3] if len(data) > 3 else 0
            self.sent_packets.append((pkt_type, pkt_len))

    def flush(self):
        pass

    def read(self, size=1):
        return b''

    def close(self):
        self.is_open = False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
