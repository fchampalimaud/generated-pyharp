import struct

import pytest
from harp.protocol import MessageType, PayloadType
from harp.protocol.message import HarpMessage
from harp.protocol.registers import CommonRegisters


# Validation error tests
def test_invalid_frame_length_raises_value_error() -> None:
    """Constructing a HarpMessage with mismatched length byte raises ValueError."""
    frame = bytes([MessageType.READ, 5, 42, 255, PayloadType.U8, 123, 0, 0])
    with pytest.raises(ValueError, match="expected to have"):
        HarpMessage(frame)


def test_invalid_checksum_raises_value_error() -> None:
    """Constructing a HarpMessage with a bad checksum raises ValueError."""
    frame = bytearray([MessageType.READ, 5, 42, 255, PayloadType.U8, 123, 0])
    frame[-1] = (sum(frame[:-1]) & 255) ^ 0xFF  # deliberately wrong
    with pytest.raises(ValueError, match="checksum"):
        HarpMessage(bytes(frame))


# Payload type mismatch tests
def test_float_payload_with_int_type_raises() -> None:
    """Passing a float value when payload type is integer raises struct.error."""
    with pytest.raises(struct.error):
        HarpMessage.from_payload(
            3.14,
            message_type=MessageType.WRITE,
            address=42,
            payload_type=PayloadType.U8,
        )


def test_int_payload_with_float_type_coerces() -> None:
    """Passing an int value when payload type is FLOAT coerces to float."""
    msg = HarpMessage.from_payload(
        42,
        message_type=MessageType.WRITE,
        address=42,
        payload_type=PayloadType.FLOAT,
    )
    assert abs(msg.payload - 42.0) < 1e-6


def test_float_list_with_int_type_raises() -> None:
    """Passing a list of floats when payload type is integer raises struct.error."""
    with pytest.raises(struct.error):
        HarpMessage.from_payload(
            [1.0, 2.0],
            message_type=MessageType.WRITE,
            address=42,
            payload_type=PayloadType.U16,
        )


def test_int_list_with_float_type_coerces() -> None:
    """Passing a list of ints when payload type is FLOAT coerces to floats."""
    msg = HarpMessage.from_payload(
        [1, 2, 3],
        message_type=MessageType.WRITE,
        address=42,
        payload_type=PayloadType.FLOAT,
    )
    assert len(msg.payload) == 3
    for actual, expected in zip(msg.payload, [1.0, 2.0, 3.0]):
        assert abs(actual - expected) < 1e-6


# Missing property / parameter tests
def test_non_timestamped_message_timestamp_is_none() -> None:
    """A message without a timestamp returns None for the timestamp property."""
    frame = bytearray([MessageType.READ, 5, 42, 255, PayloadType.U8, 123, 0])
    frame[-1] = sum(frame[:-1]) & 255
    message = HarpMessage.from_bytes(bytes(frame))
    assert message.timestamp is None


def test_custom_port() -> None:
    """The port parameter is correctly stored and retrievable."""
    message = HarpMessage.from_payload(
        42,
        message_type=MessageType.WRITE,
        address=10,
        port=3,
        payload_type=PayloadType.U8,
    )
    assert message.port == 3


def test_payload_type_property() -> None:
    """The payload_type property returns the correct PayloadType enum."""
    message = HarpMessage.from_payload(
        100,
        message_type=MessageType.WRITE,
        address=42,
        payload_type=PayloadType.S16,
    )
    assert message.payload_type == PayloadType.S16


