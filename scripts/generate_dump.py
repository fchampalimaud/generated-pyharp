# This generates synthetic .bin dump files for benchmarking struct payloads.

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from harp.protocol import MessageType, PayloadType
from harp.protocol.registers import StructField

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
        _fill_string_field(buf, col_start, byte_size, num_entries, rng)
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


def _fill_string_field(
    buf: np.ndarray,
    col_start: int,
    max_len: int,
    num_entries: int,
    rng: np.random.Generator,
) -> None:
    """Vectorized random string generation — no Python row loop."""
    str_lens = rng.integers(1, max_len + 1, size=num_entries)
    indices = np.arange(max_len)
    mask = indices[np.newaxis, :] < str_lens[:, np.newaxis]  # (N, max_len)
    chars = rng.integers(
        ord("a"), ord("z") + 1, size=(num_entries, max_len), dtype=np.uint8
    )
    chars[~mask] = 0  # null-pad beyond length
    buf[:, col_start : col_start + max_len] = chars


def generate_dump(
    path: Path,
    *,
    address: int,
    payload_type: PayloadType,
    payload_struct: tuple[StructField, ...],
    payload_size: int,
    num_entries: int,
    frequency_hz: float = 1000.0,
    start_seconds: int = 100,
    seed: int = 42,
) -> None:
    rng = np.random.default_rng(seed)

    has_timestamp = payload_type.has_timestamp()
    header_size = 5 + (6 if has_timestamp else 0)
    frame_size = header_size + payload_size + 1  # +1 checksum
    length_byte = frame_size - 2

    # Allocate raw byte buffer
    buf = np.zeros((num_entries, frame_size), dtype=np.uint8)

    # ── Header (constant across all frames) ──
    buf[:, 0] = int(MessageType.EVENT)
    buf[:, 1] = length_byte
    buf[:, 2] = address
    buf[:, 3] = 255  # port
    buf[:, 4] = int(payload_type)

    # ── Timestamps at ~frequency_hz with small jitter ──
    if has_timestamp:
        interval = 1.0 / frequency_hz
        jitter = rng.normal(0, interval * 0.01, size=num_entries)
        timestamps = start_seconds + np.cumsum(np.full(num_entries, interval) + jitter)
        seconds = np.floor(timestamps).astype(np.uint32)
        ticks = ((timestamps - seconds) / TICK_PERIOD_S).astype(np.uint16)

        buf[:, 5:9] = seconds.view(np.uint8).reshape(num_entries, 4)
        buf[:, 9:11] = ticks.view(np.uint8).reshape(num_entries, 2)

    # ── Payload fields ──
    payload_offset = header_size
    for field in payload_struct:
        _fill_field(buf, payload_offset, field, num_entries, rng)

    # ── Checksum ──
    buf[:, -1] = buf[:, :-1].sum(axis=1, dtype=np.uint8)

    path.parent.mkdir(parents=True, exist_ok=True)
    buf.tofile(path)

    size_mib = path.stat().st_size / (1024**2)
    print(f"Generated {num_entries:,} frames → {path} ({size_mib:.1f} MiB)")


COMPLEX_CONFIG_STRUCT = (
    StructField("pwm_port", PayloadType.U8, offset=0),
    StructField("duty_cycle", PayloadType.FLOAT, offset=4),
    StructField("frequency", PayloadType.FLOAT, offset=8),
    StructField("events_enabled", PayloadType.U8, offset=12),
    StructField("delta", PayloadType.U32, offset=13),
    StructField("name", PayloadType.U8, offset=17, length=33, is_string=True),
)
COMPLEX_CONFIG_PAYLOAD_SIZE = 50
COMPLEX_CONFIG_ADDRESS = 34


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic .bin dumps")
    parser.add_argument("--entries", type=int, default=1_700_000)
    parser.add_argument("--frequency", type=float, default=1000.0)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "data" / "complex_config_34.bin",
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    generate_dump(
        args.output,
        address=COMPLEX_CONFIG_ADDRESS,
        payload_type=PayloadType.TIMESTAMPED_U8,
        payload_struct=COMPLEX_CONFIG_STRUCT,
        payload_size=COMPLEX_CONFIG_PAYLOAD_SIZE,
        num_entries=args.entries,
        frequency_hz=args.frequency,
        seed=args.seed,
    )


if __name__ == "__main__":
    main()
