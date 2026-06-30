"""Per-message encode/decode microbenchmark.

Measures RegisterBase.format() and RegisterBase.parse() for each register
pattern, reporting min/mean/max per operation in microseconds.

Usage:
    uv run python scripts/benchmark_message.py
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from statistics import mean, stdev
from timeit import Timer

from harp.protocol import (
    EnableFlag,
    MessageType,
    OperationMode,
    PayloadType,
    ResetFlags,
)
from harp.protocol.registers import (
    MaskPayload,
    OperationControlPayload,
    RegisterAccess,
    RegisterBase,
    StructPayload,
    WhoAmI,
    DeviceName,
    OperationControl,
    ResetDevice,
    mask_field,
    payload_field,
)


# ---------------------------------------------------------------------------
# Register definitions for benchmarking
# ---------------------------------------------------------------------------

# Homogeneous struct (AnalogData-like)
@dataclass
class AnalogDataPayload(StructPayload):
    AnalogInput0: int = payload_field(PayloadType.S16, offset=0)
    Encoder: int = payload_field(PayloadType.S16, offset=2)
    AnalogInput1: int = payload_field(PayloadType.S16, offset=4)


class AnalogData(RegisterBase[AnalogDataPayload]):
    address = 44
    access = RegisterAccess.EVENTFUL


# Heterogeneous struct (ComplexConfiguration)
@dataclass
class ComplexConfigPayload(StructPayload):
    pwm_port: int = payload_field(PayloadType.U8, offset=0)
    duty_cycle: float = payload_field(PayloadType.FLOAT, offset=4)
    frequency: float = payload_field(PayloadType.FLOAT, offset=8)
    events_enabled: bool = payload_field(PayloadType.U8, offset=12)
    delta: int = payload_field(PayloadType.U32, offset=13)
    name: str = payload_field(PayloadType.U8, offset=17, length=33, is_string=True)


class ComplexConfiguration(RegisterBase[ComplexConfigPayload]):
    address = 34
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL


# Masked struct (StartPulseTrain-like)
class PwmPort(IntEnum):
    PWM0 = 0
    PWM1 = 1
    PWM2 = 2
    PWM3 = 3


@dataclass
class StartPulseTrainPayload(StructPayload):
    pulse_width: int = payload_field(PayloadType.U16, offset=0, mask=0x03FF)
    digital_output: PwmPort = payload_field(
        PayloadType.U16, offset=0, mask=0x0C00, type=PwmPort
    )
    pulse_count: int = payload_field(PayloadType.U16, offset=2, mask=0x00FF, type=int)
    frequency: int = payload_field(PayloadType.U16, offset=2, mask=0xFF00, type=int)


class StartPulseTrain(RegisterBase[StartPulseTrainPayload]):
    address = 101
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# Benchmark payloads (pre-built so construction cost is excluded)
# ---------------------------------------------------------------------------

CASES = [
    {
        "name": "Scalar int (WhoAmI U16)",
        "register": WhoAmI,
        "value": 1234,
        "msg_type": MessageType.READ,
    },
    {
        "name": "IntFlag (ResetDevice U8)",
        "register": ResetDevice,
        "value": ResetFlags.RESTORE_DEFAULT | ResetFlags.SAVE,
        "msg_type": MessageType.WRITE,
    },
    {
        "name": "MaskPayload (OperationControl)",
        "register": OperationControl,
        "value": OperationControlPayload(
            OperationMode=OperationMode.ACTIVE,
            DumpRegisters=False,
            MuteReplies=False,
            VisualIndicators=EnableFlag.ENABLED,
            OperationLed=EnableFlag.ENABLED,
            Heartbeat=EnableFlag.ENABLED,
        ),
        "msg_type": MessageType.WRITE,
    },
    {
        "name": "StructPayload homog (AnalogData S16x3)",
        "register": AnalogData,
        "value": AnalogDataPayload(AnalogInput0=100, Encoder=-200, AnalogInput1=300),
        "msg_type": MessageType.EVENT,
    },
    {
        "name": "StructPayload hetero (ComplexConfig)",
        "register": ComplexConfiguration,
        "value": ComplexConfigPayload(
            pwm_port=3,
            duty_cycle=0.75,
            frequency=1000.0,
            events_enabled=True,
            delta=500,
            name="benchmark",
        ),
        "msg_type": MessageType.WRITE,
    },
    {
        "name": "Masked struct (StartPulseTrain U16x2)",
        "register": StartPulseTrain,
        "value": StartPulseTrainPayload(
            pulse_width=200,
            digital_output=PwmPort.PWM2,
            pulse_count=10,
            frequency=50,
        ),
        "msg_type": MessageType.WRITE,
    },
    {
        "name": "Raw bytes (DeviceName U8x25)",
        "register": DeviceName,
        "value": list(b"benchmark_device") + [0] * 9,
        "msg_type": MessageType.WRITE,
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

REPEATS = 20
NUMBER = 1000
MIN_TIME = 0.1


def _bench(fn, label: str) -> dict[str, float]:
    timer = Timer(fn)
    loops, total = timer.autorange()
    while total < MIN_TIME:
        loops *= 2
        total = timer.timeit(number=loops)

    samples = timer.repeat(repeat=REPEATS, number=loops)
    per_op = [s / loops for s in samples]
    return {
        "min": min(per_op),
        "mean": mean(per_op),
        "max": max(per_op),
        "stdev": stdev(per_op) if len(per_op) > 1 else 0.0,
        "loops": loops,
    }


def main() -> None:
    print("=" * 80)
    print("Per-message encode/decode microbenchmark")
    print("=" * 80)
    print(f"  repeats={REPEATS}, auto-range with min_time={MIN_TIME}s")
    print()

    header = f"{'Pattern':<42s} {'encode (us)':>11s} {'decode (us)':>11s} {'roundtrip (us)':>14s}"
    print(header)
    print("-" * len(header))

    for case in CASES:
        reg = case["register"]
        val = case["value"]
        msg_type = case["msg_type"]

        # Pre-build the message for decode benchmarking
        if val is not None:
            msg = reg.format(val, msg_type)
        else:
            msg = reg.format(None, MessageType.READ)

        encode_stats = _bench(lambda r=reg, v=val, mt=msg_type: r.format(v, mt), "encode")
        decode_stats = _bench(lambda r=reg, m=msg: r.parse(m), "decode")

        enc_us = encode_stats["min"] * 1e6
        dec_us = decode_stats["min"] * 1e6
        rt_us = enc_us + dec_us

        print(f"  {case['name']:<40s} {enc_us:>10.2f} {dec_us:>10.2f} {rt_us:>13.2f}")

    print()
    print("All times are min-of-repeats in microseconds (lower is better).")


if __name__ == "__main__":
    main()
