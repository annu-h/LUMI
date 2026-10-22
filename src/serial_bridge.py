"""
LUMI Serial Bridge — USB-Serial communication with ESP32 firmware.

Implements the binary protocol defined in firmware/include/lumi_protocol.h.

Usage:
    bridge = LumiSerialBridge(port="COM3", baud=115200)
    bridge.connect()

    # Send command
    bridge.start_capture()

    # Receive mic audio
    for chunk in bridge.iter_mic_chunks(timeout_s=5.0):
        audio_data = chunk['samples']  # np.ndarray int16
        process_audio(audio_data)

    bridge.stop_capture()

    # Send speaker audio
    bridge.start_playback(audio_pcm, sample_rate=16000)
    bridge.wait_playback_done(timeout_s=10.0)
"""

import logging
import struct
import time
import threading
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional, Iterator, Callable
from collections import deque

import numpy as np
import serial

logger = logging.getLogger(__name__)

# Protocol constants
SOF = 0x56AA
PROTOCOL_VERSION = (1, 0, 0)
MAX_PAYLOAD = 255

class PacketType(IntEnum):
    # Device → Host
    DEVICE_INFO = 0x01
    PERIPHERAL_STATUS = 0x02
    LOG = 0x03
    AUDIO_MIC_CHUNK = 0x04
    AUDIO_MIC_END = 0x05
    KEYPAD_EVENT = 0x06
    SYSTEM_STATE = 0x07
    AUDIO_PLAY_DONE = 0x08
    RTC_TIME = 0x09

    # Host → Device
    HOST_READY = 0x10
    AUDIO_SPK_START = 0x11
    AUDIO_SPK_CHUNK = 0x12
    AUDIO_SPK_END = 0x13
    COMMAND = 0x14
    UTTERANCE_END = 0x15
    LED_CONTROL = 0x16

class Command(IntEnum):
    NOOP = 0x00
    START_CAPTURE = 0x01
    STOP_CAPTURE = 0x02
    CANCEL_PLAYBACK = 0x03
    GET_STATUS = 0x04
    SET_MODE = 0x05

class SystemState(IntEnum):
    BOOT = 0x00
    READY = 0x01
    IDLE = 0x02
    LISTENING = 0x03
    PROCESSING = 0x04
    SPEAKING = 0x05
    ERROR = 0x06

@dataclass
class DeviceInfo:
    fw_version: tuple[int, int, int]
    board: str
    mcu: str
    sample_rate: int
    channels: int
    bits_per_sample: int

@dataclass
class PeripheralStatus:
    sd_ok: bool
    rtc_ok: bool
    tft_ok: bool
    i2s_ok: bool

