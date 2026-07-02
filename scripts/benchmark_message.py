"""Per-message encode/decode microbenchmark.

Measures RegisterBase.format() and RegisterBase.parse() for each register
pattern, reporting min/mean/max per operation in microseconds.

Includes a "raw struct" baseline for patterns where the encode/decode work
is dominated by struct.pack/unpack, so framework overhead is visible.

Usage:
    uv run python scripts/benchmark_message.py
"""

from __future__ import annotations

import struct
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
    OperationControlPayload,
    RegisterAccess,
    RegisterBase,
    StructPayload,
    WhoAmI,
    DeviceName,
    OperationControl,
    ResetDevice,
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
    name: str = payload_field(PayloadType.U8, offset=17, length=33, interface_type=str)


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
        PayloadType.U16, offset=0, mask=0x0C00, interface_type=PwmPort
    )
    pulse_count: int = payload_field(PayloadType.U16, offset=2, mask=0x00FF, interface_type=int)
    frequency: int = payload_field(PayloadType.U16, offset=2, mask=0xFF00, interface_type=int)


class StartPulseTrain(RegisterBase[StartPulseTrainPayload]):
    address = 101
    access = RegisterAccess.WRITABLE


# ---------------------------------------------------------------------------
# Raw struct baselines (no register framework, just struct.pack/unpack)
# ---------------------------------------------------------------------------

_ANALOG_FMT = "<3h"
_ANALOG_PACKED = struct.pack(_ANALOG_FMT, 100, -200, 300)

_PULSE_FMT = "<2H"
_PULSE_PACKED = struct.pack(_PULSE_FMT, 200 | (2 << 10), 10 | (50 << 8))


def _raw_analog_encode():
    return struct.pack(_ANALOG_FMT, 100, -200, 300)


def _raw_analog_decode():
    return struct.unpack(_ANALOG_FMT, _ANALOG_PACKED)


def _raw_complex_encode():
    buf = bytearray(50)
    struct.pack_into("<B", buf, 0, 3)
    struct.pack_into("<f", buf, 4, 0.75)
    struct.pack_into("<f", buf, 8, 1000.0)
    struct.pack_into("<B", buf, 12, 1)
    struct.pack_into("<I", buf, 13, 500)
    buf[17:26] = b"benchmark"
    return bytes(buf)


_COMPLEX_RAW = _raw_complex_encode()


def _raw_complex_decode():
    pwm_port = struct.unpack_from("<B", _COMPLEX_RAW, 0)[0]
    duty_cycle = struct.unpack_from("<f", _COMPLEX_RAW, 4)[0]
    frequency = struct.unpack_from("<f", _COMPLEX_RAW, 8)[0]
    events_enabled = struct.unpack_from("<B", _COMPLEX_RAW, 12)[0]
    delta = struct.unpack_from("<I", _COMPLEX_RAW, 13)[0]
    name = _COMPLEX_RAW[17:50].rstrip(b"\x00").decode("utf-8")
    return (pwm_port, duty_cycle, frequency, events_enabled, delta, name)


def _raw_pulse_encode():
    return struct.pack(_PULSE_FMT, 200 | (2 << 10), 10 | (50 << 8))


def _raw_pulse_decode():
    w0, w1 = struct.unpack(_PULSE_FMT, _PULSE_PACKED)
    return (w0 & 0x3FF, (w0 >> 10) & 0x3, w1 & 0xFF, (w1 >> 8) & 0xFF)


# ---------------------------------------------------------------------------
# Benchmark cases
# ---------------------------------------------------------------------------

CASES = [
    {
        "name": "Scalar int (WhoAmI U16)",
        "register": WhoAmI,
        "value": 1234,
        "msg_type": MessageType.READ,
        "raw_encode": None,
        "raw_decode": None,
    },
    {
        "name": "IntFlag (ResetDevice U8)",
        "register": ResetDevice,
        "value": ResetFlags.RESTORE_DEFAULT | ResetFlags.SAVE,
        "msg_type": MessageType.WRITE,
        "raw_encode": None,
        "raw_decode": None,
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
        "raw_encode": None,
        "raw_decode": None,
    },
    {
        "name": "StructPayload homog (AnalogData S16x3)",
        "register": AnalogData,
        "value": AnalogDataPayload(AnalogInput0=100, Encoder=-200, AnalogInput1=300),
        "msg_type": MessageType.EVENT,
        "raw_encode": _raw_analog_encode,
        "raw_decode": _raw_analog_decode,
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
        "raw_encode": _raw_complex_encode,
        "raw_decode": _raw_complex_decode,
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
        "raw_encode": _raw_pulse_encode,
        "raw_decode": _raw_pulse_decode,
    },
    {
        "name": "Raw bytes (DeviceName U8x25)",
        "register": DeviceName,
        "value": list(b"benchmark_device") + [0] * 9,
        "msg_type": MessageType.WRITE,
        "raw_encode": None,
        "raw_decode": None,
    },
]


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

REPEATS = 20
MIN_TIME = 0.1


def _bench(fn) -> dict[str, float]:
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

    header = (
        f"{'Pattern':<42s} {'encode':>10s} {'decode':>10s} "
        f"{'roundtrip':>10s} {'raw_struct':>10s} {'overhead':>8s}"
    )
    print(header)
    print("-" * len(header))

    for case in CASES:
        reg = case["register"]
        val = case["value"]
        msg_type = case["msg_type"]

        if val is not None:
            msg = reg.format(val, msg_type)
        else:
            msg = reg.format(None, MessageType.READ)

        encode_stats = _bench(lambda r=reg, v=val, mt=msg_type: r.format(v, mt))
        decode_stats = _bench(lambda r=reg, m=msg: r.parse(m))

        enc_us = encode_stats["min"] * 1e6
        dec_us = decode_stats["min"] * 1e6
        rt_us = enc_us + dec_us

        raw_str = ""
        overhead_str = ""
        if case["raw_encode"] is not None and case["raw_decode"] is not None:
            raw_enc = _bench(case["raw_encode"])
            raw_dec = _bench(case["raw_decode"])
            raw_us = raw_enc["min"] * 1e6 + raw_dec["min"] * 1e6
            raw_str = f"{raw_us:>9.2f}"
            overhead_str = f"{rt_us / raw_us:>7.1f}x"

        print(
            f"  {case['name']:<40s} {enc_us:>9.2f} {dec_us:>9.2f} "
            f"{rt_us:>9.2f} {raw_str:>10s} {overhead_str:>8s}"
        )

    print()
    print("All times in microseconds (min-of-repeats, lower is better).")
    print("raw_struct = bare struct.pack/unpack without register framework or message framing.")
    print("overhead   = roundtrip / raw_struct.")


if __name__ == "__main__":
    main()
