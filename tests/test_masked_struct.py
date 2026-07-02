from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

from harp.protocol import MessageType, PayloadType
from harp.protocol.message import HarpMessage
from harp.protocol.registers import (
    RegisterAccess,
    RegisterBase,
    StructPayload,
    payload_field,
)

# ---------------------------------------------------------------------------
# Overlapping masks on one U16 word (like StartPulse from protocol spec)
# ---------------------------------------------------------------------------


class PwmPort(IntEnum):
    PWM0 = 0
    PWM1 = 1
    PWM2 = 2
    PWM3 = 3


@dataclass
class StartPulsePayload(StructPayload):
    pulse_width: int = payload_field(PayloadType.U16, offset=0, mask=0x03FF)
    digital_output: PwmPort = payload_field(
        PayloadType.U16, offset=0, mask=0x0C00, interface_type=PwmPort
    )


class StartPulse(RegisterBase[StartPulsePayload]):
    address = 100
    access = RegisterAccess.WRITABLE


class TestOverlappingMasksSingleWord:
    def test_roundtrip(self):
        payload = StartPulsePayload(pulse_width=500, digital_output=PwmPort.PWM2)
        msg = StartPulse.format(payload, MessageType.WRITE)
        result = StartPulse.parse(msg)
        assert result.pulse_width == 500
        assert result.digital_output == PwmPort.PWM2
        assert isinstance(result.digital_output, PwmPort)

    def test_each_port(self):
        for port in PwmPort:
            payload = StartPulsePayload(pulse_width=100, digital_output=port)
            msg = StartPulse.format(payload, MessageType.WRITE)
            result = StartPulse.parse(msg)
            assert result.digital_output == port
            assert result.pulse_width == 100

    def test_encoded_bits(self):
        payload = StartPulsePayload(pulse_width=0x1FF, digital_output=PwmPort.PWM3)
        encoded = StartPulse.encode(payload)
        raw_u16 = encoded[0]
        assert raw_u16 & 0x03FF == 0x1FF
        assert (raw_u16 & 0x0C00) >> 10 == 3

    def test_max_pulse_width(self):
        payload = StartPulsePayload(pulse_width=0x3FF, digital_output=PwmPort.PWM0)
        msg = StartPulse.format(payload, MessageType.WRITE)
        result = StartPulse.parse(msg)
        assert result.pulse_width == 0x3FF
        assert result.digital_output == PwmPort.PWM0

    def test_zero_values(self):
        payload = StartPulsePayload(pulse_width=0, digital_output=PwmPort.PWM0)
        msg = StartPulse.format(payload, MessageType.WRITE)
        result = StartPulse.parse(msg)
        assert result.pulse_width == 0
        assert result.digital_output == PwmPort.PWM0


# ---------------------------------------------------------------------------
# Multi-word masked struct (like StartPulseTrain: 4 masks across 2 U16 words)
# ---------------------------------------------------------------------------


@dataclass
class StartPulseTrainPayload(StructPayload):
    pulse_width: int = payload_field(PayloadType.U16, offset=0, mask=0x03FF)
    digital_output: PwmPort = payload_field(
        PayloadType.U16, offset=0, mask=0x0C00, interface_type=PwmPort
    )
    pulse_count: int = payload_field(PayloadType.U16, offset=2, mask=0x00FF, interface_type=int)
    frequency: int = payload_field(PayloadType.U16, offset=2, mask=0xFF00, interface_type=int)


class StartPulseTrain(RegisterBase[StartPulseTrainPayload]):
    address = 101
    access = RegisterAccess.WRITABLE


class TestMultiWordMaskedStruct:
    def test_roundtrip(self):
        payload = StartPulseTrainPayload(
            pulse_width=200,
            digital_output=PwmPort.PWM1,
            pulse_count=10,
            frequency=50,
        )
        msg = StartPulseTrain.format(payload, MessageType.WRITE)
        result = StartPulseTrain.parse(msg)
        assert result.pulse_width == 200
        assert result.digital_output == PwmPort.PWM1
        assert result.pulse_count == 10
        assert result.frequency == 50

    def test_boundary_values(self):
        payload = StartPulseTrainPayload(
            pulse_width=0x3FF,
            digital_output=PwmPort.PWM3,
            pulse_count=0xFF,
            frequency=0xFF,
        )
        msg = StartPulseTrain.format(payload, MessageType.WRITE)
        result = StartPulseTrain.parse(msg)
        assert result.pulse_width == 0x3FF
        assert result.digital_output == PwmPort.PWM3
        assert result.pulse_count == 0xFF
        assert result.frequency == 0xFF

    def test_encoded_word_layout(self):
        payload = StartPulseTrainPayload(
            pulse_width=0x1AB,
            digital_output=PwmPort.PWM2,
            pulse_count=0x34,
            frequency=0x56,
        )
        encoded = StartPulseTrain.encode(payload)
        word0 = encoded[0]
        word1 = encoded[1]
        assert word0 & 0x03FF == 0x1AB
        assert (word0 & 0x0C00) >> 10 == 2
        assert word1 & 0x00FF == 0x34
        assert (word1 & 0xFF00) >> 8 == 0x56

    def test_from_bytes_roundtrip(self):
        payload = StartPulseTrainPayload(
            pulse_width=300,
            digital_output=PwmPort.PWM0,
            pulse_count=5,
            frequency=100,
        )
        msg = StartPulseTrain.format(payload, MessageType.WRITE)
        reconstructed = HarpMessage.from_bytes(msg.to_bytes())
        result = StartPulseTrain.parse(reconstructed)
        assert result.pulse_width == 300
        assert result.digital_output == PwmPort.PWM0
        assert result.pulse_count == 5
        assert result.frequency == 100

    def test_register_attributes(self):
        assert StartPulseTrain.payload_type == PayloadType.U16
        assert StartPulseTrain.count == 2