class LumiSerialBridge:
    def __init__(self, port: str = "COM3", baud: int = 115200,
                 on_log: Optional[Callable[[str], None]] = None,
                 on_keypad: Optional[Callable[[str], None]] = None,
                 on_state_change: Optional[Callable[[SystemState], None]] = None):
        self.port = port
        self.baud = baud
        self._serial: Optional[serial.Serial] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._running = False

        self._device_info: Optional[DeviceInfo] = None
        self._peripheral_status: Optional[PeripheralStatus] = None

        self._mic_queue: deque = deque(maxlen=100)
        self._playback_done_event = threading.Event()
        self._last_system_state: Optional[SystemState] = None

        self._on_log = on_log or (lambda msg: logger.info("ESP32: %s", msg))
        self._on_keypad = on_keypad
        self._on_state_change = on_state_change

        self._rx_packets = 0
        self._rx_errors = 0
        self._tx_packets = 0

        self._lock = threading.Lock()

    def connect(self, timeout_s: float = 3.0) -> bool:
        """Open serial port, start RX thread, perform handshake."""
        try:
            self._serial = serial.Serial(self.port, self.baud, timeout=0.1)
            time.sleep(0.5)  # Allow ESP32 to boot

            self._running = True
            self._rx_thread = threading.Thread(target=self._rx_worker, daemon=True)
            self._rx_thread.start()

            # Send HOST_READY handshake
            self._send_packet(PacketType.HOST_READY, b'')

            # Wait for DEVICE_INFO
            deadline = time.monotonic() + timeout_s
            while time.monotonic() < deadline:
                if self._device_info is not None:
                    logger.info("Connected to LUMI firmware v%d.%d.%d on %s",
                               *self._device_info.fw_version, self._device_info.board)
                    return True
                time.sleep(0.05)

            logger.warning("Handshake timeout — device may not be running LUMI firmware")
            return False

        except Exception as e:
            logger.error("Failed to connect: %s", e)
            self.disconnect()
            return False

    def disconnect(self):
        """Close serial port and stop RX thread."""
        self._running = False
        if self._rx_thread and self._rx_thread.is_alive():
            self._rx_thread.join(timeout=1.0)
        if self._serial and self._serial.is_open:
            self._serial.close()
        self._serial = None

    def start_capture(self):
        """Begin microphone capture on the ESP32."""
        self._mic_queue.clear()
        self._send_command(Command.START_CAPTURE)

    def stop_capture(self):
        """Stop microphone capture."""
        self._send_command(Command.STOP_CAPTURE)

    def iter_mic_chunks(self, timeout_s: float = 10.0) -> Iterator[dict]:
        """Iterate microphone audio chunks until END marker or timeout.

        Yields:
            dict with keys:
                - 'samples': np.ndarray of int16 PCM samples
                - 'seq': sequence number (mod 256)
                - 'timestamp': receive timestamp
        """
        deadline = time.monotonic() + timeout_s
        last_seq = None

        while time.monotonic() < deadline:
            if len(self._mic_queue) > 0:
                chunk = self._mic_queue.popleft()
                if chunk is None:  # END marker
                    return

                # Check for sequence gaps
                if last_seq is not None:
                    expected = (last_seq + 1) % 256
                    if chunk['seq'] != expected:
                        gap = (chunk['seq'] - expected) % 256
                        logger.warning("Mic sequence gap: expected %d, got %d (gap=%d)",
                                      expected, chunk['seq'], gap)
                last_seq = chunk['seq']

                yield chunk
                deadline = time.monotonic() + timeout_s  # extend deadline
            else:
                time.sleep(0.01)

    def start_playback(self, audio: np.ndarray, sample_rate: int = 16000, chunk_size: int = 192):
        """Send PCM audio to ESP32 speaker (blocking until all chunks sent)."""
        if audio.dtype != np.int16:
            audio = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)

        total_samples = len(audio)
        self._playback_done_event.clear()

        # Send START with total sample count
        payload = struct.pack('<I', total_samples)
        self._send_packet(PacketType.AUDIO_SPK_START, payload)

        # Send chunks
        pos = 0
        while pos < total_samples:
            end = min(pos + chunk_size, total_samples)
            chunk = audio[pos:end]
            self._send_packet(PacketType.AUDIO_SPK_CHUNK, chunk.tobytes())
            pos = end
            time.sleep(0.002)  # Flow control

        # Send END
        self._send_packet(PacketType.AUDIO_SPK_END, b'')

    def wait_playback_done(self, timeout_s: float = 10.0) -> bool:
        """Wait for AUDIO_PLAY_DONE packet from device."""
        return self._playback_done_event.wait(timeout=timeout_s)

    def send_utterance_end(self):
        """Signal that the Python host has finished speaking."""
        self._send_packet(PacketType.UTTERANCE_END, b'')

    def set_led(self, on: bool):
        """Control the status LED."""
        self._send_packet(PacketType.LED_CONTROL, bytes([1 if on else 0]))

    def get_status(self) -> Optional[PeripheralStatus]:
        """Request and return peripheral status."""
        self._send_command(Command.GET_STATUS)
        time.sleep(0.1)
        return self._peripheral_status

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        return self._device_info

    @property
    def is_connected(self) -> bool:
        return self._serial is not None and self._serial.is_open

    # -------------------------------------------------------------------------
    # Private methods
    # -------------------------------------------------------------------------

    def _send_command(self, cmd: Command):
        self._send_packet(PacketType.COMMAND, bytes([cmd]))

    def _send_packet(self, pkt_type: PacketType, payload: bytes):
        if not self._serial or not self._serial.is_open:
            raise RuntimeError("Serial port not open")

        if len(payload) > MAX_PAYLOAD:
            raise ValueError(f"Payload too large: {len(payload)} > {MAX_PAYLOAD}")

        # Build packet: SOF(2) TYPE(1) LEN(1) PAYLOAD(...) CHECKSUM(1)
        frame = bytearray()
        frame.append(0x56)  # SOF low
        frame.append(0xAA)  # SOF high
        frame.append(pkt_type)
        frame.append(len(payload))
        frame.extend(payload)

        # Checksum over TYPE, LEN, PAYLOAD
        checksum = 0
        for b in frame[2:]:
            checksum ^= b
        frame.append(checksum)

        with self._lock:
            self._serial.write(frame)
            self._tx_packets += 1

    def _rx_worker(self):
        """Background thread that reads and parses packets."""
        rx_buf = bytearray()

        while self._running:
            try:
                if self._serial and self._serial.in_waiting > 0:
                    data = self._serial.read(self._serial.in_waiting or 1)
                    rx_buf.extend(data)
                    self._parse_buffer(rx_buf)
                else:
                    time.sleep(0.01)
            except Exception as e:
                logger.error("RX worker error: %s", e)
                time.sleep(0.1)

    def _parse_buffer(self, buf: bytearray):
        """Parse complete packets from buffer."""
        while len(buf) >= 5:  # Minimum: SOF(2) + TYPE(1) + LEN(1) + CHECKSUM(1)
            # Search for SOF
            idx = -1
            for i in range(len(buf) - 1):
                if buf[i] == 0x56 and buf[i+1] == 0xAA:
                    idx = i
                    break

            if idx < 0:
                buf.clear()
                return

            if idx > 0:
                buf[:] = buf[idx:]  # Discard bytes before SOF

            if len(buf) < 5:
                return  # Wait for more data

            pkt_type = buf[2]
            pkt_len = buf[3]
            frame_len = 5 + pkt_len  # SOF(2) + TYPE + LEN + PAYLOAD + CHECKSUM

            if len(buf) < frame_len:
                return  # Wait for complete packet

            # Verify checksum
            checksum_computed = 0
            for b in buf[2:4+pkt_len]:
                checksum_computed ^= b
            checksum_received = buf[4 + pkt_len]

            if checksum_computed != checksum_received:
                self._rx_errors += 1
                logger.warning("Checksum error: computed=0x%02X received=0x%02X",
                              checksum_computed, checksum_received)
                buf[:] = buf[2:]  # Skip SOF, try to resync
                continue

            # Extract payload
            payload = bytes(buf[4:4+pkt_len])
            self._rx_packets += 1

            # Dispatch
            try:
                self._handle_packet(PacketType(pkt_type), payload)
            except Exception as e:
                logger.error("Packet handler error (type=0x%02X): %s", pkt_type, e)

            # Remove processed packet
            buf[:] = buf[frame_len:]

    def _handle_packet(self, pkt_type: PacketType, payload: bytes):
        if pkt_type == PacketType.DEVICE_INFO:
            self._parse_device_info(payload)
        elif pkt_type == PacketType.PERIPHERAL_STATUS:
            self._parse_peripheral_status(payload)
        elif pkt_type == PacketType.LOG:
            text = payload.decode('utf-8', errors='replace')
            self._on_log(text)
        elif pkt_type == PacketType.AUDIO_MIC_CHUNK:
            self._parse_mic_chunk(payload)
        elif pkt_type == PacketType.AUDIO_MIC_END:
            self._mic_queue.append(None)  # END marker
        elif pkt_type == PacketType.KEYPAD_EVENT:
            if len(payload) >= 1:
                key_char = chr(payload[0])
                if self._on_keypad:
                    self._on_keypad(key_char)
        elif pkt_type == PacketType.SYSTEM_STATE:
            if len(payload) >= 1:
                state = SystemState(payload[0])
                self._last_system_state = state
                if self._on_state_change:
                    self._on_state_change(state)
        elif pkt_type == PacketType.AUDIO_PLAY_DONE:
            self._playback_done_event.set()

    def _parse_device_info(self, payload: bytes):
        if len(payload) < 3:
            return
        fw_major, fw_minor, fw_patch = payload[0], payload[1], payload[2]
        offset = 3

        # Parse board name
        if offset >= len(payload):
            return
        board_len = payload[offset]
        offset += 1
        board = payload[offset:offset+board_len].decode('utf-8', errors='replace')
        offset += board_len

        # Parse MCU name
        if offset >= len(payload):
            return
        mcu_len = payload[offset]
        offset += 1
        mcu = payload[offset:offset+mcu_len].decode('utf-8', errors='replace')
        offset += mcu_len

        # Parse audio format (4 bytes)
        sample_rate = 16000
        channels = 1
        bits_per_sample = 16
        if offset + 4 <= len(payload):
            sr_div = payload[offset]
            channels = payload[offset+1]
            bits_per_sample = payload[offset+2]
            sample_rate = sr_div * 1000

        self._device_info = DeviceInfo(
            fw_version=(fw_major, fw_minor, fw_patch),
            board=board, mcu=mcu,
            sample_rate=sample_rate, channels=channels,
            bits_per_sample=bits_per_sample
        )

    def _parse_peripheral_status(self, payload: bytes):
        if len(payload) >= 4:
            self._peripheral_status = PeripheralStatus(
                sd_ok=bool(payload[0]),
                rtc_ok=bool(payload[1]),
                tft_ok=bool(payload[2]),
                i2s_ok=bool(payload[3])
            )

    def _parse_mic_chunk(self, payload: bytes):
        if len(payload) < 1:
            return
        seq = payload[0]
        pcm_bytes = payload[1:]
        samples = np.frombuffer(pcm_bytes, dtype=np.int16)

        self._mic_queue.append({
            'samples': samples,
            'seq': seq,
            'timestamp': time.monotonic()
        })
