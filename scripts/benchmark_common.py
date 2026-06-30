from __future__ import annotations

import importlib.util
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from harp.data import RegisterDump, ValidationMode, load_register_dump
from harp.protocol import PayloadType
from harp.protocol.registers import RegisterBase, RegisterAccess, StructField

CURRENT_DIR = Path(__file__).resolve().parent
# NOTE: change this path to point to the actual dump file you want to benchmark (ours is ~123MB, ~2h session)
DUMP_PATH = CURRENT_DIR / "data" / "behavior_44.bin"
DUMP_PATH_COMPLEX = CURRENT_DIR / "data" / "complex_config_34.bin"

LEGACY_HARP_IO_PATH = CURRENT_DIR / "_harp_io.py"

VALIDATION = ValidationMode.HEADER


# NOTE: Example for complex configuration based on the complex configuratione example in https://github.com/harp-tech/generators/pull/87
# and added a string field to demonstrate string generation.
@dataclass
class ComplexConfigPayload:
    pwm_port: int
    duty_cycle: float
    frequency: float
    events_enabled: bool
    delta: int
    name: str


class ComplexConfiguration(RegisterBase[ComplexConfigPayload]):
    address = 34
    payload_type = PayloadType.U8
    decode = lambda p: ComplexConfigPayload(
        pwm_port=p[0],
        duty_cycle=struct.unpack_from("<f", bytes(p), 4)[0],
        frequency=struct.unpack_from("<f", bytes(p), 8)[0],
        events_enabled=p[12] != 0,
        delta=int.from_bytes(bytes(p[13:17]), "little"),
        name=bytes(p[17:50]).rstrip(b"\x00").decode("utf-8"),
    )
    encode = lambda v: [
        v.pwm_port,
        0,
        0,
        0,
        *struct.pack("<f", v.duty_cycle),
        *struct.pack("<f", v.frequency),
        1 if v.events_enabled else 0,
        *v.delta.to_bytes(4, "little"),
        *v.name.encode("utf-8").ljust(33, b"\x00"),
    ]
    count = 50
    access = RegisterAccess.WRITABLE | RegisterAccess.EVENTFUL
    payload_struct = (
        StructField("pwm_port", PayloadType.U8, offset=0),
        StructField("duty_cycle", PayloadType.FLOAT, offset=4),
        StructField("frequency", PayloadType.FLOAT, offset=8),
        StructField("events_enabled", PayloadType.U8, offset=12),
        StructField("delta", PayloadType.U32, offset=13),
        StructField("name", PayloadType.U8, offset=17, length=33, is_string=True),
    )


# NOTE: Defined here to avoid the generation of the Behavior device generation. This is what is currently generated.
@dataclass
class AnalogDataPayload:
    # The voltage at the output of the ADC channel 0.
    AnalogInput0: int
    # The quadrature counter value on Port 2
    Encoder: int
    # The voltage at the output of the ADC channel 1.
    AnalogInput1: int


# NOTE: Defined here to avoid the generation of the Behavior device generation. This is what is currently generated.
class AnalogData(RegisterBase[AnalogDataPayload]):
    address = 44  # BehaviorRegisters.ANALOG_DATA on the Behavior generated code
    payload_type = PayloadType.S16
    decode = lambda payload: AnalogDataPayload(
        AnalogInput0=payload[0],
        Encoder=payload[1],
        AnalogInput1=payload[2],
    )
    encode = lambda value: [
        value.AnalogInput0,
        value.Encoder,
        value.AnalogInput1,
    ]
    count = 3
    access = RegisterAccess.EVENTFUL
    fields = (
        "AnalogInput0",
        "Encoder",
        "AnalogInput1",
    )


REGISTER = AnalogData
PAYLOAD_TYPE = PayloadType.TIMESTAMPED_S16
ANALOG_COLUMNS = ("AnalogInput0", "Encoder", "AnalogInput1")


