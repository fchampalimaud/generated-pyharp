import struct
import timeit
from dataclasses import dataclass

from harp.protocol import MessageType, PayloadType
from harp.protocol.message import HarpMessage
from harp.protocol.registers import (
    RegisterAccess,
    RegisterBase,
    StructPayload,
    payload_field,
)


@dataclass
class ComplexConfigPayload(StructPayload):
    pwm_port: int = payload_field(PayloadType.U8, offset=0)
    duty_cycle: float = payload_field(PayloadType.FLOAT, offset=4)
    frequency: float = payload_field(PayloadType.FLOAT, offset=8)
    events_enabled: bool = payload_field(PayloadType.U8, offset=12)
    delta: int = payload_field(PayloadType.U32, offset=13)
    name: str = payload_field(PayloadType.U8, offset=17, length=33, is_string=True)


class ComplexConfig(RegisterBase[ComplexConfigPayload]):
    address = 34
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL


val = ComplexConfigPayload(
    pwm_port=3,
    duty_cycle=0.75,
    frequency=1000.0,
    events_enabled=True,
    delta=500,
    name="benchmark",
)

N = 100000

t = timeit.timeit(lambda: val.encode(), number=N)
print(f"StructPayload.encode():        {t / N * 1e6:.2f} us")

encoded = val.encode()
t = timeit.timeit(
    lambda: HarpMessage.from_payload(
        encoded,
        message_type=MessageType.WRITE,
        address=34,
        payload_type=PayloadType.U8,
    ),
    number=N,
)
print(f"HarpMessage.from_payload():    {t / N * 1e6:.2f} us")

t = timeit.timeit(
    lambda: HarpMessage._get_raw_payload(PayloadType.U8, encoded), number=N
)
print(f"  _get_raw_payload():          {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: HarpMessage._get_raw_timestamp(None), number=N)
print(f"  _get_raw_timestamp(None):    {t / N * 1e6:.2f} us")

msg = ComplexConfig.format(val, MessageType.WRITE)
raw = msg.to_bytes()
t = timeit.timeit(lambda: HarpMessage._calculate_checksum(raw), number=N)
print(f"  _calculate_checksum():       {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: HarpMessage(raw), number=N)
print(f"  HarpMessage.__init__():      {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: msg._get_payload(), number=N)
print(f"  _get_payload():              {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: ComplexConfig.format(val, MessageType.WRITE), number=N)
print(f"ComplexConfig.format() total:  {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: ComplexConfig.parse(msg), number=N)
print(f"ComplexConfig.parse() total:   {t / N * 1e6:.2f} us")

payload_list = msg.payload
t = timeit.timeit(lambda: ComplexConfigPayload.decode(payload_list), number=N)
print(f"StructPayload.decode():        {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: ComplexConfig.supports(MessageType.WRITE), number=N)
print(f"supports() check:              {t / N * 1e6:.2f} us")

print()
print("--- raw struct baseline ---")


def _raw_encode():
    buf = bytearray(50)
    struct.pack_into("<B", buf, 0, 3)
    struct.pack_into("<f", buf, 4, 0.75)
    struct.pack_into("<f", buf, 8, 1000.0)
    struct.pack_into("<B", buf, 12, 1)
    struct.pack_into("<I", buf, 13, 500)
    buf[17:26] = b"benchmark"
    return bytes(buf)


_RAW = _raw_encode()


def _raw_decode():
    pwm_port = struct.unpack_from("<B", _RAW, 0)[0]
    duty_cycle = struct.unpack_from("<f", _RAW, 4)[0]
    frequency = struct.unpack_from("<f", _RAW, 8)[0]
    events_enabled = struct.unpack_from("<B", _RAW, 12)[0]
    delta = struct.unpack_from("<I", _RAW, 13)[0]
    name = _RAW[17:50].rstrip(b"\x00").decode("utf-8")
    return (pwm_port, duty_cycle, frequency, events_enabled, delta, name)


t = timeit.timeit(_raw_encode, number=N)
print(f"raw struct encode:             {t / N * 1e6:.2f} us")
t = timeit.timeit(_raw_decode, number=N)
print(f"raw struct decode:             {t / N * 1e6:.2f} us")
