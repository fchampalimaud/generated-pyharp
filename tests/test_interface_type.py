from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag
from typing import NamedTuple

from harp.protocol import HarpVersion, MessageType, PayloadType
from harp.protocol.registers import (
    RegisterAccess,
    RegisterBase,
    StructField,
    StructPayload,
    payload_field,
)


# ---------------------------------------------------------------------------
# interface_type=bool (without mask)
# ---------------------------------------------------------------------------


@dataclass
class BoolPayload(StructPayload):
    enabled: bool = payload_field(PayloadType.U8, offset=0, interface_type=bool)
    value: int = payload_field(PayloadType.U16, offset=1)


class BoolReg(RegisterBase[BoolPayload]):
    address = 200
    access = RegisterAccess.WRITABLE


class TestInterfaceTypeBoolNoMask:
    def test_true(self):
        msg = BoolReg.format(BoolPayload(enabled=True, value=42), MessageType.WRITE)
        result = BoolReg.parse(msg)
        assert result.enabled is True
        assert isinstance(result.enabled, bool)
        assert result.value == 42

    def test_false(self):
        msg = BoolReg.format(BoolPayload(enabled=False, value=0), MessageType.WRITE)
        result = BoolReg.parse(msg)
        assert result.enabled is False
        assert isinstance(result.enabled, bool)


# ---------------------------------------------------------------------------
# interface_type=str (replaces is_string=True)
# ---------------------------------------------------------------------------


@dataclass
class StringPayload(StructPayload):
    label: str = payload_field(PayloadType.U8, offset=0, length=10, interface_type=str)
    count: int = payload_field(PayloadType.U8, offset=10)


class StringReg(RegisterBase[StringPayload]):
    address = 201
    access = RegisterAccess.WRITABLE


class TestInterfaceTypeStr:
    def test_roundtrip(self):
        msg = StringReg.format(StringPayload(label="hello", count=5), MessageType.WRITE)
        result = StringReg.parse(msg)
        assert result.label == "hello"
        assert result.count == 5

    def test_empty_string(self):
        msg = StringReg.format(StringPayload(label="", count=0), MessageType.WRITE)
        result = StringReg.parse(msg)
        assert result.label == ""

    def test_max_length_string(self):
        msg = StringReg.format(StringPayload(label="a" * 10, count=42), MessageType.WRITE)
        result = StringReg.parse(msg)
        assert result.label == "a" * 10

    def test_is_string_property(self):
        fields = StringReg.payload_struct
        label_field = [f for f in fields if f.name == "label"][0]
        count_field = [f for f in fields if f.name == "count"][0]
        assert label_field.is_string is True
        assert count_field.is_string is False


# ---------------------------------------------------------------------------
# interface_type=HarpVersion on multi-byte field
# ---------------------------------------------------------------------------


@dataclass
class VersionFieldPayload(StructPayload):
    hw: HarpVersion = payload_field(PayloadType.U8, offset=0, length=3, interface_type=HarpVersion)
    count: int = payload_field(PayloadType.U8, offset=3)


class VersionFieldReg(RegisterBase[VersionFieldPayload]):
    address = 202
    access = RegisterAccess.WRITABLE


class TestInterfaceTypeHarpVersion:
    def test_roundtrip(self):
        v = HarpVersion(1, 13, 0)
        msg = VersionFieldReg.format(
            VersionFieldPayload(hw=v, count=42), MessageType.WRITE
        )
        result = VersionFieldReg.parse(msg)
        assert result.hw == v
        assert isinstance(result.hw, HarpVersion)
        assert result.hw.major == 1
        assert result.hw.minor == 13
        assert result.hw.patch == 0
        assert result.count == 42

    def test_max_version(self):
        v = HarpVersion(255, 255, 255)
        msg = VersionFieldReg.format(
            VersionFieldPayload(hw=v, count=0), MessageType.WRITE
        )
        result = VersionFieldReg.parse(msg)
        assert result.hw == v


# ---------------------------------------------------------------------------
# interface_type=IntEnum (without mask)
# ---------------------------------------------------------------------------


class Mode(IntEnum):
    OFF = 0
    LOW = 1
    HIGH = 2


@dataclass
class EnumPayload(StructPayload):
    mode: Mode = payload_field(PayloadType.U8, offset=0, interface_type=Mode)
    value: int = payload_field(PayloadType.U16, offset=1)


class EnumReg(RegisterBase[EnumPayload]):
    address = 203
    access = RegisterAccess.WRITABLE


