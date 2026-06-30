from __future__ import annotations

import struct
import typing
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

from harp.protocol.base import (
    STRUCT_CHARS,
    ClockConfigurationFlags,
    EnableFlag,
    MessageType,
    OperationMode,
    PayloadType,
    ResetFlags,
)
from harp.protocol.message import HarpMessage

T = TypeVar("T")


def _id(x):
    return x


def _extract_payload_cls(cls):
    for base in getattr(cls, "__orig_bases__", ()):
        origin = typing.get_origin(base)
        if origin is RegisterBase:
            args = typing.get_args(base)
            if args:
                return args[0]
    return None


class RegisterAccess(IntFlag):
    READABLE = 0
    WRITABLE = 1
    EVENTFUL = 2

    @property
    def readable(self) -> bool:
        return True

    @property
    def writable(self) -> bool:
        return bool(self & RegisterAccess.WRITABLE)

    @property
    def eventful(self) -> bool:
        return bool(self & RegisterAccess.EVENTFUL)


@dataclass(frozen=True)
class StructField:
    name: str
    type: PayloadType
    offset: int
    length: int | None = None
    is_string: bool = False
    mask: int | None = None
    mask_type: type | None = None

    @property
    def byte_size(self) -> int:
        if self.length is not None:
            return self.length
        return self.type.type_size()

    @property
    def shift(self) -> int:
        if self.mask is None:
            return 0
        return (self.mask & -self.mask).bit_length() - 1


def payload_field(
    payload_type: PayloadType,
    offset: int,
    *,
    length: int | None = None,
    is_string: bool = False,
    mask: int | None = None,
    type: type | None = None,
) -> Any:
    return StructField(
        name="",
        type=payload_type,
        offset=offset,
        length=length,
        is_string=is_string,
        mask=mask,
        mask_type=type,
    )


class StructPayload:
    __struct__: ClassVar[tuple[StructField, ...]]
    __base_type__: ClassVar[PayloadType]
    __byte_count__: ClassVar[int]

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        inline: list[tuple[str, StructField]] = []
        for attr_name, value in list(cls.__dict__.items()):
            if isinstance(value, StructField):
                inline.append((attr_name, value))
                delattr(cls, attr_name)

        if inline:
            cls.__struct__ = tuple(
                StructField(
                    name=name,
                    type=sf.type,
                    offset=sf.offset,
                    length=sf.length,
                    is_string=sf.is_string,
                    mask=sf.mask,
                    mask_type=sf.mask_type,
                )
                for name, sf in inline
            )

        s = getattr(cls, "__struct__", None)
        if s is None:
            return

        if "__base_type__" not in cls.__dict__:
            types = {f.type for f in s if not f.is_string and f.length is None}
            cls.__base_type__ = next(iter(types)) if len(types) == 1 else PayloadType.U8

        if "__byte_count__" not in cls.__dict__:
            cls.__byte_count__ = max(f.offset + f.byte_size for f in s)

    @classmethod
    def _decode_bytes(cls, raw_payload):
        data = bytes(raw_payload)
        kwargs = {}
        for f in cls.__struct__:
            if f.is_string:
                kwargs[f.name] = (
                    data[f.offset : f.offset + f.length].rstrip(b"\x00").decode("utf-8")
                )
            elif f.length is not None:
                n = f.length // f.type.type_size()
                kwargs[f.name] = list(
                    struct.unpack_from(f"<{n}{STRUCT_CHARS[f.type]}", data, f.offset)
                )
            else:
                val = struct.unpack_from(f"<{STRUCT_CHARS[f.type]}", data, f.offset)[0]
                if f.mask is not None:
                    val = (val & f.mask) >> f.shift
                    if f.mask_type is not None:
                        val = bool(val) if f.mask_type is bool else f.mask_type(val)
                kwargs[f.name] = val
        return cls(**kwargs)

    @classmethod
    def _decode_values(cls, raw_payload):
        kwargs = {}
        ts = cls.__base_type__.type_size()
        for f in cls.__struct__:
            idx = f.offset // ts
            if f.length is not None:
                n = f.length // ts
                kwargs[f.name] = list(raw_payload[idx : idx + n])
            else:
                val = raw_payload[idx]
                if f.mask is not None:
                    val = (val & f.mask) >> f.shift
                    if f.mask_type is not None:
                        val = bool(val) if f.mask_type is bool else f.mask_type(val)
                kwargs[f.name] = val
        return cls(**kwargs)

    def _encode_bytes(self) -> list:
        buf = bytearray(type(self).__byte_count__)
        for f in type(self).__struct__:
            val = getattr(self, f.name)
            if f.is_string:
                encoded = val.encode("utf-8")
                buf[f.offset : f.offset + len(encoded)] = encoded
            elif f.length is not None:
                n = f.length // f.type.type_size()
                struct.pack_into(f"<{n}{STRUCT_CHARS[f.type]}", buf, f.offset, *val)
            elif f.mask is not None:
                fmt = f"<{STRUCT_CHARS[f.type]}"
                current = struct.unpack_from(fmt, buf, f.offset)[0]
                current |= (int(val) << f.shift) & f.mask
                struct.pack_into(fmt, buf, f.offset, current)
            else:
                struct.pack_into(
                    f"<{STRUCT_CHARS[f.type]}",
                    buf,
                    f.offset,
                    int(val) if isinstance(val, bool) else val,
                )
        return list(buf)

    def _encode_values(self) -> list:
        ts = type(self).__base_type__.type_size()
        count = type(self).__byte_count__ // ts
        result = [0] * count
        for f in type(self).__struct__:
            idx = f.offset // ts
            val = getattr(self, f.name)
            if f.length is not None:
                n = f.length // ts
                result[idx : idx + n] = list(val)
            elif f.mask is not None:
                result[idx] |= (int(val) << f.shift) & f.mask
            else:
                result[idx] = val
        return result

    @classmethod
    def decode(cls, raw_payload):
        if isinstance(raw_payload, int):
            raw_payload = [raw_payload]
        if cls.__base_type__.type_size() == 1:
            return cls._decode_bytes(raw_payload)
        return cls._decode_values(raw_payload)

    def encode(self) -> list:
        if type(self).__base_type__.type_size() == 1:
            return self._encode_bytes()
        return self._encode_values()


