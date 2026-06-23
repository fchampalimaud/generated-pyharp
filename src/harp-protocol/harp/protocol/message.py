from __future__ import annotations

import math
import struct
from typing import ClassVar, Optional, TypeVar, TypeAlias

from harp.protocol import MessageType, PayloadType
from harp.protocol.utils import PayloadTypeFlag

RawPayload: TypeAlias = int | float | list[int] | list[float]


class HarpMessage:
    """
    The `HarpMessage` class implements the Harp message as described in the [protocol](https://harp-tech.org/protocol/BinaryProtocol-8bit.html).

    Attributes
    ----------
    bytes : bytes
        The bytes containing the whole Harp message
    message_type : MessageType
        The message type
    length : int
        The length parameter of the Harp message
    address : int
        The address of the register to which the Harp message refers to
    port : int
        Indicates the origin or destination of the Harp message in case the device is a hub of Harp devices. The value 255 points to the device itself (default value).
    payload_type : PayloadType
        The payload type
    checksum : int
        The sum of all bytes contained in the Harp message
    """

    _base_length: ClassVar[int] = 4

    _bytes: bytes
    _timestamp: Optional[float] = None
    _payload: Optional[RawPayload] = None

    def __init__(self, message_bytes: bytes):
        """
        Parameters
        ----------
        message_type : MessageType
            The message type.
        payload_type : PayloadType
            The payload type.
        address : int
            The address of the register that the message will interact with.
        value: int | list[int] | float | list[float], optional
            The payload of the message. If message_type == MessageType.WRITE, the value cannot be None
        """

        if len(message_bytes) != message_bytes[1] + 2:
            raise ValueError(
                f"the message was expected to have {message_bytes[1] + 2} bytes (due to the value of the length byte being {message_bytes}), but {len(message_bytes)} were found"
            )

        self._bytes = message_bytes

        if self._calculate_checksum(self._bytes) != self._bytes[-1]:
            raise ValueError(
                "the checksum byte of the message does not match the calculated checksum"
            )

        self._payload = self._get_payload()

    @property
    def message_type(self) -> MessageType:
        """
        The message type.

        Returns
        -------
        MessageType
            The message type
        """
        return MessageType(self._bytes[0])

    @property
    def length(self) -> int:
        """
        The length parameter of the Harp message.

        Returns
        -------
        int
            The length parameter of the Harp message
        """
        return self._bytes[1]

    @property
    def address(self) -> int:
        """
        The address of the register to which the Harp message refers to.

        Returns
        -------
        int
            The address of the register to which the Harp message refers to
        """
        return self._bytes[2]

    @property
    def port(self) -> int:
        """
        Indicates the origin or destination of the Harp message in case the device is a hub of Harp devices. The value 255 points to the device itself (default value).

        Returns
        -------
        int
            The port value
        """
        return self._bytes[3]

    @property
    def payload_type(self) -> PayloadType:
        """
        The payload type.

        Returns
        -------
        PayloadType
            The payload type
        """
        return PayloadType(self._bytes[4])

    @property
    def timestamp(self) -> Optional[float]:
        if self.payload_type.has_timestamp():
            return (
                int.from_bytes(self._bytes[5:9], byteorder="little", signed=False)
                + int.from_bytes(self._bytes[9:11], byteorder="little", signed=False)
                * 32e-6
            )
        return None

    @property
    def payload(self) -> RawPayload | None:
        """
        The payload sent in the write Harp message.

        Returns
        -------
        RawPayload | None
            The payload sent in the write Harp message
        """
        return self._payload

    @property
    def checksum(self) -> int:
        """
        The sum of all bytes contained in the Harp message.

        Returns
        -------
        int
            The sum of all bytes contained in the Harp message
        """
        return self._bytes[-1]

    @property
    def is_error(self) -> bool:
        """
        Indicates if this HarpMessage is an error message or not.

        Returns
        -------
        bool
            Returns True if this HarpMessage is an error message, False otherwise.
        """
        return self.message_type.is_error()

    @classmethod
    def from_bytes(cls, message_bytes: bytes) -> HarpMessage:
        return HarpMessage(message_bytes)

    @classmethod
    def from_payload(
        cls,
        payload: RawPayload | None = None,
        *,
        message_type: MessageType,
        address: int,
        port: int = 255,
        payload_type: PayloadType,
        timestamp: float | None = None,
    ) -> HarpMessage:
        if timestamp is None:
            payload_type = PayloadType( payload_type & ~(PayloadTypeFlag.HAS_TIMESTAMP) )
        else:
            payload_type = PayloadType( payload_type | PayloadTypeFlag.HAS_TIMESTAMP )

        raw_timestamp = cls._get_raw_timestamp(timestamp)
        raw_payload = cls._get_raw_payload(payload_type, payload)

        message_bytes = bytearray(
            cls._base_length + len(raw_timestamp) + len(raw_payload) + 2
        )
        message_bytes[0] = message_type
        message_bytes[1] = cls._base_length + len(raw_timestamp) + len(raw_payload)
        message_bytes[2] = address
        message_bytes[3] = port
        message_bytes[4] = payload_type
        if timestamp is None:
            payload_index = 5
        else:
            payload_index = 11
            message_bytes[5:11] = raw_timestamp
        if payload is not None:
            message_bytes[payload_index:-1] = raw_payload
        message_bytes[-1] = cls._calculate_checksum(bytes(message_bytes))

        return HarpMessage(bytes(message_bytes))

    def to_bytes(self) -> bytes:
        """
        The bytes containing the whole Harp message.

        Returns
        -------
        bytes
            The bytes containing the whole Harp message
        """
        return self._bytes

    @classmethod
    def _get_raw_timestamp(
        cls,
        timestamp: Optional[float],
    ) -> bytearray:
        if timestamp is None:
            return bytearray()

        seconds = int(math.floor(timestamp))
        microseconds = int((timestamp - seconds) / (32 * 10**-6))

        raw_timestamp = bytearray(6)
        raw_timestamp[0:4] = seconds.to_bytes(length=4, byteorder="little")
        raw_timestamp[4:6] = microseconds.to_bytes(length=2, byteorder="little")

        return raw_timestamp

    # TODO: improve function
    @classmethod
    def _get_raw_payload(
        cls,
        payload_type: PayloadType,
        payload: RawPayload | None,
    ) -> bytearray:
        raw_payload = bytearray()

        if payload is None:
            return raw_payload

        if payload_type.is_float() and not (
            isinstance(payload, float)
            or (
                isinstance(payload, list)
                and all(isinstance(item, float) for item in payload)
            )
        ):
            from harp.protocol.exceptions import HarpException

            raise HarpException(
                "The payload type provided indicates the payload should be a float or a list[float], but the payload provided is not."
            )
        elif not payload_type.is_float() and not (
            isinstance(payload, int)
            or (
                isinstance(payload, list)
                and all(isinstance(item, int) for item in payload)
            )
        ):
            from harp.protocol.exceptions import HarpException

            raise HarpException(
                "The payload type provided indicates the payload should be an int or a list[int], but the payload provided is not."
            )

        if isinstance(payload, int) or isinstance(payload, float):
            values = [payload]
        elif isinstance(payload, list):
            values = payload

        for val in values:
            if isinstance(val, float):
                raw_payload += struct.pack("<f", val)
            else:
                raw_payload += val.to_bytes(
                    payload_type.type_size(),
                    byteorder="little",
                    signed=payload_type.is_signed(),
                )

        return raw_payload

    @classmethod
    def _calculate_checksum(cls, message_bytes: bytes) -> int:
        """
        Calculates the checksum of the Harp message.

        Returns
        -------
        int
            The value of the checksum
        """
        checksum: int = 0
        for byte in message_bytes[:-1]:
            checksum += byte
        return checksum & 255

    def _get_payload(self) -> RawPayload | None:
        type_size = self.payload_type & 0b1111
        if self.payload_type.has_timestamp():
            raw_payload = self._bytes[11:-1]
        else:
            raw_payload = self._bytes[5:-1]

        if self.payload_type.is_float():
            if len(raw_payload) == 4:
                return struct.unpack("<f", raw_payload)[0]
            else:
                return [
                    struct.unpack("<f", raw_payload[i : i + 4])[0]
                    for i in range(0, len(raw_payload), 4)
                ]
        else:
            if len(raw_payload) == type_size:
                return int.from_bytes(
                    raw_payload,
                    byteorder="little",
                    signed=self.payload_type.is_signed(),
                )
            else:
                return [
                    int.from_bytes(
                        raw_payload[i : i + type_size],
                        byteorder="little",
                        signed=self.payload_type.is_signed(),
                    )
                    for i in range(0, len(raw_payload), type_size)
                ]

    def __repr__(self) -> str:
        """
        Prints debug representation of the reply message.

        Returns
        -------
        str
            The debug representation of the reply message
        """
        return self.__str__() + f"\r\nRaw Bytes: {self._bytes}"

    def __str__(self) -> str:
        """
        Prints friendly representation of a Harp message.

        Returns
        -------
        str
            The representation of the Harp message
        """
        payload_str = ""
        format_str = ""
        if self.payload_type in [PayloadType.FLOAT, PayloadType.TIMESTAMPED_FLOAT]:
            format_str = ".6f"
        else:
            bytes_per_word = self.payload_type & 0x07
            format_str = f"0{bytes_per_word}b"

        payload_str = "".join(
            f"{item:{format_str}} "
            for item in (
                self.payload if isinstance(self.payload, list) else [self.payload]
            )
        )

        # Check if the object has a 'timestamp' property and it's not None
        timestamp_line = ""
        if hasattr(self, "timestamp"):
            ts = getattr(self, "timestamp")
            if ts is not None:
                timestamp_line = f"Timestamp: {ts}\r\n"

        return (
            f"Type: {self.message_type.name}\r\n"
            + f"Length: {self.length}\r\n"
            + f"Address: {self.address}\r\n"
            + f"Port: {self.port}\r\n"
            + timestamp_line
            + f"Payload Type: {self.payload_type.name}\r\n"
            + f"Payload Length: {len(self.payload) if self.payload is list else 1}\r\n"
            + f"Payload: {payload_str}\r\n"
            + f"Checksum: {self.checksum}"
        )
