from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import pytest
from harp.protocol import (
    MessageType,
    PayloadType,
    OperationControlPayload,
    OperationMode,
    EnableFlag,
    ResetFlags,
    ClockConfigurationFlags,
    MaskPayload,
    mask_field,
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


# ---------------------------------------------------------------------------
# Bitmask splitter: two numeric masks on one byte
# ---------------------------------------------------------------------------


class Motor(IntEnum):
    OFF = 0
    LOW = 1
    HIGH = 2
    TURBO = 3


@dataclass
class NibbleSplitPayload(MaskPayload):
    low: int = mask_field(mask=0x0F, type=int)
    high: int = mask_field(mask=0xF0, type=int)


class NibbleSplitReg(RegisterBase[NibbleSplitPayload]):
    address = 200
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE


class TestBitmaskSplitter:
    def test_roundtrip(self):
        payload = NibbleSplitPayload(low=0xA, high=0x5)
        msg = NibbleSplitReg.format(payload, MessageType.WRITE)
        result = NibbleSplitReg.parse(msg)
        assert result.low == 0xA
        assert result.high == 0x5

    def test_encoded_byte(self):
        payload = NibbleSplitPayload(low=0xA, high=0x5)
        encoded = NibbleSplitReg.encode(payload)
        assert encoded == 0x5A

    def test_boundary_values(self):
        for low in (0x0, 0xF):
            for high in (0x0, 0xF):
                payload = NibbleSplitPayload(low=low, high=high)
                msg = NibbleSplitReg.format(payload, MessageType.WRITE)
                result = NibbleSplitReg.parse(msg)
                assert result.low == low
                assert result.high == high

    def test_fields_attribute(self):
        assert NibbleSplitReg.fields == ("low", "high")


# ---------------------------------------------------------------------------
# GroupMask: multi-bit enum + bool fields from mask
# ---------------------------------------------------------------------------


@dataclass
class MotorControlPayload(MaskPayload):
    motor: Motor = mask_field(mask=0x03, type=Motor)
    enabled: bool = mask_field(bit=2)
    direction: bool = mask_field(bit=3)


class MotorControlReg(RegisterBase[MotorControlPayload]):
    address = 201
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE


class TestGroupMask:
    def test_roundtrip_each_enum_value(self):
        for motor_val in Motor:
            payload = MotorControlPayload(
                motor=motor_val, enabled=True, direction=False
            )
            msg = MotorControlReg.format(payload, MessageType.WRITE)
            result = MotorControlReg.parse(msg)
            assert result.motor == motor_val
            assert isinstance(result.motor, Motor)
            assert result.enabled is True
            assert result.direction is False

    def test_all_fields_independently_addressable(self):
        payload = MotorControlPayload(
            motor=Motor.TURBO, enabled=False, direction=True
        )
        msg = MotorControlReg.format(payload, MessageType.WRITE)
        result = MotorControlReg.parse(msg)
        assert result.motor == Motor.TURBO
        assert result.enabled is False
        assert result.direction is True

    def test_encoded_bits(self):
        payload = MotorControlPayload(
            motor=Motor.HIGH, enabled=True, direction=True
        )
        encoded = MotorControlReg.encode(payload)
        # Motor.HIGH=2 in bits 0-1, enabled=1 in bit 2, direction=1 in bit 3
        assert encoded == 0b1110

    def test_fields_attribute(self):
        assert MotorControlReg.fields == ("motor", "enabled", "direction")


# ---------------------------------------------------------------------------
# IntEnum auto-derivation
# ---------------------------------------------------------------------------


class Mode(IntEnum):
    STANDBY = 0
    ACTIVE = 1
    FAST = 2


class ModeReg(RegisterBase[Mode]):
    address = 202
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE


class TestIntEnumAutoDerive:
    def test_roundtrip_each_value(self):
        for mode in Mode:
            msg = ModeReg.format(mode, MessageType.WRITE)
            result = ModeReg.parse(msg)
            assert result == mode
            assert isinstance(result, Mode)

    def test_decode_is_auto_derived(self):
        assert ModeReg.decode is not None
        assert ModeReg.encode is not None


# ---------------------------------------------------------------------------
# float auto-derivation
# ---------------------------------------------------------------------------


class FloatReg(RegisterBase[float]):
    address = 203
    payload_type = PayloadType.FLOAT
    access = RegisterAccess.WRITABLE


class TestFloatAutoDerive:
    def test_roundtrip(self):
        for val in (0.0, 1.5, -3.14):
            msg = FloatReg.format(val, MessageType.WRITE)
            result = FloatReg.parse(msg)
            assert abs(result - val) < 1e-6

    def test_decode_is_auto_derived(self):
        assert FloatReg.decode is float


# ---------------------------------------------------------------------------
# MaskPayload default values
# ---------------------------------------------------------------------------


@dataclass
class ConfigWithDefaults(MaskPayload):
    motor: Motor = mask_field(mask=0x03, type=Motor)
    enabled: bool = mask_field(bit=7)


class ConfigDefaultsReg(RegisterBase[ConfigWithDefaults]):
    address = 204
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE


class TestMaskPayloadDefaults:
    def test_decode_encodes_back(self):
        payload = ConfigWithDefaults(motor=Motor.LOW, enabled=True)
        msg = ConfigDefaultsReg.format(payload, MessageType.WRITE)
        result = ConfigDefaultsReg.parse(msg)
        assert result.motor == Motor.LOW
        assert result.enabled is True

    def test_all_combinations(self):
        for motor_val in Motor:
            for enabled in (True, False):
                payload = ConfigWithDefaults(motor=motor_val, enabled=enabled)
                msg = ConfigDefaultsReg.format(payload, MessageType.WRITE)
                result = ConfigDefaultsReg.parse(msg)
                assert result.motor == motor_val
                assert result.enabled is enabled
