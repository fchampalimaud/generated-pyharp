from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import (
    Any,
    Callable,
    ClassVar,
    Generic,
    Optional,
    TypeVar,
)

from harp.protocol import (
    ClockConfigurationFlags,
    EnableFlag,
    HarpMessage,
    MessageType,
    OperationControlPayload,
    OperationMode,
    PayloadType,
    ResetFlags,
)

T = TypeVar("T")


# Basic adapters
def _id(x):
    return x


def _enum(enum_cls):
    return lambda v: enum_cls(v), lambda v: int(v)


class RegisterAccess(IntFlag):
    READABLE = 0
    WRITABLE = 1
    EVENTFUL = 2

    @property
    def readable(self) -> bool:
        """All registers are readable by default."""
        return True

    @property
    def writable(self) -> bool:
        """Writable if the WRITABLE bit is set."""
        return bool(self & RegisterAccess.WRITABLE)

    @property
    def eventful(self) -> bool:
        """Eventful if the EVENTFUL bit is set."""
        return bool(self & RegisterAccess.EVENTFUL)


@dataclass(frozen=True)
class StructField:
    name: str
    type: PayloadType
    offset: int
    length: int | None = None
    is_string: bool = False

    @property
    def byte_size(self) -> int:
        if self.length is not None:
            return self.length
        return self.type.type_size()


@dataclass(frozen=True)
class RegisterSpec(Generic[T]):
    address: int
    payload_type: PayloadType
    decode: Callable[[Any], T]
    encode: Callable[[T], Any]
    count: int = 1
    access: RegisterAccess = RegisterAccess.READABLE
    fields: tuple[str, ...] | None = None
    payload_struct: tuple[StructField, ...] | None = None

    def supports(self, message_type: MessageType) -> bool:
        if message_type == MessageType.READ:
            return True
        if message_type == MessageType.WRITE:
            return self.access.writable
        if message_type == MessageType.EVENT:
            return self.access.eventful
        return False


class IRegister(Generic[T]):
    """
    Protocol defining the interface for a Harp register.
    """

    spec: ClassVar[RegisterSpec[T]]

    address: ClassVar[int]
    payload_type: ClassVar[PayloadType]
    length: ClassVar[int]

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()
        cls.address = cls.spec.address
        cls.payload_type = cls.spec.payload_type
        cls.length = cls.spec.count

    @classmethod
    def format(
        cls: type[IRegister[T]],
        payload: T | None,
        message_type: MessageType,
        *,
        timestamp: Optional[float] = None,
    ) -> HarpMessage:
        """Format a payload into a complete Harp message."""
        if not cls.spec.supports(message_type):
            raise ValueError(
                f"{cls.__name__} does not support message type {message_type.name}"
            )

        raw_payload = None if payload is None else cls.spec.encode(payload)
        return HarpMessage.from_payload(
            raw_payload,
            message_type=message_type,
            address=cls.spec.address,
            payload_type=cls.spec.payload_type,
            timestamp=timestamp,
        )

    @classmethod
    def parse(cls, message: HarpMessage) -> T:
        """Parse a Harp message into a typed payload."""
        return cls.spec.decode(message.payload)

    @classmethod
    def create(
        cls: type[IRegister[T]],
        value: T | None,
        message_type: MessageType,
        *,
        timestamp: Optional[float] = None,
    ) -> HarpMessage:
        """Create a message with default payload values."""
        return cls.format(value, message_type, timestamp=timestamp)


class CommonRegisters(IntEnum):
    """Enum for all available registers in the Common device.

    Attributes
    ----------
    WHO_AM_I : int
        Specifies the identity class of the device.
    HARDWARE_VERSION_HIGH : int
        Specifies the major hardware version of the device.
    HARDWARE_VERSION_LOW : int
        Specifies the minor hardware version of the device.
    ASSEMBLY_VERSION : int
        Specifies the version of the assembled components in the device.
    CORE_VERSION_HIGH : int
        Specifies the major version of the Harp core implemented by the device.
    CORE_VERSION_LOW : int
        Specifies the minor version of the Harp core implemented by the device.
    FIRMWARE_VERSION_HIGH : int
        Specifies the major version of the Harp core implemented by the device.
    FIRMWARE_VERSION_LOW : int
        Specifies the minor version of the Harp core implemented by the device.
    TIMESTAMP_SECONDS : int
        Stores the integral part of the system timestamp, in seconds.
    TIMESTAMP_MICROSECONDS : int
        Stores the fractional part of the system timestamp, in microseconds.
    OPERATION_CONTROL : int
        Stores the configuration mode of the device.
    RESET_DEVICE : int
        Resets the device and saves non-volatile registers.
    DEVICE_NAME : int
        Stores the user-specified device name.
    SERIAL_NUMBER : int
        Specifies the unique serial number of the device.
    CLOCK_CONFIGURATION : int
        Specifies the configuration for the device synchronization clock.
    """

    WHO_AM_I = 0
    HARDWARE_VERSION_HIGH = 1
    HARDWARE_VERSION_LOW = 2
    ASSEMBLY_VERSION = 3
    CORE_VERSION_HIGH = 4
    CORE_VERSION_LOW = 5
    FIRMWARE_VERSION_HIGH = 6
    FIRMWARE_VERSION_LOW = 7
    TIMESTAMP_SECONDS = 8
    TIMESTAMP_MICROSECONDS = 9
    OPERATION_CONTROL = 10
    RESET_DEVICE = 11
    DEVICE_NAME = 12
    SERIAL_NUMBER = 13
    CLOCK_CONFIGURATION = 14


