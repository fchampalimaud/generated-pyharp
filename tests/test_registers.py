from __future__ import annotations

import pytest
from harp.protocol import (
    MessageType,
    PayloadType,
    OperationControlPayload,
    OperationMode,
    EnableFlag,
    ResetFlags,
    ClockConfigurationFlags,
)
from harp.protocol.registers import (
    RegisterBase,
    IRegister,
    RegisterAccess,
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


class TestRegisterBaseClass:
    def test_iregister_is_register_base(self):
        assert IRegister is RegisterBase

    def test_missing_address_raises(self):
        with pytest.raises(TypeError, match="address is required"):

            class Bad(RegisterBase[int]):
                payload_type = PayloadType.U8
                decode = int
                encode = lambda v: v

    def test_missing_decode_raises_for_non_derivable_type(self):
        with pytest.raises(TypeError, match="decode and encode are required"):

            class Bad(RegisterBase[object]):
                address = 99
                payload_type = PayloadType.U8

    def test_auto_derives_int_decode(self):
        class AutoInt(RegisterBase[int]):
            address = 99
            payload_type = PayloadType.U8

        assert AutoInt.decode is int

    def test_auto_derives_intflag_decode(self):
        class AutoFlag(RegisterBase[ResetFlags]):
            address = 99
            payload_type = PayloadType.U8

        assert AutoFlag.decode is not None
        assert AutoFlag.decode(1) == ResetFlags.RESTORE_DEFAULT

    def test_length_equals_count(self):
        assert WhoAmI.length == WhoAmI.count == 1
        assert DeviceName.length == DeviceName.count == 25

    def test_supports_read_only(self):
        assert WhoAmI.supports(MessageType.READ)
        assert not WhoAmI.supports(MessageType.WRITE)
        assert not WhoAmI.supports(MessageType.EVENT)

    def test_supports_writable(self):
        assert SerialNumber.supports(MessageType.READ)
        assert SerialNumber.supports(MessageType.WRITE)
        assert not SerialNumber.supports(MessageType.EVENT)

    def test_supports_writable_and_eventful(self):
        assert TimestampSeconds.supports(MessageType.READ)
        assert TimestampSeconds.supports(MessageType.WRITE)
        assert TimestampSeconds.supports(MessageType.EVENT)

    def test_format_unsupported_raises(self):
        with pytest.raises(ValueError, match="does not support"):
            WhoAmI.format(1, MessageType.WRITE)


class TestScalarRegisters:
    @pytest.mark.parametrize(
        "register_cls",
        [
            WhoAmI,
            HardwareVersionHigh,
            HardwareVersionLow,
            AssemblyVersion,
            CoreVersionHigh,
            CoreVersionLow,
            FirmwareVersionHigh,
            FirmwareVersionLow,
            TimestampMicroseconds,
        ],
    )
    def test_class_attributes(self, register_cls):
        assert hasattr(register_cls, "address")
        assert hasattr(register_cls, "payload_type")
        assert register_cls.decode is not None
        assert register_cls.encode is not None

    def test_timestamp_seconds_roundtrip(self):
        msg = TimestampSeconds.format(12345, MessageType.WRITE)
        assert TimestampSeconds.parse(msg) == 12345

    def test_serial_number_roundtrip(self):
        msg = SerialNumber.format(9876, MessageType.WRITE)
        assert SerialNumber.parse(msg) == 9876


class TestEnumRegisters:
    def test_reset_device_roundtrip(self):
        msg = ResetDevice.format(ResetFlags.RESTORE_DEFAULT, MessageType.WRITE)
        result = ResetDevice.parse(msg)
        assert result == ResetFlags.RESTORE_DEFAULT
        assert isinstance(result, ResetFlags)

    def test_reset_device_combined_flags(self):
        flags = ResetFlags.RESTORE_DEFAULT | ResetFlags.SAVE
        msg = ResetDevice.format(flags, MessageType.WRITE)
        result = ResetDevice.parse(msg)
        assert result == flags

    def test_clock_configuration_roundtrip(self):
        flags = ClockConfigurationFlags.CLOCK_REPEATER | ClockConfigurationFlags.REPEATER_CAPABILITY
        msg = ClockConfiguration.format(flags, MessageType.WRITE)
        result = ClockConfiguration.parse(msg)
        assert result == flags
        assert isinstance(result, ClockConfigurationFlags)


class TestMaskRegister:
    def test_operation_control_roundtrip(self):
        payload = OperationControlPayload(
            OperationMode=OperationMode.ACTIVE,
            DumpRegisters=False,
            MuteReplies=False,
            VisualIndicators=EnableFlag.ENABLED,
            OperationLed=EnableFlag.ENABLED,
            Heartbeat=EnableFlag.ENABLED,
        )
        msg = OperationControl.format(payload, MessageType.WRITE)
        result = OperationControl.parse(msg)

        assert result.OperationMode == OperationMode.ACTIVE
        assert result.DumpRegisters is False
        assert result.MuteReplies is False
        assert result.VisualIndicators == EnableFlag.ENABLED
        assert result.OperationLed == EnableFlag.ENABLED
        assert result.Heartbeat == EnableFlag.ENABLED

    def test_operation_control_all_fields_set(self):
        payload = OperationControlPayload(
            OperationMode=OperationMode.SPEED,
            DumpRegisters=True,
            MuteReplies=True,
            VisualIndicators=EnableFlag.ENABLED,
            OperationLed=EnableFlag.ENABLED,
            Heartbeat=EnableFlag.ENABLED,
        )
        msg = OperationControl.format(payload, MessageType.WRITE)
        result = OperationControl.parse(msg)

        assert result.OperationMode == OperationMode.SPEED
        assert result.DumpRegisters is True
        assert result.MuteReplies is True

    def test_operation_control_encode_bits(self):
        payload = OperationControlPayload(
            OperationMode=OperationMode.ACTIVE,
            DumpRegisters=True,
            MuteReplies=False,
            VisualIndicators=EnableFlag.DISABLED,
            OperationLed=EnableFlag.DISABLED,
            Heartbeat=EnableFlag.DISABLED,
        )
        encoded = OperationControl.encode(payload)
        assert encoded == (0x1 | 0x8)  # ACTIVE=1, DumpRegisters=bit3

    def test_operation_control_fields(self):
        assert OperationControl.fields == (
            "OperationMode",
            "DumpRegisters",
            "MuteReplies",
            "VisualIndicators",
            "OperationLed",
            "Heartbeat",
        )


class TestRawBytesRegister:
    def test_device_name_attributes(self):
        assert DeviceName.count == 25
        assert DeviceName.payload_type == PayloadType.U8
        assert DeviceName.access == RegisterAccess.WRITABLE

    def test_device_name_roundtrip(self):
        data = list(b"test") + [0] * 21
        msg = DeviceName.format(data, MessageType.WRITE)
        result = DeviceName.parse(msg)
        assert list(result) == data


class TestCommonRegisters:
    def test_all_addresses_unique(self):
        addresses = [r.value for r in CommonRegisters]
        assert len(addresses) == len(set(addresses))

    def test_register_count(self):
        assert len(CommonRegisters) == 15


class TestCustomRegister:
    def test_custom_register_definition(self):
        class MyRegister(RegisterBase[int]):
            address = 100
            payload_type = PayloadType.U32
            decode = int
            encode = lambda v: v
            access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL

        assert MyRegister.address == 100
        assert MyRegister.payload_type == PayloadType.U32
        assert MyRegister.count == 1
        assert MyRegister.length == 1
        assert MyRegister.supports(MessageType.READ)
        assert MyRegister.supports(MessageType.WRITE)
        assert MyRegister.supports(MessageType.EVENT)

    def test_custom_register_roundtrip(self):
        class MyRegister(RegisterBase[int]):
            address = 100
            payload_type = PayloadType.U32
            decode = int
            encode = lambda v: v
            access = RegisterAccess.WRITABLE

        msg = MyRegister.format(42, MessageType.WRITE)
        assert MyRegister.parse(msg) == 42