@dataclass(frozen=True)
class MaskField:
    mask: int
    type: type = bool

    @property
    def shift(self) -> int:
        return (self.mask & -self.mask).bit_length() - 1


def mask_field(
    *,
    bit: int | None = None,
    mask: int | None = None,
    type: type = bool,
) -> Any:
    if bit is not None:
        mask = 1 << bit
    if mask is None:
        raise ValueError("Either bit or mask must be provided")
    return MaskField(mask=mask, type=type)


class MaskPayload:
    __masks__: ClassVar[tuple[tuple[str, MaskField], ...]]
    __base_type__: ClassVar[PayloadType]

    def __init_subclass__(cls, **kwargs) -> None:
        super().__init_subclass__(**kwargs)

        inline: list[tuple[str, MaskField]] = []
        for attr_name, value in list(cls.__dict__.items()):
            if isinstance(value, MaskField):
                inline.append((attr_name, value))
                delattr(cls, attr_name)

        if inline:
            cls.__masks__ = tuple(inline)

        if "__base_type__" not in cls.__dict__:
            cls.__base_type__ = PayloadType.U8

    @classmethod
    def decode(cls, raw_payload):
        kwargs = {}
        for name, mf in cls.__masks__:
            raw_value = (raw_payload & mf.mask) >> mf.shift
            kwargs[name] = bool(raw_value) if mf.type is bool else mf.type(raw_value)
        return cls(**kwargs)

    def encode(self) -> int:
        result = 0
        for name, mf in type(self).__masks__:
            result |= (int(getattr(self, name)) << mf.shift) & mf.mask
        return result


