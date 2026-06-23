from __future__ import annotations

import logging
import queue
from collections.abc import Mapping
from enum import Enum, IntEnum
from io import BufferedWriter
from pathlib import Path
from typing import Any, ClassVar, Generic, Optional, TypeVar

from harp.protocol import (
    HarpMessage,
    MessageType,
    OperationControlPayload,
    ResetFlags,
    ClockConfigurationFlags,
)
from harp.protocol.exceptions import (
    HarpReadException,
    HarpTimeoutException,
    HarpWriteException,
)
from harp.protocol.registers import (
    IRegister,
    WhoAmI,
    HardwareVersionHigh,
    HardwareVersionLow,
    AssemblyVersion,
    CoreVersionHigh,
    CoreVersionLow,
    FirmwareVersionHigh,
    FirmwareVersionLow,
    TimestampSeconds,
    TimestampMicroseconds,
    OperationControl,
    ResetDevice,
    DeviceName,
    SerialNumber,
    ClockConfiguration,
    CommonRegisters,
)
from harp.serial.harp_serial import HarpSerial

import serial


R = TypeVar("R", bound=IntEnum)
T = TypeVar("T")
# NOTE: doing this because this package can be loaded in Python 3.10 where typing.Self is not available yet
D = TypeVar("D", bound="Device[Any]")


class TimeoutStrategy(Enum):
    """
    Strategy to handle timeouts when waiting for a reply from the device.

    Attributes
    ----------
    RAISE : str
        Raise HarpTimeoutException
    RETURN_NONE : str
        Return None
    LOG_AND_RAISE : str
        Log the timeout and raise HarpTimeoutException
    LOG_AND_NONE : str
        Log the timeout and return None
    """

    RAISE = "raise"  # Raise HarpTimeoutException
    RETURN_NONE = "return_none"  # Return None
    LOG_AND_RAISE = "log_and_raise"
    LOG_AND_NONE = "log_and_none"


COMMON_REGISTERS_TYPE = {
    CommonRegisters.WHO_AM_I: WhoAmI,
    CommonRegisters.HARDWARE_VERSION_HIGH: HardwareVersionHigh,
    CommonRegisters.HARDWARE_VERSION_LOW: HardwareVersionLow,
    CommonRegisters.ASSEMBLY_VERSION: AssemblyVersion,
    CommonRegisters.CORE_VERSION_HIGH: CoreVersionHigh,
    CommonRegisters.CORE_VERSION_LOW: CoreVersionLow,
    CommonRegisters.FIRMWARE_VERSION_HIGH: FirmwareVersionHigh,
    CommonRegisters.FIRMWARE_VERSION_LOW: FirmwareVersionLow,
    CommonRegisters.TIMESTAMP_SECONDS: TimestampSeconds,
    CommonRegisters.TIMESTAMP_MICROSECONDS: TimestampMicroseconds,
    CommonRegisters.OPERATION_CONTROL: OperationControl,
    CommonRegisters.RESET_DEVICE: ResetDevice,
    CommonRegisters.DEVICE_NAME: DeviceName,
    CommonRegisters.SERIAL_NUMBER: SerialNumber,
    CommonRegisters.CLOCK_CONFIGURATION: ClockConfiguration,
}