# ---------------------------------------------------------------------------
# Bool mask field via StructPayload (bit flag within a word)
# ---------------------------------------------------------------------------


@dataclass
class StatusPayload(StructPayload):
    value: int = payload_field(PayloadType.U16, offset=0, mask=0x0FFF, interface_type=int)
    overflow: bool = payload_field(PayloadType.U16, offset=0, mask=0x1000, interface_type=bool)
    valid: bool = payload_field(PayloadType.U16, offset=0, mask=0x2000, interface_type=bool)


class StatusReg(RegisterBase[StatusPayload]):
    address = 102
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL


class TestBoolMaskField:
    def test_roundtrip_all_false(self):
        payload = StatusPayload(value=100, overflow=False, valid=False)
        msg = StatusReg.format(payload, MessageType.WRITE)
        result = StatusReg.parse(msg)
        assert result.value == 100
        assert result.overflow is False
        assert result.valid is False

    def test_roundtrip_all_true(self):
        payload = StatusPayload(value=0xFFF, overflow=True, valid=True)
        msg = StatusReg.format(payload, MessageType.WRITE)
        result = StatusReg.parse(msg)
        assert result.value == 0xFFF
        assert result.overflow is True
        assert result.valid is True

    def test_independent_flags(self):
        for overflow in (True, False):
            for valid in (True, False):
                payload = StatusPayload(value=42, overflow=overflow, valid=valid)
                msg = StatusReg.format(payload, MessageType.WRITE)
                result = StatusReg.parse(msg)
                assert result.overflow is overflow
                assert result.valid is valid
                assert result.value == 42

    def test_encoded_bits(self):
        payload = StatusPayload(value=0x123, overflow=True, valid=False)
        encoded = StatusReg.encode(payload)
        raw = encoded[0]
        assert raw & 0x0FFF == 0x123
        assert bool(raw & 0x1000) is True
        assert bool(raw & 0x2000) is False


# ---------------------------------------------------------------------------
# Mixed: masked fields + plain fields in same struct (mask at some offsets)
# ---------------------------------------------------------------------------


@dataclass
class MixedPayload(StructPayload):
    channel: int = payload_field(PayloadType.U8, offset=0)
    mode: PwmPort = payload_field(PayloadType.U8, offset=1, mask=0x03, interface_type=PwmPort)
    enabled: bool = payload_field(PayloadType.U8, offset=1, mask=0x80, interface_type=bool)
    gain: float = payload_field(PayloadType.FLOAT, offset=4)


class MixedReg(RegisterBase[MixedPayload]):
    address = 103
    access = RegisterAccess.WRITABLE


class TestMixedMaskedAndPlain:
    def test_roundtrip(self):
        payload = MixedPayload(channel=7, mode=PwmPort.PWM2, enabled=True, gain=1.5)
        msg = MixedReg.format(payload, MessageType.WRITE)
        result = MixedReg.parse(msg)
        assert result.channel == 7
        assert result.mode == PwmPort.PWM2
        assert result.enabled is True
        assert abs(result.gain - 1.5) < 1e-6

    def test_mask_byte_layout(self):
        payload = MixedPayload(channel=42, mode=PwmPort.PWM3, enabled=True, gain=0.0)
        msg = MixedReg.format(payload, MessageType.WRITE)
        raw = msg.to_bytes()
        payload_bytes = raw[5:-1]
        assert payload_bytes[0] == 42
        assert payload_bytes[1] & 0x03 == 3  # PWM3
        assert bool(payload_bytes[1] & 0x80) is True  # enabled

    def test_byte_count(self):
        assert MixedPayload.__byte_count__ == 8
        assert MixedReg.count == 8
        assert MixedReg.payload_type == PayloadType.U8


# ---------------------------------------------------------------------------
# Nibble splitter as StructPayload (alternative to MaskPayload version)
# ---------------------------------------------------------------------------


@dataclass
class NibbleSplitStructPayload(StructPayload):
    low: int = payload_field(PayloadType.U8, offset=0, mask=0x0F, interface_type=int)
    high: int = payload_field(PayloadType.U8, offset=0, mask=0xF0, interface_type=int)


class NibbleSplitStructReg(RegisterBase[NibbleSplitStructPayload]):
    address = 104
    access = RegisterAccess.WRITABLE


class TestNibbleSplitAsStruct:
    def test_roundtrip(self):
        payload = NibbleSplitStructPayload(low=0xA, high=0x5)
        msg = NibbleSplitStructReg.format(payload, MessageType.WRITE)
        result = NibbleSplitStructReg.parse(msg)
        assert result.low == 0xA
        assert result.high == 0x5

    def test_encoded_byte(self):
        payload = NibbleSplitStructPayload(low=0xA, high=0x5)
        encoded = NibbleSplitStructReg.encode(payload)
        assert encoded == [0x5A]

    def test_boundary_values(self):
        for low in (0x0, 0xF):
            for high in (0x0, 0xF):
                payload = NibbleSplitStructPayload(low=low, high=high)
                msg = NibbleSplitStructReg.format(payload, MessageType.WRITE)
                result = NibbleSplitStructReg.parse(msg)
                assert result.low == low
                assert result.high == high