def test_write_error_is_error() -> None:
    """A WRITE_ERROR message reports is_error == True."""
    frame = bytearray(
        [
            MessageType.WRITE_ERROR,
            11,
            42,
            255,
            PayloadType.TIMESTAMPED_U8,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    frame[-1] = sum(frame[:-1]) & 255
    message = HarpMessage.from_bytes(bytes(frame))
    assert message.is_error


def test_event_message_type() -> None:
    """An EVENT message can be created and parsed at the HarpMessage level."""
    message = HarpMessage.from_payload(
        99,
        message_type=MessageType.EVENT,
        address=44,
        payload_type=PayloadType.U8,
    )
    assert message.message_type == MessageType.EVENT
    assert message.payload == 99
    assert not message.is_error


def test_from_payload_with_timestamp() -> None:
    """from_payload with a timestamp produces a timestamped message."""
    message = HarpMessage.from_payload(
        42,
        message_type=MessageType.WRITE,
        address=10,
        payload_type=PayloadType.U8,
        timestamp=100.5,
    )
    assert message.payload_type.has_timestamp()
    assert message.timestamp is not None
    assert message.payload == 42


DEFAULT_ADDRESS = 42


def test_create_write_float():
    """Test creating a write message with float value."""
    value = 3.14159
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=42,
        payload_type=PayloadType.FLOAT,
    )

    assert message.message_type == MessageType.WRITE
    assert abs(message.payload - value) < 0.0001
    assert len(message.to_bytes()) == 10


def test_create_write_list():
    """Test creating a write message with list values."""
    values = [10, 20, 30]
    message = HarpMessage.from_payload(
        values, message_type=MessageType.WRITE, address=42, payload_type=PayloadType.U8
    )

    assert len(message.to_bytes()) == 9

    payload_bytes = message.to_bytes()[5:8]
    assert list(payload_bytes) == values


def test_reply_is_error():
    """Test HarpMessage.is_error property."""
    frame = bytearray(
        [
            MessageType.READ_ERROR,
            11,
            42,
            255,
            PayloadType.TIMESTAMPED_U8,
            0,
            0,
            0,
            0,
            0,
            0,
            123,
            0,
        ]
    )
    checksum = sum(frame[:-1]) & 255
    frame[-1] = checksum

    reply = HarpMessage.from_bytes(bytes(frame))
    assert reply.is_error

    frame = bytearray(
        [
            MessageType.READ,
            11,
            42,
            255,
            PayloadType.TIMESTAMPED_U8,
            0,
            0,
            0,
            0,
            0,
            0,
            123,
            0,
        ]
    )
    checksum = sum(frame[:-1]) & 255
    frame[-1] = checksum

    reply = HarpMessage.from_bytes(bytes(frame))
    assert not reply.is_error


def test_create_read_U8() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U8,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 47


def test_create_read_S8() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S8,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 175


def test_create_read_U16() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U16,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 48


def test_create_read_S16() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S16,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 176


def test_create_read_U32() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U32,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 50


def test_create_read_S32() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S32,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 178


def test_create_read_U64() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U64,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 54


def test_create_read_S64() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S64,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 182


def test_create_read_float() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.FLOAT,
    )

    assert message.message_type == MessageType.READ
    assert message.checksum == 114


def test_create_write_U8() -> None:
    value: int = 23
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U8,
    )

    assert message.message_type == MessageType.WRITE
    assert message.payload == value
    assert message.checksum == 72


def test_create_write_S8() -> None:
    value: int = -3
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S8,
    )

    assert message.message_type == MessageType.WRITE
    assert message.payload == value
    assert message.checksum == 174


def test_create_write_U16() -> None:
    value: int = 1024
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U16,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 6
    assert message.payload == value
    assert message.checksum == 55


def test_create_write_S16() -> None:
    value: int = -4837
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S16,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 6
    assert message.payload == value
    assert message.checksum == 187


def test_create_write_U8_array() -> None:
    values: list[int] = [1, 2, 3, 4, 5]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U8,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 4 + len(values)
    assert message.payload == values
    assert message.checksum == 68


def test_create_write_S8_array() -> None:
    values: list[int] = [-1, -2, -3, -4, -5]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S8,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 4 + len(values)
    assert message.payload == values
    assert message.checksum == 166


def test_create_write_U16_array() -> None:
    values: list[int] = [1, 2, 3, 4, 5]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U16,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 4 + len(values) * 2
    assert message.payload == values
    assert message.checksum == 74


def test_create_write_S16_array() -> None:
    values: list[int] = [-1, -2, -3, -4, -5]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S16,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 4 + len(values) * 2
    assert message.payload == values
    assert message.checksum == 167


def test_create_write_U32_array() -> None:
    values: list[int] = [1, 2, 3, 4, 5]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U32,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 4 + len(values) * 4
    assert message.payload == values
    assert message.checksum == 86


def test_create_write_S32_array() -> None:
    values: list[int] = [-1, -2, -3, -4, -5]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S32,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 4 + len(values) * 4
    assert message.payload == values
    assert message.checksum == 169


def test_create_write_U64_array() -> None:
    values: list[int] = [1, 2, 3, 4, 5]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U64,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 4 + len(values) * 8
    assert message.payload == values
    assert message.checksum == 110


def test_create_write_S64_array() -> None:
    values: list[int] = [-1, -2, -3, -4, -5]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S64,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 4 + len(values) * 8
    assert message.payload == values
    assert message.checksum == 173


def test_create_write_float_array() -> None:
    """Test creating a write message with float array values."""
    values = [1.1, 2.2, 3.3]
    message = HarpMessage.from_payload(
        values,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.FLOAT,
    )

    assert message.message_type == MessageType.WRITE
    expected_checksum = 193
    assert len(message.payload) == len(values)
    for actual, expected in zip(message.payload, values):
        assert abs(actual - expected) < 0.0001
    assert message.checksum == expected_checksum


def test_read_who_am_i() -> None:
    message = HarpMessage.from_payload(
        message_type=MessageType.READ,
        address=CommonRegisters.WHO_AM_I,
        payload_type=PayloadType.U16,
    )

    assert message.to_bytes() == b"\x01\x04\x00\xff\x02\x06"


def test_create_write_U32() -> None:
    """Test creating a write message with U32 value."""
    value: int = 2147483000
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U32,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 8
    assert message.payload == value
    assert len(message.to_bytes()) == 10
    expected_checksum = 42
    assert message.checksum == expected_checksum


def test_create_write_S32() -> None:
    """Test creating a write message with S32 value."""
    value: int = -2147483000
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S32,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 8
    assert message.payload == value
    assert len(message.to_bytes()) == 10
    expected_checksum = 193
    assert message.checksum == expected_checksum


def test_create_write_U64() -> None:
    """Test creating a write message with U64 value."""
    value: int = 9223372036854775807
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.U64,
    )

    assert message.message_type == MessageType.WRITE
    assert message.length == 12
    assert message.payload == value
    assert len(message.to_bytes()) == 14
    expected_checksum = 183
    assert message.checksum == expected_checksum


def test_create_write_S64() -> None:
    """Test creating a write message with S64 value."""
    value: int = -9223372036854775807
    message = HarpMessage.from_payload(
        value,
        message_type=MessageType.WRITE,
        address=DEFAULT_ADDRESS,
        payload_type=PayloadType.S64,
    )
    assert message.message_type == MessageType.WRITE
    assert message.length == 12
    assert message.payload == value
    assert len(message.to_bytes()) == 14
    expected_checksum = 64
    assert message.checksum == expected_checksum


def test_reply_message_str_repr() -> None:
    """Test string representation of Reply message."""
    frame = bytearray(
        [
            MessageType.READ,
            11,
            42,
            255,
            PayloadType.TIMESTAMPED_U8,
            0,
            0,
            0,
            0,
            0,
            0,
            123,
            0,
        ]
    )
    checksum = sum(frame[:-1]) & 255
    frame[-1] = checksum

    reply = HarpMessage.from_bytes(bytes(frame))
    str_repr = str(reply)
    repr_str = repr(reply)

    assert "Type: READ" in str_repr
    assert "Length: 11" in str_repr
    assert "Address: 42" in str_repr
    assert "Port: 255" in str_repr
    assert "Payload: " in str_repr
    assert "Raw Bytes" in repr_str


def test_payload_as_string() -> None:
    """Test that raw payload bytes can be decoded as a string."""
    test_string = "Hello"
    encoded = test_string.encode("utf-8")

    frame = bytearray(
        [
            MessageType.READ,
            4 + 6 + len(encoded),
            42,
            255,
            PayloadType.TIMESTAMPED_U8,
            0,
            0,
            0,
            0,
            0,
            0,
        ]
    )
    frame.extend(encoded)
    frame.append(0)
    checksum = sum(frame[:-1]) & 255
    frame[-1] = checksum

    reply = HarpMessage.from_bytes(bytes(frame))
    raw_payload = reply._bytes[11:-1]
    assert raw_payload.decode("utf-8") == test_string


def test_harp_message_parse() -> None:
    """Test the from_bytes class method of HarpMessage."""
    frame = bytearray(
        [
            MessageType.READ,
            11,
            42,
            255,
            PayloadType.TIMESTAMPED_U8,
            0,
            0,
            0,
            0,
            0,
            0,
            123,
            0,
        ]
    )
    checksum = sum(frame[:-1]) & 255
    frame[-1] = checksum

    message = HarpMessage.from_bytes(bytes(frame))
    assert message.message_type == MessageType.READ
    assert message.address == 42
    assert message.payload == 123


def test_timestamp_handling() -> None:
    """Test timestamp handling in HarpMessage."""
    frame = bytearray(
        [
            MessageType.READ,
            11,
            42,
            255,
            PayloadType.TIMESTAMPED_U8,
            1,
            0,
            0,
            0,
            32,
            0,
            123,
            0,
        ]
    )
    checksum = sum(frame[:-1]) & 255
    frame[-1] = checksum

    reply = HarpMessage.from_bytes(bytes(frame))
    assert reply.timestamp is not None
    assert reply.timestamp == 1 + 32 * 32e-6


def test_calculate_checksum() -> None:
    """Test the _calculate_checksum class method."""
    assert HarpMessage._calculate_checksum(bytes([1, 2, 3, 4, 5, 0])) == 15
    assert HarpMessage._calculate_checksum(bytes([200, 100, 50, 20, 10, 0])) == 124


def test_raw_payload_assignment() -> None:
    """Test that payload bytes are at the expected positions based on payload type."""
    frame = bytearray(
        [
            MessageType.READ,
            11,
            42,
            255,
            PayloadType.TIMESTAMPED_U8,
            0,
            0,
            0,
            0,
            0,
            0,
            123,
            0,
        ]
    )
    checksum = sum(frame[:-1]) & 255
    frame[-1] = checksum

    message = HarpMessage.from_bytes(bytes(frame))
    assert message._bytes[11:-1] == frame[11:-1]

    frame_no_timestamp = bytearray(
        [
            MessageType.READ,
            5,
            42,
            255,
            PayloadType.U8,
            123,
            0,
        ]
    )
    checksum = sum(frame_no_timestamp[:-1]) & 255
    frame_no_timestamp[-1] = checksum

    message_no_timestamp = HarpMessage.from_bytes(bytes(frame_no_timestamp))
    assert message_no_timestamp._bytes[5:-1] == frame_no_timestamp[5:-1]