@dataclass(frozen=True)
class BenchmarkCase:
    name: str
    label: str
    baseline_name: str | None
    run: Callable[[], Any]


def _load_module(name: str, path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"Could not find vendored helper at {path}")

    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load module spec for {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_legacy_module = _load_module("legacy_harp_io", LEGACY_HARP_IO_PATH)
HARP_READ = _legacy_module.read


# ---------------------------------------------------------------------------
# harp.data helpers
# ---------------------------------------------------------------------------


def harp_data_dump(
    path: Path,
    register_cls: type[RegisterBase] = REGISTER,
    payload_type: PayloadType = PAYLOAD_TYPE,
) -> RegisterDump:
    return load_register_dump(
        path,
        register_cls,
        payload_type,
        validation=VALIDATION,
    )


def harp_data_dataframe(
    path: Path,
    register_cls: type[RegisterBase] = REGISTER,
    payload_type: PayloadType = PAYLOAD_TYPE,
    *,
    include_timestamp: bool,
    copy: bool = True,
) -> pd.DataFrame:
    dump = harp_data_dump(path, register_cls, payload_type)
    data = dump.columns(
        include_timestamp=include_timestamp, timestamp="float", copy=copy
    )
    return pd.DataFrame(data, copy=False)


# ---------------------------------------------------------------------------
# harp-python helpers
# ---------------------------------------------------------------------------


def harp_python_dataframe(path: Path, *, include_timestamp: bool) -> pd.DataFrame:
    df = HARP_READ(path, columns=list(ANALOG_COLUMNS))

    if include_timestamp:
        result = df.reset_index().rename(columns={"Time": "timestamp"})
        return result.loc[:, ["timestamp", *ANALOG_COLUMNS]]

    result = df.reset_index(drop=True)
    return result.loc[:, list(ANALOG_COLUMNS)]


# ---------------------------------------------------------------------------
# Dataset info & sanity checks
# ---------------------------------------------------------------------------


def dataset_summary(path: Path = DUMP_PATH) -> dict[str, float | int | Path]:
    if not path.exists():
        raise FileNotFoundError(f"Dump file not found: {path}")

    data = np.fromfile(path, dtype=np.uint8)
    if len(data) == 0:
        raise ValueError(f"Dump file is empty: {path}")

    stride = int(data[1]) + 2
    nrows = len(data) // stride
    size_mib = path.stat().st_size / (1024**2)

    return {
        "path": path,
        "rows": nrows,
        "stride": stride,
        "size_mib": size_mib,
    }


def print_sample_output(path: Path = DUMP_PATH) -> None:
    print("\nSample output (harp-python, first 3 rows):")
    print(
        harp_python_dataframe(path, include_timestamp=True)
        .head(3)
        .to_string(index=False)
    )

    print("\nSample output (harp.data, first 3 rows):")
    print(
        harp_data_dataframe(path, include_timestamp=True).head(3).to_string(index=False)
    )

    if DUMP_PATH_COMPLEX.exists():
        print("\nSample output (harp.data, complex config, first 3 rows):")
        print(
            harp_data_dataframe(
                DUMP_PATH_COMPLEX,
                ComplexConfiguration,
                PayloadType.TIMESTAMPED_U8,
                include_timestamp=True,
            )
            .head(3)
            .to_string(index=False)
        )


def sanity_check(path: Path = DUMP_PATH) -> None:
    legacy = harp_python_dataframe(path, include_timestamp=False)
    current = harp_data_dataframe(path, include_timestamp=False)

    assert list(current.columns) == list(legacy.columns), (
        f"column mismatch: harp-python={list(legacy.columns)!r}, harp.data={list(current.columns)!r}"
    )
    assert len(current) == len(legacy), (
        f"row count mismatch: harp-python={len(legacy)}, harp.data={len(current)}"
    )
    for column in ANALOG_COLUMNS:
        np.testing.assert_array_equal(
            legacy[column].to_numpy(),
            current[column].to_numpy(),
            err_msg=f"column {column!r} differs between harp-python and harp.data",
        )

    legacy_ts = harp_python_dataframe(path, include_timestamp=True)
    current_ts = harp_data_dataframe(path, include_timestamp=True)

    np.testing.assert_allclose(
        legacy_ts["timestamp"].to_numpy(),
        current_ts["timestamp"].to_numpy(),
        err_msg="timestamp column differs between harp-python and harp.data",
    )

    print(
        f"  Sanity check passed: {len(legacy_ts):,} rows, "
        f"payload columns and timestamps match."
    )


# ---------------------------------------------------------------------------
# Benchmark cases
# ---------------------------------------------------------------------------


def comparison_cases(path: Path = DUMP_PATH) -> list[BenchmarkCase]:
    return [
        BenchmarkCase(
            name="harp_python_ts",
            label="harp-python  read() + timestamp",
            baseline_name=None,
            run=lambda path=path: harp_python_dataframe(path, include_timestamp=True),
        ),
        BenchmarkCase(
            name="harp_python_no_ts",
            label="harp-python  read() without timestamp",
            baseline_name=None,
            run=lambda path=path: harp_python_dataframe(path, include_timestamp=False),
        ),
        BenchmarkCase(
            name="harp_data_ts_no_copy",
            label="harp.data    load + DataFrame + timestamp (no copy)",
            baseline_name="harp_python_ts",
            run=lambda path=path: harp_data_dataframe(
                path, include_timestamp=True, copy=False
            ),
        ),
        BenchmarkCase(
            name="harp_data_ts_copy",
            label="harp.data    load + DataFrame + timestamp (copy)",
            baseline_name="harp_python_ts",
            run=lambda path=path: harp_data_dataframe(
                path, include_timestamp=True, copy=True
            ),
        ),
        BenchmarkCase(
            name="harp_data_no_ts_no_copy",
            label="harp.data    load + DataFrame without timestamp (no copy)",
            baseline_name="harp_python_no_ts",
            run=lambda path=path: harp_data_dataframe(
                path, include_timestamp=False, copy=False
            ),
        ),
        BenchmarkCase(
            name="harp_data_no_ts_copy",
            label="harp.data    load + DataFrame without timestamp (copy)",
            baseline_name="harp_python_no_ts",
            run=lambda path=path: harp_data_dataframe(
                path, include_timestamp=False, copy=True
            ),
        ),
        BenchmarkCase(
            name="harp_data_no_ts_no_copy_complex",
            label="harp.data    load + DataFrame without timestamp (no copy) - complex",
            baseline_name=None,
            run=lambda path=DUMP_PATH_COMPLEX: harp_data_dataframe(
                path,
                ComplexConfiguration,
                PayloadType.TIMESTAMPED_U8,
                include_timestamp=False,
                copy=False,
            ),
        ),
        BenchmarkCase(
            name="harp_data_no_ts_copy_complex",
            label="harp.data    load + DataFrame without timestamp (copy) - complex",
            baseline_name=None,
            run=lambda path=DUMP_PATH_COMPLEX: harp_data_dataframe(
                path,
                ComplexConfiguration,
                PayloadType.TIMESTAMPED_U8,
                include_timestamp=False,
                copy=True,
            ),
        ),
    ]


def print_ratio_summary(
    title: str,
    summary: dict[str, dict[str, float]],
    cases: list[BenchmarkCase],
) -> None:
    print(f"\n{title}")
    for case in cases:
        if case.baseline_name is None:
            continue

        baseline = summary[case.baseline_name]
        current = summary[case.name]

        ratio_min = current["min"] / baseline["min"]
        ratio_mean = current["mean"] / baseline["mean"]
        direction = "slower" if ratio_mean > 1 else "faster"

        print(
            f"  {case.label:<52s}"
            f"min={ratio_min:.2f}x  "
            f"mean={ratio_mean:.2f}x  "
            f"({direction} by {abs(ratio_mean - 1) * 100:.0f}% on mean)"
        )
