import struct
from dataclasses import dataclass

from harp.protocol import MessageType, PayloadType
from harp.protocol.message import HarpMessage
from harp.protocol.registers import (
    RegisterAccess,
    RegisterBase,
    StructField,
    StructPayload,
    payload_field,
)

# ComplexConfiguration register
COMPLEX_CONFIG_ADDRESS = 34


@dataclass
class ComplexConfigPayload(StructPayload):
    pwm_port: int = payload_field(PayloadType.U8, offset=0)
    duty_cycle: float = payload_field(PayloadType.FLOAT, offset=4)
    frequency: float = payload_field(PayloadType.FLOAT, offset=8)
    events_enabled: bool = payload_field(PayloadType.U8, offset=12)
    delta: int = payload_field(PayloadType.U32, offset=13)
    name: str = payload_field(PayloadType.U8, offset=17, length=33, is_string=True)


class ComplexConfiguration(RegisterBase[ComplexConfigPayload]):
    address = COMPLEX_CONFIG_ADDRESS
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL


def _assert_complex_config_equal(
    decoded: ComplexConfigPayload, original: ComplexConfigPayload
) -> None:
    assert decoded.pwm_port == original.pwm_port
    assert abs(decoded.duty_cycle - original.duty_cycle) < 1e-6
    assert abs(decoded.frequency - original.frequency) < 1e-6
    assert decoded.events_enabled == original.events_enabled
    assert decoded.delta == original.delta
    assert decoded.name == original.name


def test_complex_config_write_roundtrip() -> None:
    """Encode a ComplexConfigPayload into a WRITE message and decode it back."""
    original = ComplexConfigPayload(
        pwm_port=3,
        duty_cycle=0.75,
        frequency=1000.0,
        events_enabled=True,
        delta=500,
        name="test_motor",
    )

    message = ComplexConfiguration.format(original, MessageType.WRITE)
    decoded = ComplexConfiguration.parse(message)

    _assert_complex_config_equal(decoded, original)


def test_complex_config_event_roundtrip() -> None:
    """Encode a ComplexConfigPayload into an EVENT message and decode it back."""
    original = ComplexConfigPayload(
        pwm_port=7,
        duty_cycle=0.5,
        frequency=2400.0,
        events_enabled=False,
        delta=0,
        name="sensor_a",
    )

    message = ComplexConfiguration.format(original, MessageType.EVENT)
    decoded = ComplexConfiguration.parse(message)

    _assert_complex_config_equal(decoded, original)


def test_complex_config_roundtrip_with_timestamp() -> None:
    """Encode with a timestamp, decode, and verify all fields survive."""
    original = ComplexConfigPayload(
        pwm_port=1,
        duty_cycle=0.33,
        frequency=50.0,
        events_enabled=True,
        delta=12345,
        name="pwm_ch1",
    )
    timestamp = 9999.5

    message = ComplexConfiguration.format(
        original, MessageType.WRITE, timestamp=timestamp
    )
    decoded = ComplexConfiguration.parse(message)

    _assert_complex_config_equal(decoded, original)
    assert message.timestamp is not None


def test_complex_config_roundtrip_edge_values() -> None:
    """Roundtrip with boundary values: max U8, max U32, empty-ish string."""
    original = ComplexConfigPayload(
        pwm_port=255,
        duty_cycle=0.0,
        frequency=0.0,
        events_enabled=False,
        delta=2**32 - 1,
        name="x",
    )

    message = ComplexConfiguration.format(original, MessageType.WRITE)
    decoded = ComplexConfiguration.parse(message)

    _assert_complex_config_equal(decoded, original)


def test_complex_config_roundtrip_max_length_name() -> None:
    """Roundtrip with a name that fills the entire 33-byte field."""
    original = ComplexConfigPayload(
        pwm_port=0,
        duty_cycle=1.0,
        frequency=99999.0,
        events_enabled=True,
        delta=1,
        name="a" * 33,
    )

    message = ComplexConfiguration.format(original, MessageType.WRITE)
    decoded = ComplexConfiguration.parse(message)

    _assert_complex_config_equal(decoded, original)


def test_complex_config_write_frame_structure() -> None:
    """Verify the raw byte layout of a ComplexConfiguration WRITE message."""
    original = ComplexConfigPayload(
        pwm_port=2,
        duty_cycle=0.5,
        frequency=100.0,
        events_enabled=True,
        delta=1000,
        name="hello",
    )

    message = ComplexConfiguration.format(original, MessageType.WRITE)
    raw = message.to_bytes()

    assert raw[0] == MessageType.WRITE
    assert raw[2] == COMPLEX_CONFIG_ADDRESS
    assert raw[3] == 255
    # 50 U8 payload bytes -> length = 4 + 50 = 54, total = 56
    assert message.length == 54
    assert len(raw) == 56