class RegisterBase(Generic[T]):
    payload_type: ClassVar[PayloadType | None] = None
    count: ClassVar[int] = 1
    access: ClassVar[RegisterAccess] = RegisterAccess.READABLE
    fields: ClassVar[tuple[str, ...] | None] = None
    payload_struct: ClassVar[tuple[StructField, ...] | None] = None
    decode: ClassVar[Callable[[Any], T] | None] = None
    encode: ClassVar[Callable[[T], Any] | None] = None

    def __init_subclass__(cls) -> None:
        super().__init_subclass__()

        if "address" not in cls.__dict__:
            raise TypeError(f"{cls.__name__}: address is required")

        payload_cls = _extract_payload_cls(cls)

        if (
            payload_cls is not None
            and isinstance(payload_cls, type)
            and issubclass(payload_cls, StructPayload)
        ):
            if cls.payload_type is None:
                cls.payload_type = payload_cls.__base_type__
            if cls.payload_struct is None:
                cls.payload_struct = payload_cls.__struct__
            if "count" not in cls.__dict__:
                cls.count = payload_cls.__byte_count__ // cls.payload_type.type_size()
            if cls.decode is None:
                cls.decode = payload_cls.decode
            if cls.encode is None:
                cls.encode = staticmethod(lambda v: v.encode())

        elif (
            payload_cls is not None
            and isinstance(payload_cls, type)
            and issubclass(payload_cls, MaskPayload)
        ):
            if cls.payload_type is None:
                cls.payload_type = payload_cls.__base_type__
            if cls.fields is None:
                cls.fields = tuple(name for name, _ in payload_cls.__masks__)
            if cls.decode is None:
                cls.decode = payload_cls.decode
            if cls.encode is None:
                cls.encode = staticmethod(lambda v: v.encode())

        elif payload_cls is not None and cls.decode is None:
            if payload_cls is int:
                cls.decode = int
                cls.encode = cls.encode or _id
            elif payload_cls is float:
                cls.decode = float
                cls.encode = cls.encode or _id
            elif payload_cls is bytes:
                cls.decode = _id
                cls.encode = cls.encode or _id
            elif isinstance(payload_cls, type) and issubclass(
                payload_cls, (IntEnum, IntFlag)
            ):
                cls.decode = staticmethod(lambda v, c=payload_cls: c(v))
                cls.encode = cls.encode or staticmethod(lambda v: int(v))

        if cls.payload_type is None:
            raise TypeError(f"{cls.__name__}: payload_type is required")
        if cls.decode is None or cls.encode is None:
            raise TypeError(
                f"{cls.__name__}: decode and encode are required "
                f"(could not auto-derive from type parameter)"
            )

        cls.length = cls.count

    @classmethod
    def supports(cls, message_type: MessageType) -> bool:
        if message_type == MessageType.READ:
            return True
        if message_type == MessageType.WRITE:
            return cls.access.writable
        if message_type == MessageType.EVENT:
            return cls.access.eventful
        return False

    @classmethod
    def format(
        cls: type[RegisterBase[T]],
        payload: T | None,
        message_type: MessageType,
        *,
        timestamp: Optional[float] = None,
    ) -> HarpMessage:
        if not cls.supports(message_type):
            raise ValueError(
                f"{cls.__name__} does not support message type {message_type.name}"
            )

        raw_payload = None if payload is None else cls.encode(payload)
        return HarpMessage.from_payload(
            raw_payload,
            message_type=message_type,
            address=cls.address,
            payload_type=cls.payload_type,
            timestamp=timestamp,
        )

    @classmethod
    def parse(cls, message: HarpMessage) -> T:
        return cls.decode(message.payload)

    @classmethod
    def create(
        cls: type[RegisterBase[T]],
        value: T | None,
        message_type: MessageType,
        *,
        timestamp: Optional[float] = None,
    ) -> HarpMessage:
        return cls.format(value, message_type, timestamp=timestamp)


IRegister = RegisterBase


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


class WhoAmI(RegisterBase[int]):
    address = CommonRegisters.WHO_AM_I
    payload_type = PayloadType.U16


class HardwareVersionHigh(RegisterBase[int]):
    address = CommonRegisters.HARDWARE_VERSION_HIGH
    payload_type = PayloadType.U8


class HardwareVersionLow(RegisterBase[int]):
    address = CommonRegisters.HARDWARE_VERSION_LOW
    payload_type = PayloadType.U8


class AssemblyVersion(RegisterBase[int]):
    address = CommonRegisters.ASSEMBLY_VERSION
    payload_type = PayloadType.U8


class CoreVersionHigh(RegisterBase[int]):
    address = CommonRegisters.CORE_VERSION_HIGH
    payload_type = PayloadType.U8


class CoreVersionLow(RegisterBase[int]):
    address = CommonRegisters.CORE_VERSION_LOW
    payload_type = PayloadType.U8


class FirmwareVersionHigh(RegisterBase[int]):
    address = CommonRegisters.FIRMWARE_VERSION_HIGH
    payload_type = PayloadType.U8


class FirmwareVersionLow(RegisterBase[int]):
    address = CommonRegisters.FIRMWARE_VERSION_LOW
    payload_type = PayloadType.U8


class TimestampSeconds(RegisterBase[int]):
    address = CommonRegisters.TIMESTAMP_SECONDS
    payload_type = PayloadType.U32
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL


class TimestampMicroseconds(RegisterBase[int]):
    address = CommonRegisters.TIMESTAMP_MICROSECONDS
    payload_type = PayloadType.U16


@dataclass
class OperationControlPayload(MaskPayload):
    OperationMode: OperationMode = mask_field(mask=0x3, type=OperationMode)
    DumpRegisters: bool = mask_field(bit=3)
    MuteReplies: bool = mask_field(bit=4)
    VisualIndicators: EnableFlag = mask_field(bit=5, type=EnableFlag)
    OperationLed: EnableFlag = mask_field(bit=6, type=EnableFlag)
    Heartbeat: EnableFlag = mask_field(bit=7, type=EnableFlag)


class OperationControl(RegisterBase[OperationControlPayload]):
    address = CommonRegisters.OPERATION_CONTROL
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE


class ResetDevice(RegisterBase[ResetFlags]):
    address = CommonRegisters.RESET_DEVICE
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE


class DeviceName(RegisterBase[bytes]):
    address = CommonRegisters.DEVICE_NAME
    payload_type = PayloadType.U8
    count = 25
    access = RegisterAccess.WRITABLE


class SerialNumber(RegisterBase[int]):
    address = CommonRegisters.SERIAL_NUMBER
    payload_type = PayloadType.U16
    access = RegisterAccess.WRITABLE


class ClockConfiguration(RegisterBase[ClockConfigurationFlags]):
    address = CommonRegisters.CLOCK_CONFIGURATION
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE
