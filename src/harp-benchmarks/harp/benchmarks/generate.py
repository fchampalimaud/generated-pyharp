from __future__ import annotations

import argparse

import numpy as np
from harp.protocol import MessageType, PayloadType
from harp.protocol.registers import RegisterBase, StructField

from harp.benchmarks._registers import (
    BENCHMARK_REGISTERS,
    BenchmarkedRegister,
    corpus_path,
)

TICK_PERIOD_S = 32e-6


def _fill_field(
    buf: np.ndarray,
    payload_offset: int,
    field: StructField,
    num_entries: int,
    rng: np.random.Generator,
) -> None:
    col_start = payload_offset + field.offset
    byte_size = field.byte_size

    if field.is_string:
        str_lens = rng.integers(1, byte_size + 1, size=num_entries)
        indices = np.arange(byte_size)
        mask = indices[np.newaxis, :] < str_lens[:, np.newaxis]
        chars = rng.integers(
            ord("a"), ord("z") + 1, size=(num_entries, byte_size), dtype=np.uint8
        )
        chars[~mask] = 0
        buf[:, col_start : col_start + byte_size] = chars
        return

    element_size = field.type.type_size()
    element_count = byte_size // element_size

    if field.type.is_float():
        values = rng.uniform(0.0, 100.0, size=(num_entries, element_count)).astype(
            np.float32
        )
    elif field.type.is_signed():
        info = np.iinfo(f"int{element_size * 8}")
        values = rng.integers(
            info.min,
            info.max + 1,
            size=(num_entries, element_count),
            dtype=np.dtype(f"<i{element_size}"),
        )
    else:
        info = np.iinfo(f"uint{element_size * 8}")
        values = rng.integers(
            0,
            info.max + 1,
            size=(num_entries, element_count),
            dtype=np.dtype(f"<u{element_size}"),
        )

    buf[:, col_start : col_start + byte_size] = values.view(np.uint8).reshape(
        num_entries, byte_size
    )


def _resolve_payload_type(register_cls: type[RegisterBase]) -> PayloadType:
    raw = int(register_cls.payload_type)
    raw |= 0x10  # HAS_TIMESTAMP
    return PayloadType(raw)


def _payload_nbytes(register_cls: type[RegisterBase], payload_type: PayloadType) -> int:
    type_size = payload_type.type_size()
    return register_cls.count * type_size


def generate_one(
    reg: BenchmarkedRegister,
    entries: int,
    *,
    frequency_hz: float = 1000.0,
    start_seconds: int = 100,
    seed: int = 42,
) -> None:
    register_cls = reg.register
    rng = np.random.default_rng(seed)

    payload_type = _resolve_payload_type(register_cls)
    payload_size = _payload_nbytes(register_cls, payload_type)

    header_size = 5 + 6  # always timestamped
    frame_size = header_size + payload_size + 1
    length_byte = frame_size - 2

    buf = np.zeros((entries, frame_size), dtype=np.uint8)

    buf[:, 0] = int(MessageType.EVENT)
    buf[:, 1] = length_byte
    buf[:, 2] = register_cls.address
    buf[:, 3] = 255
    buf[:, 4] = int(payload_type)

    interval = 1.0 / frequency_hz
    jitter = rng.normal(0, interval * 0.01, size=entries)
    timestamps = start_seconds + np.cumsum(np.full(entries, interval) + jitter)
    seconds = np.floor(timestamps).astype(np.uint32)
    ticks = ((timestamps - seconds) / TICK_PERIOD_S).astype(np.uint16)

    buf[:, 5:9] = seconds.view(np.uint8).reshape(entries, 4)
    buf[:, 9:11] = ticks.view(np.uint8).reshape(entries, 2)

    payload_offset = header_size
    if register_cls.payload_struct is not None:
        for field in register_cls.payload_struct:
            _fill_field(buf, payload_offset, field, entries, rng)
    else:
        type_size = payload_type.type_size()
        element_count = register_cls.count

        if payload_type.is_float():
            values = rng.uniform(0.0, 100.0, size=(entries, element_count)).astype(
                np.float32
            )
        elif payload_type.is_signed():
            info = np.iinfo(f"int{type_size * 8}")
            values = rng.integers(
                info.min,
                info.max + 1,
                size=(entries, element_count),
                dtype=np.dtype(f"<i{type_size}"),
            )
        else:
            info = np.iinfo(f"uint{type_size * 8}")
            values = rng.integers(
                0,
                info.max + 1,
                size=(entries, element_count),
                dtype=np.dtype(f"<u{type_size}"),
            )

        buf[:, payload_offset : payload_offset + payload_size] = values.view(
            np.uint8
        ).reshape(entries, payload_size)

    buf[:, -1] = buf[:, :-1].sum(axis=1, dtype=np.uint8)

    path = corpus_path(reg)
    path.parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(path)

    size_mib = path.stat().st_size / (1024**2)
    print(f"  {reg.name} ({entries:,} frames) -> {path} ({size_mib:.1f} MiB)")


def ensure_corpus(
    reg: BenchmarkedRegister,
    entries: int,
    *,
    force: bool = False,
) -> None:
    path = corpus_path(reg)

    payload_type = _resolve_payload_type(reg.register)
    payload_size = _payload_nbytes(reg.register, payload_type)
    frame_size = 5 + 6 + payload_size + 1
    expected_size = frame_size * entries

    if not force and path.exists() and path.stat().st_size == expected_size:
        return

    generate_one(reg, entries)


def main():
    parser = argparse.ArgumentParser(description="Generate benchmark corpus files.")
    parser.add_argument("--entries", type=int, default=1_000_000)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    registers = BENCHMARK_REGISTERS
    if args.only:
        names = set(args.only)
        registers = [r for r in registers if r.name in names]

    print(f"Generating corpus ({args.entries:,} entries per register):")
    for reg in registers:
        ensure_corpus(reg, args.entries, force=args.force)

    print("Done.")


if __name__ == "__main__":
    main()