def test_complex_config_from_bytes_roundtrip() -> None:
    """Serialize to bytes, reconstruct via from_bytes, and decode."""
    original = ComplexConfigPayload(
        pwm_port=10,
        duty_cycle=0.9,
        frequency=440.0,
        events_enabled=True,
        delta=88200,
        name="audio_out",
    )

    message = ComplexConfiguration.format(original, MessageType.WRITE)
    raw = message.to_bytes()

    reconstructed = HarpMessage.from_bytes(raw)
    decoded = ComplexConfiguration.parse(reconstructed)

    _assert_complex_config_equal(decoded, original)


# Struct with array fields and gaps
# ---------------------------------
#
# Layout (20 bytes total):
#   offset  0: channel    U8         (1 byte)
#   offset  1-3: ---- gap ----       (3 bytes padding)
#   offset  4: samples    S16 x 4    (8 bytes, array field)
#   offset 12-13: ---- gap ----      (2 bytes padding)
#   offset 14: gain       FLOAT      (4 bytes)
#   offset 18-19: ---- gap ----      (2 bytes padding)

ARRAY_STRUCT_ADDRESS = 60
ARRAY_STRUCT_COUNT = 20


@dataclass
class ArrayStructPayload(StructPayload):
    __byte_count__ = ARRAY_STRUCT_COUNT
    channel: int = payload_field(PayloadType.U8, offset=0)
    samples: list[int] = payload_field(PayloadType.S16, offset=4, length=8)
    gain: float = payload_field(PayloadType.FLOAT, offset=14)


class ArrayStructRegister(RegisterBase[ArrayStructPayload]):
    address = ARRAY_STRUCT_ADDRESS
    count = ARRAY_STRUCT_COUNT
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL


def test_array_struct_roundtrip() -> None:
    """Roundtrip a struct that contains an array field (S16 x 4)."""
    original = ArrayStructPayload(
        channel=5,
        samples=[100, -200, 32767, -32768],
        gain=2.5,
    )

    message = ArrayStructRegister.format(original, MessageType.WRITE)
    decoded = ArrayStructRegister.parse(message)

    assert decoded.channel == original.channel
    assert decoded.samples == original.samples
    assert abs(decoded.gain - original.gain) < 1e-6


def test_array_struct_from_bytes_roundtrip() -> None:
    """Serialize to bytes, reconstruct via from_bytes, and decode."""
    original = ArrayStructPayload(
        channel=0,
        samples=[1, 2, 3, 4],
        gain=0.1,
    )

    message = ArrayStructRegister.format(original, MessageType.WRITE)
    reconstructed = HarpMessage.from_bytes(message.to_bytes())
    decoded = ArrayStructRegister.parse(reconstructed)

    assert decoded.channel == original.channel
    assert decoded.samples == original.samples
    assert abs(decoded.gain - original.gain) < 1e-6


def test_array_struct_gap_bytes_are_zero() -> None:
    """Verify that gap regions in the payload are filled with zeros."""
    original = ArrayStructPayload(
        channel=255,
        samples=[-1, -1, -1, -1],
        gain=99.9,
    )

    message = ArrayStructRegister.format(original, MessageType.WRITE)
    payload_bytes = message.to_bytes()[5:-1]  # strip header (5) and checksum (1)
    assert len(payload_bytes) == ARRAY_STRUCT_COUNT

    # gap at offsets 1-3
    assert payload_bytes[1:4] == b"\x00\x00\x00"
    # gap at offsets 12-13
    assert payload_bytes[12:14] == b"\x00\x00"
    # gap at offsets 18-19
    assert payload_bytes[18:20] == b"\x00\x00"


def test_array_struct_field_offsets_correct() -> None:
    """Verify each field lands at the right byte offset despite gaps."""
    original = ArrayStructPayload(
        channel=42,
        samples=[1000, -2000, 3000, -4000],
        gain=1.5,
    )

    message = ArrayStructRegister.format(original, MessageType.WRITE)
    payload_bytes = bytes(message.to_bytes()[5:-1])

    # channel at offset 0
    assert payload_bytes[0] == 42

    # samples at offset 4: 4 x little-endian S16
    assert struct.unpack_from("<4h", payload_bytes, 4) == (1000, -2000, 3000, -4000)

    # gain at offset 14: little-endian float
    assert abs(struct.unpack_from("<f", payload_bytes, 14)[0] - 1.5) < 1e-6


def test_array_struct_gap_does_not_corrupt_fields() -> None:
    """Mutate gap bytes in a raw frame and confirm field values are unaffected."""
    original = ArrayStructPayload(
        channel=7,
        samples=[10, 20, 30, 40],
        gain=3.14,
    )

    message = ArrayStructRegister.format(original, MessageType.WRITE)
    frame = bytearray(message.to_bytes())

    # Inject non-zero bytes into all three gap regions (payload starts at byte 5)
    payload_start = 5
    for gap_offset in [1, 2, 3, 12, 13, 18, 19]:
        frame[payload_start + gap_offset] = 0xAB

    # Recompute checksum so from_bytes accepts the modified frame
    frame[-1] = sum(frame[:-1]) & 0xFF

    reconstructed = HarpMessage.from_bytes(bytes(frame))
    decoded = ArrayStructRegister.parse(reconstructed)

    assert decoded.channel == original.channel
    assert decoded.samples == original.samples
    assert abs(decoded.gain - original.gain) < 1e-6


