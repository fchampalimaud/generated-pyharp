from __future__ import annotations

import pytest
from harp.protocol import MessageType

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


def _roundtrip(register_cls, value, msg_type=None):
    if msg_type is None:
        msg_type = next(iter(register_cls._supported_types))
    msg = register_cls.format(value, msg_type)
    return register_cls.parse(msg)


class TestScalarRegisters:
    def test_digital_inputs(self):
        result = _roundtrip(DigitalInputs, 42)
        assert result == 42

    def test_counter0_negative(self):
        result = _roundtrip(Counter0, -123456)
        assert result == -123456

    def test_counter0_zero(self):
        result = _roundtrip(Counter0, 0)
        assert result == 0

    def test_pulse_do_port0(self):
        result = _roundtrip(PulseDOPort0, 1000)
        assert result == 1000

    def test_pulse_do0(self):
        result = _roundtrip(PulseDO0, 2000)
        assert result == 2000


class TestIntFlagRegister:
    def test_port_dio_set_combined(self):
        val = PortDigitalIOS.DIO0 | PortDigitalIOS.DIO3
        result = _roundtrip(PortDIOSet, val)
        assert result == val
        assert isinstance(result, PortDigitalIOS)

    def test_port_dio_set_single(self):
        result = _roundtrip(PortDIOSet, PortDigitalIOS.DIO7)
        assert result == PortDigitalIOS.DIO7


class TestIntEnumRegister:
    def test_encoder_mode_displacement(self):
        result = _roundtrip(EncoderMode, EncoderModeMask.DISPLACEMENT)
        assert result == EncoderModeMask.DISPLACEMENT
        assert isinstance(result, EncoderModeMask)

    def test_encoder_mode_position(self):
        result = _roundtrip(EncoderMode, EncoderModeMask.POSITION)
        assert result == EncoderModeMask.POSITION


class TestHarpVersionAutoDerive:
    def test_custom_payload_roundtrip(self):
        v = HarpVersion(1, 2, 3)
        result = _roundtrip(CustomPayload, v)
        assert result == v
        assert isinstance(result, HarpVersion)

    def test_custom_raw_payload_roundtrip(self):
        v = HarpVersion(4, 5, 6)
        result = _roundtrip(CustomRawPayload, v)
        assert result == v

    def test_harp_version_encode_decode(self):
        v = HarpVersion(1, 13, 0)
        packed = v.__harp_encode__()
        decoded = HarpVersion.__harp_decode__(packed)
        assert decoded == v

    def test_harp_version_max_values(self):
        v = HarpVersion(255, 255, 255)
        result = _roundtrip(CustomPayload, v)
        assert result == v


class TestAnalogData:
    def test_roundtrip(self):
        payload = AnalogDataPayload(
            AccelerometerX=1.0,
            AccelerometerY=-2.5,
            AccelerometerZ=9.8,
            GyroscopeX=0.01,
            GyroscopeY=-0.02,
            GyroscopeZ=0.03,
        )
        result = _roundtrip(AnalogData, payload)
        assert abs(result.AccelerometerX - 1.0) < 1e-6
        assert abs(result.AccelerometerY - (-2.5)) < 1e-6
        assert abs(result.AccelerometerZ - 9.8) < 1e-4
        assert abs(result.GyroscopeX - 0.01) < 1e-6
        assert abs(result.GyroscopeY - (-0.02)) < 1e-6
        assert abs(result.GyroscopeZ - 0.03) < 1e-6


class TestComplexConfiguration:
    def test_roundtrip(self):
        payload = ComplexConfigurationPayload(
            PwmPort=PwmPort.PWM2,
            DutyCycle=0.75,
            Frequency=1000.0,
            EventsEnabled=True,
            Delta=500,
        )
        result = _roundtrip(ComplexConfiguration, payload)
        assert result.PwmPort == PwmPort.PWM2
        assert isinstance(result.PwmPort, PwmPort)
        assert abs(result.DutyCycle - 0.75) < 1e-6
        assert abs(result.Frequency - 1000.0) < 1e-3
        assert result.EventsEnabled is True
        assert isinstance(result.EventsEnabled, bool)
        assert result.Delta == 500

    def test_bool_false(self):
        payload = ComplexConfigurationPayload(
            PwmPort=PwmPort.PWM0,
            DutyCycle=0.0,
            Frequency=0.0,
            EventsEnabled=False,
            Delta=0,
        )
        result = _roundtrip(ComplexConfiguration, payload)
        assert result.EventsEnabled is False


class TestVersionPayload:
    def test_roundtrip(self):
        payload = VersionPayload(
            HardwareVersion=HarpVersion(1, 2, 0),
            FirmwareVersion=HarpVersion(3, 4, 5),
            CoreVersion=HarpVersion(1, 13, 0),
            Tag="abc",
            Hash=list(range(20)),
        )
        result = _roundtrip(Version, payload)
        assert result.HardwareVersion == HarpVersion(1, 2, 0)
        assert isinstance(result.HardwareVersion, HarpVersion)
        assert result.FirmwareVersion == HarpVersion(3, 4, 5)
        assert result.CoreVersion == HarpVersion(1, 13, 0)
        assert result.Tag == "abc"
        assert result.Hash == list(range(20))

    def test_empty_tag(self):
        payload = VersionPayload(
            HardwareVersion=HarpVersion(0, 0, 0),
            FirmwareVersion=HarpVersion(0, 0, 0),
            CoreVersion=HarpVersion(0, 0, 0),
            Tag="",
            Hash=[0] * 20,
        )
        result = _roundtrip(Version, payload)
        assert result.Tag == ""
        assert result.HardwareVersion == HarpVersion(0, 0, 0)


class TestCustomMemberConverter:
    def test_roundtrip(self):
        payload = CustomMemberConverterPayload(Header=0xAB, Data=-1234)
        result = _roundtrip(CustomMemberConverter, payload)
        assert result.Header == 0xAB
        assert result.Data == -1234

    def test_signed_boundary(self):
        payload = CustomMemberConverterPayload(Header=0, Data=-32768)
        result = _roundtrip(CustomMemberConverter, payload)
        assert result.Data == -32768

        payload = CustomMemberConverterPayload(Header=255, Data=32767)
        result = _roundtrip(CustomMemberConverter, payload)
        assert result.Data == 32767


class TestBitmaskSplitter:
    def test_roundtrip(self):
        payload = BitmaskSplitterPayload(Low=0xA, High=0x5)
        result = _roundtrip(BitmaskSplitter, payload)
        assert result.Low == 0xA
        assert result.High == 0x5

    def test_boundary_values(self):
        for low in (0x0, 0xF):
            for high in (0x0, 0xF):
                payload = BitmaskSplitterPayload(Low=low, High=high)
                result = _roundtrip(BitmaskSplitter, payload)
                assert result.Low == low
                assert result.High == high


class TestStartPulseMasks:
    def test_start_pulse_roundtrip(self):
        payload = StartPulsePayload(PulseWidth=500, DigitalOutput=PwmPort.PWM1)
        result = _roundtrip(StartPulse, payload)
        assert result.PulseWidth == 500
        assert result.DigitalOutput == PwmPort.PWM1

    def test_start_pulse_train_roundtrip(self):
        payload = StartPulseTrainPayload(
            PulseWidth=200,
            DigitalOutput=PwmPort.PWM1,
            PulseCount=10,
            Frequency=50,
        )
        result = _roundtrip(StartPulseTrain, payload)
        assert result.PulseWidth == 200
        assert result.DigitalOutput == PwmPort.PWM1
        assert result.PulseCount == 10
        assert result.Frequency == 50