class Device(Generic[R]):
    """
    The `Device` class provides the interface for interacting with Harp devices. This implementation of the Harp device was based on the official documentation available on the [harp-tech website](https://harp-tech.org/protocol/Device.html).

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
    OPERATION_CONTROL : OperationControlPayload
        Stores the configuration mode of the device.
    RESET_DEVICE : ResetFlags
        Resets the device and saves non-volatile registers.
    DEVICE_NAME : bytes
        Stores the user-specified device name.
    SERIAL_NUMBER : int
        Specifies the unique serial number of the device.
    CLOCK_CONFIGURATION : ClockConfigurationFlags
        Specifies the configuration for the device synchronization clock.
    """

    COMMON_REGISTERS_TYPE: ClassVar[Mapping[CommonRegisters, type[IRegister[Any]]]] = COMMON_REGISTERS_TYPE
    DEVICE_REGISTERS_TYPE: ClassVar[Mapping[R, type[IRegister[Any]]]] = {}

    EXPECTED_WHO_AM_I: ClassVar[int | None] = None

    _ser: HarpSerial
    _dump_file_path: Optional[Path]
    _dump_file: Optional[BufferedWriter] = None
    _timeout: float

    def __init__(
        self,
        serial_port: str,
        dump_file_path: Optional[str] = None,
        timeout: float = 1,
        timeout_strategy: TimeoutStrategy = TimeoutStrategy.RAISE,
    ):
        """
        Parameters
        ----------
        serial_port : str
            The serial port used to establish the connection with the Harp device. It must be denoted as `/dev/ttyUSBx` in Linux and `COMx` in Windows, where `x` is the number of the serial port
        dump_file_path: str, optional
            The binary file to which all Harp messages will be written
        timeout: float, optional
            The timeout in seconds when waiting for a reply from the device
        timeout_strategy: TimeoutStrategy, optional
            The strategy to handle timeouts when waiting for a reply from the device
        """
        self.log = logging.getLogger(f"{__name__}.{self.__class__.__name__}")
        self._serial_port = serial_port
        self._dump_file_path = None
        if dump_file_path is not None:
            self._dump_file_path = Path() / dump_file_path
        self._timeout = timeout
        self._timeout_strategy = timeout_strategy

        # Connect to the Harp device and load the data stored in the device's common registers
        self.connect()
        self.load()
        self._validate_who_am_i()

    def _validate_who_am_i(self):
        if self.EXPECTED_WHO_AM_I is not None:
            if self.WHO_AM_I != self.EXPECTED_WHO_AM_I:
                raise ValueError(
                    f"Unexpected WHO_AM_I value: expected {self.EXPECTED_WHO_AM_I}, got {self.WHO_AM_I}"
                )

    def load(self) -> None:
        """
        Loads the data stored in the device's common registers.
        """
        self.WHO_AM_I = self.read_register(WhoAmI)
        self.HARDWARE_VERSION_HIGH = self.read_register(HardwareVersionHigh)
        self.HARDWARE_VERSION_LOW = self.read_register(HardwareVersionLow)
        self.ASSEMBLY_VERSION = self.read_register(AssemblyVersion)
        self.CORE_VERSION_HIGH = self.read_register(CoreVersionHigh)
        self.CORE_VERSION_LOW = self.read_register(CoreVersionLow)
        self.FIRMWARE_VERSION_HIGH = self.read_register(FirmwareVersionHigh)
        self.FIRMWARE_VERSION_LOW = self.read_register(FirmwareVersionLow)
        self.OPERATION_CONTROL = self.read_register(OperationControl)
        self.RESET_DEVICE = self.read_register(ResetDevice)
        self.DEVICE_NAME = self.read_register(DeviceName)
        self.SERIAL_NUMBER = self.read_register(SerialNumber)
        self.CLOCK_CONFIGURATION = self.read_register(ClockConfiguration)

    def info(self) -> None:
        """
        Prints the device information.
        """
        print("Device info:")
        print(f"Who Am I: {self.WHO_AM_I}")
        print(f"Hardware Version High: {self.HARDWARE_VERSION_HIGH}")
        print(f"Hardware Version Low: {self.HARDWARE_VERSION_LOW}")
        print(f"Assembly Version: {self.ASSEMBLY_VERSION}")
        print(f"Core Version High: {self.CORE_VERSION_HIGH}")
        print(f"Core Version Low: {self.CORE_VERSION_LOW}")
        print(f"Firmware Version High: {self.FIRMWARE_VERSION_HIGH}")
        print(f"Firmware Version Low: {self.FIRMWARE_VERSION_LOW}")
        print(f"Operation Control: {self.OPERATION_CONTROL}")
        print(f"Reset Device: {self.RESET_DEVICE}")
        print(f"Device Name: {self.DEVICE_NAME}")
        print(f"Serial Number: {self.SERIAL_NUMBER}")
        print(f"Clock Configuration: {self.CLOCK_CONFIGURATION}")
        # print(f"* Mode: {self._read_device_mode().name}")

    def connect(self) -> None:
        """
        Connects to the Harp device.
        """
        self._ser = HarpSerial(
            self._serial_port,
            baudrate=1000000,
            timeout=self._timeout,
            parity=serial.PARITY_NONE,
            stopbits=1,
            bytesize=8,
            rtscts=True,
        )

        # open file if it is defined
        if self._dump_file_path is not None:
            self._dump_file = open(self._dump_file_path, "ab")

    def disconnect(self) -> None:
        """
        Disconnects from the Harp device.
        """
        # close file if it exists
        if self._dump_file:
            self._dump_file.close()
            self._dump_file = None

        self._ser.close()

    def _send_checked(self, msg: HarpMessage) -> Optional[HarpMessage]:
        reply = self.send(msg)
        if reply is not None and reply.is_error:
            # Route read vs write exception appropriately
            if msg.message_type == MessageType.READ:
                raise HarpReadException(f"{msg.address}", reply)
            else:
                raise HarpWriteException(f"{msg.address}", reply)
        return reply

    def get_register_type(self, reg: CommonRegisters | R) -> type[IRegister[Any]]:
        if reg in self.COMMON_REGISTERS_TYPE:
            return self.COMMON_REGISTERS_TYPE[reg]
        return self.DEVICE_REGISTERS_TYPE[reg]

    def read_register(
        self,
        register_type: type[IRegister[T]],
        *,
        timestamp: float | None = None,
    ) -> T:
        message = register_type.format(None, MessageType.READ, timestamp=timestamp)
        reply = self._send_checked(message)
        if reply is None:
            raise HarpTimeoutException(self._timeout, message)
        return register_type.parse(reply)

    def write_register(
        self,
        register_type: type[IRegister[T]],
        value: T,
        *,
        timestamp: float | None = None,
    ) -> T:
        message = register_type.format(value, MessageType.WRITE, timestamp=timestamp)
        reply = self._send_checked(message)
        if reply is None:
            raise HarpTimeoutException(self._timeout, message)
        return register_type.parse(reply)

    def read_reg(
        self,
        reg: CommonRegisters | R,
        *,
        timestamp: float | None = None,
    ) -> Any:
        register_type = self.get_register_type(reg)
        return self.read_register(register_type, timestamp=timestamp)

    def write_reg(
        self,
        reg: CommonRegisters | R,
        value: object,
        *,
        timestamp: float | None = None,
    ) -> Any:
        register_type = self.get_register_type(reg)
        return self.write_register(register_type, value, timestamp=timestamp)

    def dump_registers(self) -> list:
        """
        Asserts the DUMP bit to dump the values of all core and app registers
        as Harp Read Reply Messages. More information on the DUMP bit can be found [here](https://harp-tech.org/protocol/Device.html#r_operation_ctrl-u16--operation-mode-configuration).

        Returns
        -------
        list
            The list containing the reply Harp messages for all the device's registers
        """
        reg_value = self.read_register(OperationControl)

        # Assert DUMP bit
        reg_value.DumpRegisters = True
        self.write_register(OperationControl, reg_value)

        # Receive the contents of all registers as Harp Read Reply Messages
        replies = []
        while True:
            msg = self._read()
            if msg is None:
                break
            else:
                replies.append(msg)
                self._dump_reply(msg.to_bytes())
        return replies

    def send(
        self,
        message: HarpMessage,
        *,
        expect_reply: bool = True,
        timeout_strategy: TimeoutStrategy | None = None,
    ) -> HarpMessage | None:
        """
        Sends a Harp message and (optionally) waits for a reply.

        Parameters
        ----------
        message : HarpMessage
            The HarpMessage to be sent to the device
        expect_reply : bool, optional
            If False, do not wait for a reply (fire-and-forget)
        timeout_strategy : TimeoutStrategy | None
            Override the device-level timeout strategy for this call

        Returns
        -------
        HarpMessage | None
            Reply (or None when allowed by the timeout strategy or expect_reply=False)

        Raises
        -------
        HarpTimeoutException
            If no reply is received and the effective strategy requires raising
        """
        if (
            type(message) is not HarpMessage
            and any(isinstance(message, t) for t in self.COMMON_REGISTERS_TYPE.values())
            and any(isinstance(message, t) for t in self.DEVICE_REGISTERS_TYPE.values())
        ):
            raise TypeError("message must be a HarpMessage instance")

        self._ser.write(message.to_bytes())

        if not expect_reply:
            return None

        strategy = timeout_strategy or self._timeout_strategy

        reply = self._read()
        if reply is None:
            hte = HarpTimeoutException(self._timeout, message)
            if strategy in (
                TimeoutStrategy.LOG_AND_RAISE,
                TimeoutStrategy.LOG_AND_NONE,
            ):
                self.log.warning(str(hte))
            if strategy in (TimeoutStrategy.RAISE, TimeoutStrategy.LOG_AND_RAISE):
                raise hte
        else:
            self._dump_reply(reply.to_bytes())
        return reply

    def _read(self) -> HarpMessage | None:
        """
        Reads an incoming serial message in a blocking way.

        Returns
        -------
        HarpMessage | None
            The incoming Harp message in case it exists

        Raises
        -------
        TimeoutError
            If no reply is received within the timeout period
        """
        try:
            return self._ser.msg_q.get(block=True, timeout=self._timeout)
        except queue.Empty:
            return None

    def _dump_reply(self, reply: bytearray):
        """
        Dumps the reply to a Harp message in the dump file in case it exists.
        """
        if self._dump_file:
            self._dump_file.write(reply)

    def get_events(self) -> list[HarpMessage]:
        """
        Gets all events from the event queue.

        Returns
        -------
        list
            The list containing every Harp event message that were on the queue
        """
        msgs = []
        while True:
            try:
                msg = self._ser.event_q.get(timeout=False)
                self._dump_reply(msg.to_bytes())
                msgs.append(msg)
            except queue.Empty:
                break
        return msgs

    def event_count(self) -> int:
        """
        Gets the number of events in the event queue.

        Returns
        -------
        int
            The number of events in the event queue
        """
        return self._ser.event_q.qsize()

    def __enter__(self: D) -> D:
        """
        Support for using Device with 'with' statement.

        Returns
        -------
        Device
            The Device instance
        """
        # Connection is already established in __init__
        # but we could add additional setup if needed
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Cleanup resources when exiting the 'with' block.

        Parameters
        ----------
        exc_type : Exception type or None
            Type of the exception that caused the context to be exited
        exc_val : Exception or None
            Exception instance that caused the context to be exited
        exc_tb : traceback or None
            Traceback if an exception occurred
        """
        self.disconnect()
        # Return False to propagate exceptions that occurred in the with block
        return False

    @property
    def who_am_i(self) -> int:
        return self.WHO_AM_I

    @property
    def hardware_version_high(self) -> int:
        return self.HARDWARE_VERSION_HIGH

    @property
    def hardware_version_low(self) -> int:
        return self.HARDWARE_VERSION_LOW

    @property
    def assembly_version(self) -> int:
        return self.ASSEMBLY_VERSION

    @property
    def core_version_high(self) -> int:
        return self.CORE_VERSION_HIGH

    @property
    def core_version_low(self) -> int:
        return self.CORE_VERSION_LOW

    @property
    def firmware_version_high(self) -> int:
        return self.FIRMWARE_VERSION_HIGH

    @property
    def firmware_version_low(self) -> int:
        return self.FIRMWARE_VERSION_LOW

    @property
    def operation_control(self) -> OperationControlPayload:
        return self.OPERATION_CONTROL

    @property
    def reset_device(self) -> ResetFlags:
        return self.RESET_DEVICE

    @property
    def device_name(self) -> bytes:
        return self.DEVICE_NAME

    @property
    def serial_number(self) -> int:
        return self.SERIAL_NUMBER

    @property
    def clock_configuration(self) -> ClockConfigurationFlags:
        return self.CLOCK_CONFIGURATION


    def read_who_am_i(self) -> int:
        """
        Reads the WhoAmI register.

        Returns
        -------
        int
            The value stored in the WhoAmI register
        """
        return self.read_register(WhoAmI)

    def read_hardware_version_high(self) -> int:
        """
        Reads the HardwareVersionHigh register.

        Returns
        -------
        int
            The value stored in the HardwareVersionHigh register
        """
        return self.read_register(HardwareVersionHigh)

    def read_hardware_version_low(self) -> int:
        """
        Reads the HardwareVersionLow register.

        Returns
        -------
        int
            The value stored in the HardwareVersionLow register
        """
        return self.read_register(HardwareVersionLow)

    def read_assembly_version(self) -> int:
        """
        Reads the AssemblyVersion register.

        Returns
        -------
        int
            The value stored in the AssemblyVersion register
        """
        return self.read_register(AssemblyVersion)

    def read_core_version_high(self) -> int:
        """
        Reads the CoreVersionHigh register.

        Returns
        -------
        int
            The value stored in the CoreVersionHigh register
        """
        return self.read_register(CoreVersionHigh)

    def read_core_version_low(self) -> int:
        """
        Reads the CoreVersionLow register.

        Returns
        -------
        int
            The value stored in the CoreVersionLow register
        """
        return self.read_register(CoreVersionLow)

    def read_firmware_version_high(self) -> int:
        """
        Reads the FirmwareVersionHigh register.

        Returns
        -------
        int
            The value stored in the FirmwareVersionHigh register
        """
        return self.read_register(FirmwareVersionHigh)

    def read_firmware_version_low(self) -> int:
        """
        Reads the FirmwareVersionLow register.

        Returns
        -------
        int
            The value stored in the FirmwareVersionLow register
        """
        return self.read_register(FirmwareVersionLow)

    def read_timestamp_seconds(self) -> int:
        """
        Reads the TimestampSeconds register.

        Returns
        -------
        int
            The value stored in the TimestampSeconds register
        """
        return self.read_register(TimestampSeconds)

    def write_timestamp_seconds(self, value: int) -> int:
        """
        Writes a value to the TimestampSeconds register.

        Parameters
        ----------
        value : int
            The value to be written to the TimestampSeconds register
        """
        return self.write_register(TimestampSeconds, value)

    def read_timestamp_microseconds(self) -> int:
        """
        Reads the TimestampMicroseconds register.

        Returns
        -------
        int
            The value stored in the TimestampMicroseconds register
        """
        return self.read_register(TimestampMicroseconds)

    def read_operation_control(self) -> OperationControlPayload:
        """
        Reads the OperationControl register.

        Returns
        -------
        OperationControlPayload
            The value stored in the OperationControl register
        """
        return self.read_register(OperationControl)

    def write_operation_control(self, value: OperationControlPayload) -> OperationControlPayload:
        """
        Writes a value to the OperationControl register.

        Parameters
        ----------
        value : OperationControlPayload
            The value to be written to the OperationControl register
        """
        return self.write_register(OperationControl, value)

    def read_reset_device(self) -> ResetFlags:
        """
        Reads the ResetDevice register.

        Returns
        -------
        ResetFlags
            The value stored in the ResetDevice register
        """
        return self.read_register(ResetDevice)

    def write_reset_device(self, value: ResetFlags) -> ResetFlags:
        """
        Writes a value to the ResetDevice register.

        Parameters
        ----------
        value : ResetFlags
            The value to be written to the ResetDevice register
        """
        return self.write_register(ResetDevice, value)

    def read_device_name(self) -> bytes:
        """
        Reads the DeviceName register.

        Returns
        -------
        bytes
            The value stored in the DeviceName register
        """
        return self.read_register(DeviceName)

    def write_device_name(self, value: bytes) -> bytes:
        """
        Writes a value to the DeviceName register.

        Parameters
        ----------
        value : bytes
            The value to be written to the DeviceName register
        """
        return self.write_register(DeviceName, value)

    def read_serial_number(self) -> int:
        """
        Reads the SerialNumber register.

        Returns
        -------
        int
            The value stored in the SerialNumber register
        """
        return self.read_register(SerialNumber)

    def write_serial_number(self, value: int) -> int:
        """
        Writes a value to the SerialNumber register.

        Parameters
        ----------
        value : int
            The value to be written to the SerialNumber register
        """
        return self.write_register(SerialNumber, value)

    def read_clock_configuration(self) -> ClockConfigurationFlags:
        """
        Reads the ClockConfiguration register.

        Returns
        -------
        ClockConfigurationFlags
            The value stored in the ClockConfiguration register
        """
        return self.read_register(ClockConfiguration)

    def write_clock_configuration(self, value: ClockConfigurationFlags) -> ClockConfigurationFlags:
        """
        Writes a value to the ClockConfiguration register.

        Parameters
        ----------
        value : ClockConfigurationFlags
            The value to be written to the ClockConfiguration register
        """
        return self.write_register(ClockConfiguration, value)

