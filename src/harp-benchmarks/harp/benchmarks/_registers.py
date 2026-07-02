from __future__ import annotations

from pathlib import Path
from typing import Any, NamedTuple

from harp.benchmarks.register_models import (
    AnalogData,
    AnalogDataPayload,
    BitmaskSplitter,
    BitmaskSplitterPayload,
    ComplexConfiguration,
    ComplexConfigurationPayload,
    Counter0,
    CustomMemberConverter,
    CustomMemberConverterPayload,
    CustomPayload,
    CustomRawPayload,
    DigitalInputs,
    EncoderMode,
    EncoderModeMask,
    HarpVersion,
    PortDIOSet,
    PortDigitalIOS,
    PulseDO0,
    PulseDOPort0,
    PwmPort,
    StartPulse,
    StartPulsePayload,
    StartPulseTrain,
    StartPulseTrainPayload,
    Version,
    VersionPayload,
)


class BenchmarkedRegister(NamedTuple):
    name: str
    register: type
    value: Any


BENCHMARK_REGISTERS: list[BenchmarkedRegister] = [
    BenchmarkedRegister("DigitalInputs", DigitalInputs, 42),
    BenchmarkedRegister(
        "AnalogData",
        AnalogData,
        AnalogDataPayload(
            AccelerometerX=1.0,
            AccelerometerY=-2.5,
            AccelerometerZ=9.8,
            GyroscopeX=0.01,
            GyroscopeY=-0.02,
            GyroscopeZ=0.03,
        ),
    ),
    BenchmarkedRegister(
        "ComplexConfiguration",
        ComplexConfiguration,
        ComplexConfigurationPayload(
            PwmPort=PwmPort.PWM2,
            DutyCycle=0.75,
            Frequency=1000.0,
            EventsEnabled=True,
            Delta=500,
        ),
    ),
    BenchmarkedRegister(
        "Version",
        Version,
        VersionPayload(
            HardwareVersion=HarpVersion(1, 2, 0),
            FirmwareVersion=HarpVersion(3, 4, 5),
            CoreVersion=HarpVersion(1, 13, 0),
            Tag="abc",
            Hash=list(range(20)),
        ),
    ),
    BenchmarkedRegister("CustomPayload", CustomPayload, HarpVersion(1, 2, 3)),
    BenchmarkedRegister("CustomRawPayload", CustomRawPayload, HarpVersion(4, 5, 6)),
    BenchmarkedRegister(
        "CustomMemberConverter",
        CustomMemberConverter,
        CustomMemberConverterPayload(Header=0xAB, Data=-1234),
    ),
    BenchmarkedRegister(
        "BitmaskSplitter",
        BitmaskSplitter,
        BitmaskSplitterPayload(Low=0xA, High=0x5),
    ),
    BenchmarkedRegister("Counter0", Counter0, -123456),
    BenchmarkedRegister(
        "PortDIOSet", PortDIOSet, PortDigitalIOS.DIO0 | PortDigitalIOS.DIO3
    ),
    BenchmarkedRegister("PulseDOPort0", PulseDOPort0, 1000),
    BenchmarkedRegister("PulseDO0", PulseDO0, 2000),
    BenchmarkedRegister(
        "StartPulse",
        StartPulse,
        StartPulsePayload(PulseWidth=500, DigitalOutput=PwmPort.PWM1),
    ),
    BenchmarkedRegister(
        "StartPulseTrain",
        StartPulseTrain,
        StartPulseTrainPayload(
            PulseWidth=200,
            DigitalOutput=PwmPort.PWM1,
            PulseCount=10,
            Frequency=50,
        ),
    ),
    BenchmarkedRegister("EncoderMode", EncoderMode, EncoderModeMask.DISPLACEMENT),
]

BENCHMARK_DIR = Path("./benchmark")
DATA_DIR = BENCHMARK_DIR / "data"
REPORT_PATH = BENCHMARK_DIR / "report.md"


def corpus_path(reg: BenchmarkedRegister) -> Path:
    return DATA_DIR / f"{reg.name}_{reg.register.address}.bin"
