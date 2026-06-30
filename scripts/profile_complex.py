import time

import pandas as pd
from benchmark_common import (
    DUMP_PATH,
    DUMP_PATH_COMPLEX,
    PAYLOAD_TYPE,
    AnalogData,
    ComplexConfiguration,
)
from harp.data import ValidationMode, load_register_dump
from harp.protocol import PayloadType

results = {}


def profile_path(label, path, register_cls, payload_type):
    print(f"\n=== {label} ===")

    # Step 1: file read + header validation (no column extraction yet)
    t0 = time.perf_counter()
    dump = load_register_dump(
        path, register_cls, payload_type, validation=ValidationMode.HEADER
    )
    t1 = time.perf_counter()
    load_ms = (t1 - t0) * 1000
    print(f"  load_register_dump: {load_ms:.2f} ms  ({len(dump)} entries)")

    # Step 2: column extraction (triggers threaded AoS-to-SoA for struct payloads)
    t2 = time.perf_counter()
    cols = dump.payload_columns(copy=False)
    t3 = time.perf_counter()
    extract_ms = (t3 - t2) * 1000
    print(f"  payload_columns:    {extract_ms:.2f} ms  ({len(cols)} columns)")

    # Step 3a: DataFrame (copy=False — zero-copy, shares memory with dump)
    t4 = time.perf_counter()
    df = pd.DataFrame(cols, copy=False)
    t5 = time.perf_counter()
    df_no_copy_ms = (t5 - t4) * 1000
    print(f"  DataFrame(copy=False):  {df_no_copy_ms:.2f} ms  dtypes={list(df.dtypes)}")

    # Step 3b: DataFrame (copy=True, default — numpy-level copy, safe)
    t6 = time.perf_counter()
    df_copy = pd.DataFrame(dump.payload_columns(copy=True), copy=False)  # noqa: F841
    t7 = time.perf_counter()
    df_copy_ms = (t7 - t6) * 1000
    print(f"  DataFrame(copy=True):   {df_copy_ms:.2f} ms")

    total_no_copy = load_ms + extract_ms + df_no_copy_ms
    total_copy = load_ms + extract_ms + df_copy_ms
    print(f"  TOTAL (copy=False): {total_no_copy:.2f} ms")
    print(f"  TOTAL (copy=True):  {total_copy:.2f} ms")

    results[label] = {
        "entries": len(dump),
        "total_no_copy_ms": total_no_copy,
        "total_copy_ms": total_copy,
    }


profile_path("AnalogData (homogeneous)", DUMP_PATH, AnalogData, PAYLOAD_TYPE)
profile_path(
    "ComplexConfig (struct)",
    DUMP_PATH_COMPLEX,
    ComplexConfiguration,
    PayloadType.TIMESTAMPED_U8,
)

# --- Comparison ---
analog = results["AnalogData (homogeneous)"]
complex_ = results["ComplexConfig (struct)"]

print("\n=== Comparison (per-entry) ===")
for copy_label, key in [
    ("copy=False", "total_no_copy_ms"),
    ("copy=True", "total_copy_ms"),
]:
    analog_us = analog[key] * 1000 / analog["entries"]
    complex_us = complex_[key] * 1000 / complex_["entries"]
    slowdown = complex_us / analog_us
    estimated_ms = complex_us * analog["entries"] / 1000

    print(f"  --- {copy_label} ---")
    print(
        f"  AnalogData:     {analog_us:.3f} µs/entry  ({analog['entries']:,} entries)"
    )
    print(
        f"  ComplexConfig:  {complex_us:.3f} µs/entry  ({complex_['entries']:,} entries)"
    )
    print(f"  Slowdown:       {slowdown:.1f}x per entry")
    print(
        f"  ComplexConfig @ {analog['entries']:,} entries (estimate): "
        f"{estimated_ms:.0f} ms"
    )