class TestInterfaceTypeEnumNoMask:
    def test_roundtrip(self):
        msg = EnumReg.format(EnumPayload(mode=Mode.HIGH, value=100), MessageType.WRITE)
        result = EnumReg.parse(msg)
        assert result.mode == Mode.HIGH
        assert isinstance(result.mode, Mode)
        assert result.value == 100

    def test_all_modes(self):
        for m in Mode:
            msg = EnumReg.format(EnumPayload(mode=m, value=0), MessageType.WRITE)
            result = EnumReg.parse(msg)
            assert result.mode == m


# ---------------------------------------------------------------------------
# interface_type=IntEnum with mask
# ---------------------------------------------------------------------------


class Direction(IntEnum):
    LEFT = 0
    RIGHT = 1
    UP = 2
    DOWN = 3


@dataclass
class MaskedEnumPayload(StructPayload):
    direction: Direction = payload_field(
        PayloadType.U8, offset=0, mask=0x03, interface_type=Direction
    )
    speed: int = payload_field(PayloadType.U8, offset=0, mask=0xFC)


class MaskedEnumReg(RegisterBase[MaskedEnumPayload]):
    address = 204
    access = RegisterAccess.WRITABLE


class TestInterfaceTypeEnumWithMask:
    def test_roundtrip(self):
        msg = MaskedEnumReg.format(
            MaskedEnumPayload(direction=Direction.UP, speed=15), MessageType.WRITE
        )
        result = MaskedEnumReg.parse(msg)
        assert result.direction == Direction.UP
        assert isinstance(result.direction, Direction)
        assert result.speed == 15


# ---------------------------------------------------------------------------
# RegisterBase[HarpVersion] auto-derivation
# ---------------------------------------------------------------------------


class HarpVersionReg(RegisterBase[HarpVersion]):
    address = 205
    payload_type = PayloadType.U32
    access = RegisterAccess.WRITABLE


class TestRegisterLevelAutoDerive:
    def test_roundtrip(self):
        v = HarpVersion(2, 0, 1)
        msg = HarpVersionReg.format(v, MessageType.WRITE)
        result = HarpVersionReg.parse(msg)
        assert result == v
        assert isinstance(result, HarpVersion)

    def test_has_decode_encode(self):
        assert HarpVersionReg.decode is not None
        assert HarpVersionReg.encode is not None


# ---------------------------------------------------------------------------
# Custom type with __harp_decode__/__harp_encode__ protocol
# ---------------------------------------------------------------------------


class RGBColor(NamedTuple):
    r: int
    g: int
    b: int

    @classmethod
    def __harp_decode__(cls, v):
        return cls(v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF)

    def __harp_encode__(self):
        return self.r | (self.g << 8) | (self.b << 16)


class RGBReg(RegisterBase[RGBColor]):
    address = 206
    payload_type = PayloadType.U32
    access = RegisterAccess.WRITABLE


class TestCustomAutoDerive:
    def test_roundtrip(self):
        c = RGBColor(255, 128, 0)
        msg = RGBReg.format(c, MessageType.WRITE)
        result = RGBReg.parse(msg)
        assert result == c
        assert isinstance(result, RGBColor)

    def test_as_struct_field(self):
        @dataclass
        class ColorPayload(StructPayload):
            color: RGBColor = payload_field(
                PayloadType.U8, offset=0, length=3, interface_type=RGBColor
            )

        class ColorReg(RegisterBase[ColorPayload]):
            address = 207
            access = RegisterAccess.WRITABLE

        c = RGBColor(10, 20, 30)
        msg = ColorReg.format(ColorPayload(color=c), MessageType.WRITE)
        result = ColorReg.parse(msg)
        assert result.color == c


# ---------------------------------------------------------------------------
# StructField backward compatibility
# ---------------------------------------------------------------------------


class TestStructFieldBackwardCompat:
    def test_is_string_true_for_str(self):
        f = StructField(name="x", type=PayloadType.U8, offset=0, length=10, interface_type=str)
        assert f.is_string is True

    def test_is_string_false_for_none(self):
        f = StructField(name="x", type=PayloadType.U8, offset=0)
        assert f.is_string is False

    def test_is_string_false_for_bool(self):
        f = StructField(name="x", type=PayloadType.U8, offset=0, interface_type=bool)
        assert f.is_string is False

    def test_byte_size_with_length(self):
        f = StructField(name="x", type=PayloadType.U8, offset=0, length=10)
        assert f.byte_size == 10

    def test_byte_size_without_length(self):
        f = StructField(name="x", type=PayloadType.U32, offset=0)
        assert f.byte_size == 4

    def test_shift_with_mask(self):
        f = StructField(name="x", type=PayloadType.U16, offset=0, mask=0x0C00)
        assert f.shift == 10

    def test_shift_without_mask(self):
        f = StructField(name="x", type=PayloadType.U16, offset=0)
        assert f.shift == 0
