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
class AnalogDataPayload(StructPayload):
    AnalogInput0: int = payload_field(PayloadType.S16, offset=0)
    Encoder: int = payload_field(PayloadType.S16, offset=2)
    AnalogInput1: int = payload_field(PayloadType.S16, offset=4)


class AnalogData(RegisterBase[AnalogDataPayload]):
    address = 44
    access = RegisterAccess.EVENTFUL


val = AnalogDataPayload(AnalogInput0=100, Encoder=-200, AnalogInput1=300)

N = 100000

t = timeit.timeit(lambda: val.encode(), number=N)
print(f"StructPayload.encode():        {t / N * 1e6:.2f} us")

encoded = val.encode()
t = timeit.timeit(
    lambda: HarpMessage.from_payload(
        encoded,
        message_type=MessageType.EVENT,
        address=44,
        payload_type=PayloadType.S16,
    ),
    number=N,
)
print(f"HarpMessage.from_payload():    {t / N * 1e6:.2f} us")

t = timeit.timeit(
    lambda: HarpMessage._get_raw_payload(PayloadType.S16, encoded), number=N
)
print(f"  _get_raw_payload():          {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: HarpMessage._get_raw_timestamp(None), number=N)
print(f"  _get_raw_timestamp(None):    {t / N * 1e6:.2f} us")

msg = AnalogData.format(val, MessageType.EVENT)
raw = msg.to_bytes()
t = timeit.timeit(lambda: HarpMessage._calculate_checksum(raw), number=N)
print(f"  _calculate_checksum():       {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: HarpMessage(raw), number=N)
print(f"  HarpMessage.__init__():      {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: msg._get_payload(), number=N)
print(f"  _get_payload():              {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: AnalogData.format(val, MessageType.EVENT), number=N)
print(f"AnalogData.format() total:     {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: AnalogData.parse(msg), number=N)
print(f"AnalogData.parse() total:      {t / N * 1e6:.2f} us")

payload_list = msg.payload
t = timeit.timeit(lambda: AnalogDataPayload.decode(payload_list), number=N)
print(f"StructPayload.decode():        {t / N * 1e6:.2f} us")

t = timeit.timeit(lambda: AnalogData.supports(MessageType.EVENT), number=N)
print(f"supports() check:              {t / N * 1e6:.2f} us")

print()
print("--- raw struct baseline ---")
fmt = "<3h"
packed = struct.pack(fmt, 100, -200, 300)
t = timeit.timeit(lambda: struct.pack(fmt, 100, -200, 300), number=N)
print(f'struct.pack("<3h"):            {t / N * 1e6:.2f} us')
t = timeit.timeit(lambda: struct.unpack(fmt, packed), number=N)
print(f'struct.unpack("<3h"):          {t / N * 1e6:.2f} us')