# StructField.byte_size tests
def test_struct_field_byte_size_scalar() -> None:
    """byte_size for scalar fields equals the type's native size."""
    assert StructField("x", PayloadType.U8, offset=0).byte_size == 1
    assert StructField("x", PayloadType.S16, offset=0).byte_size == 2
    assert StructField("x", PayloadType.U32, offset=0).byte_size == 4
    assert StructField("x", PayloadType.FLOAT, offset=0).byte_size == 4
    assert StructField("x", PayloadType.U64, offset=0).byte_size == 8


def test_struct_field_byte_size_with_length() -> None:
    """byte_size for array/string fields equals the explicit length."""
    assert (
        StructField("s", PayloadType.U8, offset=0, length=33, is_string=True).byte_size
        == 33
    )
    assert StructField("a", PayloadType.S16, offset=4, length=8).byte_size == 8


# ComplexConfiguration gap at offsets 1-3 (pwm_port to duty_cycle)
def test_complex_config_gap_bytes_are_zero() -> None:
    """Verify the 3-byte gap between pwm_port (offset 0) and duty_cycle (offset 4)."""
    original = ComplexConfigPayload(
        pwm_port=42,
        duty_cycle=0.5,
        frequency=100.0,
        events_enabled=True,
        delta=1000,
        name="test",
    )
    message = ComplexConfiguration.format(original, MessageType.WRITE)
    payload_bytes = message.to_bytes()[5:-1]
    assert payload_bytes[1:4] == b"\x00\x00\x00"


# ---------------------------------------------------------------------------
# KitchenSink: every scalar PayloadType in one struct
# ---------------------------------------------------------------------------

KITCHEN_SINK_ADDRESS = 70


@dataclass
class KitchenSinkPayload(StructPayload):
    a_u8: int = payload_field(PayloadType.U8, offset=0)
    a_s16: int = payload_field(PayloadType.S16, offset=2)
    a_u32: int = payload_field(PayloadType.U32, offset=4)
    a_float: float = payload_field(PayloadType.FLOAT, offset=8)
    a_s32: int = payload_field(PayloadType.S32, offset=12)


class KitchenSink(RegisterBase[KitchenSinkPayload]):
    address = KITCHEN_SINK_ADDRESS
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL


def test_kitchen_sink_roundtrip() -> None:
    original = KitchenSinkPayload(
        a_u8=42,
        a_s16=-1000,
        a_u32=123456789,
        a_float=3.14,
        a_s32=-987654321,
    )
    message = KitchenSink.format(original, MessageType.WRITE)
    decoded = KitchenSink.parse(message)

    assert decoded.a_u8 == original.a_u8
    assert decoded.a_s16 == original.a_s16
    assert decoded.a_u32 == original.a_u32
    assert abs(decoded.a_float - original.a_float) < 1e-6
    assert decoded.a_s32 == original.a_s32


def test_kitchen_sink_boundary_values() -> None:
    original = KitchenSinkPayload(
        a_u8=255,
        a_s16=-32768,
        a_u32=2**32 - 1,
        a_float=0.0,
        a_s32=-(2**31),
    )
    message = KitchenSink.format(original, MessageType.WRITE)
    decoded = KitchenSink.parse(message)

    assert decoded.a_u8 == 255
    assert decoded.a_s16 == -32768
    assert decoded.a_u32 == 2**32 - 1
    assert decoded.a_float == 0.0
    assert decoded.a_s32 == -(2**31)


def test_kitchen_sink_max_positive_values() -> None:
    original = KitchenSinkPayload(
        a_u8=0,
        a_s16=32767,
        a_u32=0,
        a_float=1e30,
        a_s32=2**31 - 1,
    )
    message = KitchenSink.format(original, MessageType.WRITE)
    decoded = KitchenSink.parse(message)

    assert decoded.a_u8 == 0
    assert decoded.a_s16 == 32767
    assert decoded.a_u32 == 0
    assert abs(decoded.a_float - 1e30) / 1e30 < 1e-6
    assert decoded.a_s32 == 2**31 - 1


def test_kitchen_sink_from_bytes_roundtrip() -> None:
    original = KitchenSinkPayload(
        a_u8=1,
        a_s16=-1,
        a_u32=1,
        a_float=-0.5,
        a_s32=-1,
    )
    message = KitchenSink.format(original, MessageType.WRITE)
    reconstructed = HarpMessage.from_bytes(message.to_bytes())
    decoded = KitchenSink.parse(reconstructed)

    assert decoded.a_u8 == original.a_u8
    assert decoded.a_s16 == original.a_s16
    assert decoded.a_u32 == original.a_u32
    assert abs(decoded.a_float - original.a_float) < 1e-6
    assert decoded.a_s32 == original.a_s32


def test_kitchen_sink_byte_count() -> None:
    assert KitchenSinkPayload.__byte_count__ == 16
    assert KitchenSink.count == 16
    assert KitchenSink.payload_type == PayloadType.U8
