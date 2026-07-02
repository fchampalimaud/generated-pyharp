from datetime import datetime
from enum import IntEnum, IntFlag
from typing import NamedTuple

from harp.protocol.utils import MessageTypeFlag, PayloadTypeFlag

PROTOCOL_VERSION = "1.13"

# The reference epoch for UTC harp time
REFERENCE_EPOCH = datetime(1904, 1, 1)


class MessageType(IntEnum):
    """
    An enumeration of the allowed message types of a Harp message. More information on the MessageType byte of a Harp message can be found [here](https://harp-tech.org/protocol/BinaryProtocol-8bit.html#messagetype-1-byte).

    Attributes
    ----------
    READ : int
        The value that corresponds to a Read Harp message (1)
    WRITE : int
        The value that corresponds to a Write Harp message (2)
    EVENT : int
        The value that corresponds to an Event Harp message (3). Messages of this type are only meant to be send by the device
    READ_ERROR : int
        The value that corresponds to a Read Error Harp message (9). Messages of this type are only meant to be send by the device
    WRITE_ERROR : int
        The value that corresponds to a Write Error Harp message (10). Messages of this type are only meant to be send by the device
    """

    READ = 0x01
    WRITE = 0x02
    EVENT = 0x03
    ERROR = 0x08
    READ_ERROR = READ | MessageTypeFlag.ERROR
    WRITE_ERROR = WRITE | MessageTypeFlag.ERROR

    def is_error(self) -> bool:
        return bool(self & MessageTypeFlag.ERROR)


class PayloadType(IntEnum):
    """
    An enumeration of the allowed payload types of a Harp message. More information on the PayloadType byte of a Harp message can be found [here](https://harp-tech.org/protocol/BinaryProtocol-8bit.html#payloadtype-1-byte).

    Attributes
    ----------
    U8 : int
        The value that corresponds to a message of type U8
    S8 : int
        The value that corresponds to a message of type S8
    U16 : int
        The value that corresponds to a message of type U16
    S16 : int
        The value that corresponds to a message of type S16
    U32 : int
        The value that corresponds to a message of type U32
    S32 : int
        The value that corresponds to a message of type S32
    U64 : int
        The value that corresponds to a message of type U64
    S64 : int
        The value that corresponds to a message of type S64
    FLOAT : int
        The value that corresponds to a message of type Float
    TIMESTAMP : int
        The value that corresponds to a message of type Timestamp. This is not a valid PayloadType, but it is used to indicate that the message has a timestamp.
    TIMESTAMPED_U8 : int
        The value that corresponds to a message of type TimestampedU8
    TIMESTAMPED_S8 : int
        The value that corresponds to a message of type TimestampedS8
    TIMESTAMPED_U16 : int
        The value that corresponds to a message of type TimestampedU16
    TIMESTAMPED_S16 : int
        The value that corresponds to a message of type TimestampedS16
    TIMESTAMPED_U32 : int
        The value that corresponds to a message of type TimestampedU32
    TIMESTAMPED_S32 : int
        The value that corresponds to a message of type TimestampedS32
    TIMESTAMPED_U64 : int
        The value that corresponds to a message of type TimestampedU64
    TIMESTAMPED_S64 : int
        The value that corresponds to a message of type TimestampedS64
    TIMESTAMPED_FLOAT : int
        The value that corresponds to a message of type TimestampedFloat
    """

    U8 = 0x01
    S8 = PayloadTypeFlag.IS_SIGNED | 0x01
    U16 = 0x02
    S16 = PayloadTypeFlag.IS_SIGNED | 0x02
    U32 = 0x04
    S32 = PayloadTypeFlag.IS_SIGNED | 0x04
    U64 = 0x08
    S64 = PayloadTypeFlag.IS_SIGNED | 0x08
    FLOAT = PayloadTypeFlag.IS_FLOAT | 0x04
    TIMESTAMPED_U8 = PayloadTypeFlag.HAS_TIMESTAMP | U8
    TIMESTAMPED_S8 = PayloadTypeFlag.HAS_TIMESTAMP | S8
    TIMESTAMPED_U16 = PayloadTypeFlag.HAS_TIMESTAMP | U16
    TIMESTAMPED_S16 = PayloadTypeFlag.HAS_TIMESTAMP | S16
    TIMESTAMPED_U32 = PayloadTypeFlag.HAS_TIMESTAMP | U32
    TIMESTAMPED_S32 = PayloadTypeFlag.HAS_TIMESTAMP | S32
    TIMESTAMPED_U64 = PayloadTypeFlag.HAS_TIMESTAMP | U64
    TIMESTAMPED_S64 = PayloadTypeFlag.HAS_TIMESTAMP | S64
    TIMESTAMPED_FLOAT = PayloadTypeFlag.HAS_TIMESTAMP | FLOAT

    def has_timestamp(self) -> bool:
        """
        bool
            Returns True if this PayloadType has a timestamp, False otherwise.
        """
        return bool(self & PayloadTypeFlag.HAS_TIMESTAMP)

    def is_float(self) -> bool:
        """
        bool
            Returns True if this PayloadType is a float, False otherwise.
        """
        return bool(self & PayloadTypeFlag.IS_FLOAT)

    def is_signed(self) -> bool:
        """
        bool
            Returns True if this PayloadType is signed, False otherwise.
        """
        return bool(self & PayloadTypeFlag.IS_SIGNED)

    def type_size(self) -> int:
        return self & PayloadTypeFlag.TYPE_SIZE

    def struct_char(self) -> str:
        return STRUCT_CHARS[self & ~PayloadTypeFlag.HAS_TIMESTAMP]


STRUCT_CHARS: dict[int, str] = {
    PayloadType.U8: "B",
    PayloadType.S8: "b",
    PayloadType.U16: "H",
    PayloadType.S16: "h",
    PayloadType.U32: "I",
    PayloadType.S32: "i",
    PayloadType.U64: "Q",
    PayloadType.S64: "q",
    PayloadType.FLOAT: "f",
}


class ResetFlags(IntFlag):
    """
    Specifies the behavior of the non-volatile registers when resetting the device.

    Attributes
    ----------
    NONE : int
        All reset flags are cleared.
    RESTORE_DEFAULT : int
        The device will boot with all the registers reset to their default factory values.
    RESTORE_EEPROM : int
        The device will boot and restore all the registers to the values stored in non-volatile memory.
    SAVE : int
        The device will boot and save all the current register values to non-volatile memory.
    RESTORE_NAME : int
        The device will boot with the default device name.
    UPDATE_FIRMWARE : int
        The device will enter firmware update mode.
    BOOT_FROM_DEFAULT : int
        Specifies that the device has booted from default factory values.
    BOOT_FROM_EEPROM : int
        Specifies that the device has booted from non-volatile values stored in EEPROM.
    """

    NONE = 0x0
    RESTORE_DEFAULT = 0x1
    RESTORE_EEPROM = 0x2
    SAVE = 0x4
    RESTORE_NAME = 0x8
    UPDATE_FIRMWARE = 0x20
    BOOT_FROM_DEFAULT = 0x40
    BOOT_FROM_EEPROM = 0x80


class ClockConfigurationFlags(IntFlag):
    """
    Specifies configuration flags for the device synchronization clock.

    Attributes
    ----------
    NONE : int
        All clock configuration flags are cleared.
    CLOCK_REPEATER : int
        The device will repeat the clock synchronization signal to the clock output connector, if available.
    CLOCK_GENERATOR : int
        The device resets and generates the clock synchronization signal on the clock output connector, if available.
    REPEATER_CAPABILITY : int
        Specifies the device has the capability to repeat the clock synchronization signal to the clock output connector.
    GENERATOR_CAPABILITY : int
        Specifies the device has the capability to generate the clock synchronization signal to the clock output connector.
    CLOCK_UNLOCK : int
        The device will unlock the timestamp register counter and will accept commands to set new timestamp values.
    CLOCK_LOCK : int
        The device will lock the timestamp register counter and will not accept commands to set new timestamp values.
    """

    NONE = 0x0
    CLOCK_REPEATER = 0x1
    CLOCK_GENERATOR = 0x2
    REPEATER_CAPABILITY = 0x8
    GENERATOR_CAPABILITY = 0x10
    CLOCK_UNLOCK = 0x40
    CLOCK_LOCK = 0x80


class OperationMode(IntEnum):
    """
    Specifies the operation mode of the device.

    Attributes
    ----------
    STANDBY : int
        Disable all event reporting on the device.
    ACTIVE : int
        Event detection is enabled. Only enabled events are reported by the device.
    SPEED : int
        The device enters speed mode.
    """

    STANDBY = 0
    ACTIVE = 1
    SPEED = 3


class EnableFlag(IntEnum):
    """
    Specifies whether a specific register flag is enabled or disabled.

    Attributes
    ----------
    DISABLED : int
        Specifies that the flag is disabled.
    ENABLED : int
        Specifies that the flag is enabled.
    """

    DISABLED = 0
    ENABLED = 1


class HarpVersion(NamedTuple):
    major: int
    minor: int
    patch: int

    @classmethod
    def __harp_decode__(cls, v):
        return cls(v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)

    def __harp_encode__(self):
        return self.major | (self.minor << 8) | (self.patch << 16)


