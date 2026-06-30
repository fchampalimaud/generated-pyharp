from dataclasses import dataclass

import pytest
from harp.protocol import MessageType, PayloadType
from harp.protocol.message import HarpMessage
from harp.protocol.registers import (
    RegisterAccess,
    RegisterBase,
)

ANALOG_DATA_ADDRESS = 44


@dataclass
class AnalogDataPayload:
    AnalogInput0: int
    Encoder: int
    AnalogInput1: int


class AnalogData(RegisterBase[AnalogDataPayload]):
    address = ANALOG_DATA_ADDRESS
    payload_type = PayloadType.S16
    decode = lambda payload: AnalogDataPayload(
        AnalogInput0=payload[0],
        Encoder=payload[1],
        AnalogInput1=payload[2],
    )
    encode = lambda value: [
        value.AnalogInput0,
        value.Encoder,
        value.AnalogInput1,
    ]
    count = 3
    access = RegisterAccess.EVENTFUL
    fields = (
        "AnalogInput0",
        "Encoder",
        "AnalogInput1",
    )


def test_analog_data_event_roundtrip() -> None:
    """Encode an AnalogDataPayload into an EVENT message and decode it back."""
    original = AnalogDataPayload(AnalogInput0=100, Encoder=-200, AnalogInput1=300)

    message = AnalogData.format(original, MessageType.EVENT)
    decoded = AnalogData.parse(message)

    assert decoded.AnalogInput0 == original.AnalogInput0
    assert decoded.Encoder == original.Encoder
    assert decoded.AnalogInput1 == original.AnalogInput1


def test_analog_data_event_roundtrip_with_timestamp() -> None:
    """Encode with a timestamp, decode, and verify fields survive the roundtrip."""
    original = AnalogDataPayload(AnalogInput0=512, Encoder=-1024, AnalogInput1=2048)
    timestamp = 12345.001024

    message = AnalogData.format(original, MessageType.EVENT, timestamp=timestamp)
    decoded = AnalogData.parse(message)

    assert decoded.AnalogInput0 == original.AnalogInput0
    assert decoded.Encoder == original.Encoder
    assert decoded.AnalogInput1 == original.AnalogInput1
    assert message.timestamp is not None


def test_analog_data_roundtrip_edge_values() -> None:
    """Roundtrip with S16 boundary values."""
    original = AnalogDataPayload(AnalogInput0=-32768, Encoder=32767, AnalogInput1=0)

    message = AnalogData.format(original, MessageType.EVENT)
    decoded = AnalogData.parse(message)

    assert decoded.AnalogInput0 == original.AnalogInput0
    assert decoded.Encoder == original.Encoder
    assert decoded.AnalogInput1 == original.AnalogInput1


def test_analog_data_event_frame_structure() -> None:
    """Verify the raw byte layout of an AnalogData EVENT message (no timestamp)."""
    original = AnalogDataPayload(AnalogInput0=1, Encoder=2, AnalogInput1=3)

    message = AnalogData.format(original, MessageType.EVENT)
    raw = message.to_bytes()

    assert raw[0] == MessageType.EVENT
    assert raw[2] == ANALOG_DATA_ADDRESS
    assert raw[3] == 255  # default port
    assert message.payload == [1, 2, 3]
    # 3 x S16 = 6 payload bytes -> length = 4 + 6 = 10, total = 12
    assert message.length == 10
    assert len(raw) == 12


def test_analog_data_read_message() -> None:
    """A READ message for AnalogData has no data payload."""
    message = AnalogData.format(None, MessageType.READ)

    assert message.message_type == MessageType.READ
    assert message.address == ANALOG_DATA_ADDRESS


def test_analog_data_from_bytes_roundtrip() -> None:
    """Serialize to bytes, reconstruct via from_bytes, and decode."""
    original = AnalogDataPayload(AnalogInput0=-1, Encoder=0, AnalogInput1=1)

    message = AnalogData.format(original, MessageType.EVENT)
    raw = message.to_bytes()

    reconstructed = HarpMessage.from_bytes(raw)
    decoded = AnalogData.parse(reconstructed)

    assert decoded.AnalogInput0 == original.AnalogInput0
    assert decoded.Encoder == original.Encoder
    assert decoded.AnalogInput1 == original.AnalogInput1


# IRegister contract tests
def test_unsupported_message_type_raises_value_error() -> None:
    """AnalogData is EVENTFUL-only; formatting a WRITE should raise ValueError."""
    payload = AnalogDataPayload(AnalogInput0=1, Encoder=2, AnalogInput1=3)
    with pytest.raises(ValueError, match="does not support"):
        AnalogData.format(payload, MessageType.WRITE)


def test_create_is_alias_for_format() -> None:
    """IRegister.create() produces the same bytes as format()."""
    payload = AnalogDataPayload(AnalogInput0=10, Encoder=-20, AnalogInput1=30)
    msg_format = AnalogData.format(payload, MessageType.EVENT)
    msg_create = AnalogData.create(payload, MessageType.EVENT)
    assert msg_format.to_bytes() == msg_create.to_bytes()


def test_init_subclass_sets_class_attributes() -> None:
    """__init_subclass__ copies spec fields to class-level attributes."""
    assert AnalogData.address == ANALOG_DATA_ADDRESS
    assert AnalogData.payload_type == PayloadType.S16
    assert AnalogData.length == 3


def test_register_supports() -> None:
    """RegisterBase.supports() reflects the access flags correctly."""
    register = AnalogData()
    assert register.supports(MessageType.READ) is True
    assert register.supports(MessageType.EVENT) is True
    assert register.supports(MessageType.WRITE) is False


def test_register_access_properties() -> None:
    """RegisterAccess readable/writable/eventful properties match the flags."""
    read_only = RegisterAccess.READABLE
    assert read_only.readable is True
    assert read_only.writable is False
    assert read_only.eventful is False

    writable = RegisterAccess.WRITABLE
    assert writable.readable is True
    assert writable.writable is True
    assert writable.eventful is False

    eventful = RegisterAccess.EVENTFUL
    assert eventful.readable is True
    assert eventful.writable is False
    assert eventful.eventful is True

    both = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL
    assert both.readable is True
    assert both.writable is True
    assert both.eventful is True