class WhoAmI(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.WHO_AM_I,
        payload_type=PayloadType.U16,
        decode=int,
        encode=_id,
    )


class HardwareVersionHigh(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.HARDWARE_VERSION_HIGH,
        payload_type=PayloadType.U8,
        decode=int,
        encode=_id,
    )


class HardwareVersionLow(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.HARDWARE_VERSION_LOW,
        payload_type=PayloadType.U8,
        decode=int,
        encode=_id,
    )


class AssemblyVersion(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.ASSEMBLY_VERSION,
        payload_type=PayloadType.U8,
        decode=int,
        encode=_id,
    )


class CoreVersionHigh(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.CORE_VERSION_HIGH,
        payload_type=PayloadType.U8,
        decode=int,
        encode=_id,
    )


class CoreVersionLow(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.CORE_VERSION_LOW,
        payload_type=PayloadType.U8,
        decode=int,
        encode=_id,
    )


class FirmwareVersionHigh(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.FIRMWARE_VERSION_HIGH,
        payload_type=PayloadType.U8,
        decode=int,
        encode=_id,
    )


class FirmwareVersionLow(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.FIRMWARE_VERSION_LOW,
        payload_type=PayloadType.U8,
        decode=int,
        encode=_id,
    )


class TimestampSeconds(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.TIMESTAMP_SECONDS,
        payload_type=PayloadType.U32,
        decode=int,
        encode=_id,
        access=RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL,
    )


class TimestampMicroseconds(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.TIMESTAMP_MICROSECONDS,
        payload_type=PayloadType.U16,
        decode=int,
        encode=_id,
    )


class OperationControl(IRegister[OperationControlPayload]):
    spec = RegisterSpec[OperationControlPayload](
        address=CommonRegisters.OPERATION_CONTROL,
        payload_type=PayloadType.U8,
        decode=lambda payload: OperationControlPayload(
            OperationMode=OperationMode(payload & 0x3),
            DumpRegisters=bool((payload & 0x8) != 0),
            MuteReplies=bool((payload & 0x10) != 0),
            VisualIndicators=EnableFlag((payload & 0x20) != 0),
            OperationLed=EnableFlag((payload & 0x40) != 0),
            Heartbeat=EnableFlag((payload & 0x80) != 0),
        ),
        encode=lambda value: (int(value.OperationMode) & 0x3)
        | (0x8 if bool(value.DumpRegisters) else 0)
        | (0x10 if bool(value.MuteReplies) else 0)
        | (0x20 if bool(value.VisualIndicators) else 0)
        | (0x40 if bool(value.OperationLed) else 0)
        | (0x80 if bool(value.Heartbeat) else 0),
        access=RegisterAccess.WRITABLE,
        fields=(
            "OperationMode",
            "DumpRegisters",
            "MuteReplies",
            "VisualIndicators",
            "OperationLed",
            "Heartbeat",
        ),
    )

    @classmethod
    def create_from_fields(
        cls: type["IRegister[T]"],
        *,
        operation_mode: OperationMode,
        dump_registers: bool,
        mute_replies: bool,
        visual_indicators: EnableFlag,
        operation_led: EnableFlag,
        heartbeat: EnableFlag,
        message_type: MessageType = MessageType.WRITE,
        timestamp: Optional[float] = None,
    ) -> HarpMessage:
        if message_type == MessageType.READ:
            return cls.format(None, message_type, timestamp=timestamp)

        payload = OperationControlPayload(
            OperationMode=operation_mode,
            DumpRegisters=dump_registers,
            MuteReplies=mute_replies,
            VisualIndicators=visual_indicators,
            OperationLed=operation_led,
            Heartbeat=heartbeat,
        )
        return cls.format(payload, message_type, timestamp=timestamp)


class ResetDevice(IRegister[ResetFlags]):
    spec = RegisterSpec[ResetFlags](
        address=CommonRegisters.RESET_DEVICE,
        payload_type=PayloadType.U8,
        decode=lambda payload: ResetFlags(payload),
        encode=lambda value: int(value),
        access=RegisterAccess.WRITABLE,
    )


class DeviceName(IRegister[bytes]):
    spec = RegisterSpec[bytes](
        address=CommonRegisters.DEVICE_NAME,
        payload_type=PayloadType.U8,
        decode=_id,
        encode=_id,
        count=25,
        access=RegisterAccess.WRITABLE,
    )


class SerialNumber(IRegister[int]):
    spec = RegisterSpec[int](
        address=CommonRegisters.SERIAL_NUMBER,
        payload_type=PayloadType.U16,
        decode=int,
        encode=_id,
        access=RegisterAccess.WRITABLE,
    )


class ClockConfiguration(IRegister[ClockConfigurationFlags]):
    spec = RegisterSpec[ClockConfigurationFlags](
        address=CommonRegisters.CLOCK_CONFIGURATION,
        payload_type=PayloadType.U8,
        decode=lambda payload: ClockConfigurationFlags(payload),
        encode=lambda value: int(value),
        access=RegisterAccess.WRITABLE,
    )
