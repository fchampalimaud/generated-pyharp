from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum, IntFlag

from harp.protocol import HarpVersion, MessageType, PayloadType
from harp.protocol.registers import (
    RegisterAccess,
    RegisterBase,
    StructPayload,
    payload_field,
)

# ---------------------------------------------------------------------------
# Enums (modeled after generators/tests/Metadata/device.yml)
# ---------------------------------------------------------------------------


class PortDigitalIOS(IntFlag):
    DIO0 = 0x1
    DIO1 = 0x2
    DIO2 = 0x4
    DIO3 = 0x8
    DIO4 = 0x10
    DIO5 = 0x20
    DIO6 = 0x40
    DIO7 = 0x80
    PORT_DIO0 = 0x100
    PORT_DIO1 = 0x800


class PwmPort(IntEnum):
    PWM0 = 0x1
    PWM1 = 0x2
    PWM2 = 0x4
    PWM3 = 0xA


class EncoderModeMask(IntEnum):
    POSITION = 0x0
    DISPLACEMENT = 0x1


# ---------------------------------------------------------------------------
# 1. DigitalInputs — trivial scalar U8 (addr 32)
# ---------------------------------------------------------------------------


class DigitalInputs(RegisterBase[int]):
    address = 32
    payload_type = PayloadType.U8
    access = RegisterAccess.EVENTFUL


# ---------------------------------------------------------------------------
# 2. AnalogData — homogeneous struct, 6x FLOAT (addr 33)
# ---------------------------------------------------------------------------


@dataclass
class AnalogDataPayload(StructPayload):
    AccelerometerX: float = payload_field(PayloadType.FLOAT, offset=0)
    AccelerometerY: float = payload_field(PayloadType.FLOAT, offset=4)
    AccelerometerZ: float = payload_field(PayloadType.FLOAT, offset=8)
    GyroscopeX: float = payload_field(PayloadType.FLOAT, offset=12)
    GyroscopeY: float = payload_field(PayloadType.FLOAT, offset=16)
    GyroscopeZ: float = payload_field(PayloadType.FLOAT, offset=20)


class AnalogData(RegisterBase[AnalogDataPayload]):
    address = 33
    access = RegisterAccess.EVENTFUL


# ---------------------------------------------------------------------------
# 3. ComplexConfiguration — heterogeneous struct, U8 x 50, with gap,
#    bool, enum, and string field (addr 34)
# ---------------------------------------------------------------------------


@dataclass
class ComplexConfigurationPayload(StructPayload):
    PwmPort: PwmPort = payload_field(PayloadType.U8, offset=0, interface_type=PwmPort)
    # bytes 1..3 are gap
    DutyCycle: float = payload_field(PayloadType.FLOAT, offset=4)
    Frequency: float = payload_field(PayloadType.FLOAT, offset=8)
    EventsEnabled: bool = payload_field(PayloadType.U8, offset=12, interface_type=bool)
    Delta: int = payload_field(PayloadType.U32, offset=13)
    Name: str = payload_field(PayloadType.U8, offset=17, length=33, interface_type=str)


class ComplexConfiguration(RegisterBase[ComplexConfigurationPayload]):
    address = 34
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL


# ---------------------------------------------------------------------------
# 4. Version — heterogeneous struct, U8 x 32, with HarpVersion fields,
#    string, and raw array (addr 35)
# ---------------------------------------------------------------------------


@dataclass
class VersionPayload(StructPayload):
    HardwareVersion: HarpVersion = payload_field(
        PayloadType.U8, offset=0, length=3, interface_type=HarpVersion
    )
    FirmwareVersion: HarpVersion = payload_field(
        PayloadType.U8, offset=3, length=3, interface_type=HarpVersion
    )
    CoreVersion: HarpVersion = payload_field(
        PayloadType.U8, offset=6, length=3, interface_type=HarpVersion
    )
    Tag: str = payload_field(PayloadType.U8, offset=9, length=3, interface_type=str)
    Hash: list[int] = payload_field(PayloadType.U8, offset=12, length=20)


class Version(RegisterBase[VersionPayload]):
    address = 35
    access = RegisterAccess.READABLE


# ---------------------------------------------------------------------------
# 5. CustomPayload — register-level interfaceType (addr 36)
#    Whole U32 payload decoded as HarpVersion via auto-derive
# ---------------------------------------------------------------------------


class CustomPayload(RegisterBase[HarpVersion]):
    address = 36
    payload_type = PayloadType.U32


# ---------------------------------------------------------------------------
# 6. CustomRawPayload — same pattern as CustomPayload (addr 37)
# ---------------------------------------------------------------------------


class CustomRawPayload(RegisterBase[HarpVersion]):
    address = 37
    payload_type = PayloadType.U32


# ---------------------------------------------------------------------------
# 7. CustomMemberConverter — mixed types: U8 header + S16 data (addr 38)
#    No converter needed — just use the right PayloadType per field
# ---------------------------------------------------------------------------


@dataclass
class CustomMemberConverterPayload(StructPayload):
    Header: int = payload_field(PayloadType.U8, offset=0)
    Data: int = payload_field(PayloadType.S16, offset=1)


class CustomMemberConverter(RegisterBase[CustomMemberConverterPayload]):
    address = 38
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# 8. BitmaskSplitter — two masked nibbles on one U8 (addr 39)
# ---------------------------------------------------------------------------


@dataclass
class BitmaskSplitterPayload(StructPayload):
    Low: int = payload_field(PayloadType.U8, offset=0, mask=0x0F)
    High: int = payload_field(PayloadType.U8, offset=0, mask=0xF0)


class BitmaskSplitter(RegisterBase[BitmaskSplitterPayload]):
    address = 39
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# 9. Counter0 — trivial scalar S32 (addr 40)
# ---------------------------------------------------------------------------


class Counter0(RegisterBase[int]):
    address = 40
    payload_type = PayloadType.S32
    access = RegisterAccess.EVENTFUL


# ---------------------------------------------------------------------------
# 10. PortDIOSet — whole-register IntFlag (addr 41)
# ---------------------------------------------------------------------------


class PortDIOSet(RegisterBase[PortDigitalIOS]):
    address = 41
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# 11. PulseDOPort0 — trivial scalar U16 (addr 42)
# ---------------------------------------------------------------------------


class PulseDOPort0(RegisterBase[int]):
    address = 42
    payload_type = PayloadType.U16
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# 12. PulseDO0 — trivial scalar U16 (addr 43)
# ---------------------------------------------------------------------------


class PulseDO0(RegisterBase[int]):
    address = 43
    payload_type = PayloadType.U16
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# 13. StartPulse — two overlapping masks on one U16 word (addr 100)
# ---------------------------------------------------------------------------


@dataclass
class StartPulsePayload(StructPayload):
    PulseWidth: int = payload_field(PayloadType.U16, offset=0, mask=0x03FF)
    DigitalOutput: PwmPort = payload_field(
        PayloadType.U16, offset=0, mask=0x0C00, interface_type=PwmPort
    )


class StartPulse(RegisterBase[StartPulsePayload]):
    address = 100
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# 14. StartPulseTrain — 4 masked fields across 2x U16 (addr 101)
# ---------------------------------------------------------------------------


@dataclass
class StartPulseTrainPayload(StructPayload):
    PulseWidth: int = payload_field(PayloadType.U16, offset=0, mask=0x03FF)
    DigitalOutput: PwmPort = payload_field(
        PayloadType.U16, offset=0, mask=0x0C00, interface_type=PwmPort
    )
    PulseCount: int = payload_field(PayloadType.U16, offset=2, mask=0x00FF)
    Frequency: int = payload_field(PayloadType.U16, offset=2, mask=0xFF00)


class StartPulseTrain(RegisterBase[StartPulseTrainPayload]):
    address = 101
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# 15. EncoderMode — whole-register IntEnum (addr 103)
# ---------------------------------------------------------------------------


class EncoderMode(RegisterBase[EncoderModeMask]):
    address = 103
    payload_type = PayloadType.U8
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# Smoke test
# ---------------------------------------------------------------------------


def _roundtrip(name, register_cls, value):
    msg_type = next(iter(register_cls._supported_types))
    msg = register_cls.format(value, msg_type)
    result = register_cls.parse(msg)
    print(f"  {name}: OK  (value={result!r})")
    return result


def main():
    from harp.benchmarks._registers import BENCHMARK_REGISTERS

    print("Register model round-trips:")
    for reg in BENCHMARK_REGISTERS:
        _roundtrip(reg.name, reg.register, reg.value)
    print(f"\nAll {len(BENCHMARK_REGISTERS)} register models passed round-trip.")


if __name__ == "__main__":
    main()
