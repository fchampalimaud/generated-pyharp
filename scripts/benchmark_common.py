from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np
import pandas as pd
from harp.data import RegisterDump, ValidationMode, load_register_dump
from harp.protocol import PayloadType
from harp.protocol.registers import RegisterBase, RegisterAccess, StructPayload, payload_field

CURRENT_DIR = Path(__file__).resolve().parent
# NOTE: change this path to point to the actual dump file you want to benchmark (ours is ~123MB, ~2h session)
DUMP_PATH = CURRENT_DIR / "data" / "behavior_44.bin"
DUMP_PATH_COMPLEX = CURRENT_DIR / "data" / "complex_config_34.bin"

LEGACY_HARP_IO_PATH = CURRENT_DIR / "_harp_io.py"

VALIDATION = ValidationMode.HEADER


# NOTE: Example for complex configuration based on the complex configuratione example in https://github.com/harp-tech/generators/pull/87
# and added a string field to demonstrate string generation.
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


# NOTE: Defined here to avoid the generation of the Behavior device generation. This is what is currently generated.
@dataclass
class AnalogDataPayload(StructPayload):
    AnalogInput0: int = payload_field(PayloadType.S16, offset=0)
    Encoder: int = payload_field(PayloadType.S16, offset=2)
    AnalogInput1: int = payload_field(PayloadType.S16, offset=4)


# NOTE: Defined here to avoid the generation of the Behavior device generation. This is what is currently generated.
class AnalogData(RegisterBase[AnalogDataPayload]):
    address = 44
    access = RegisterAccess.EVENTFUL


REGISTER = AnalogData
PAYLOAD_TYPE = PayloadType.TIMESTAMPED_S16
ANALOG_COLUMNS = ("AnalogInput0", "Encoder", "AnalogInput1")
COMPLEX_COLUMNS = tuple(f"byte_{i}" for i in range(50))


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


def harp_python_dataframe_complex(path: Path, *, include_timestamp: bool) -> pd.DataFrame:
    df = HARP_READ(path, columns=list(COMPLEX_COLUMNS))

    if include_timestamp:
        result = df.reset_index().rename(columns={"Time": "timestamp"})
        return result.loc[:, ["timestamp", *COMPLEX_COLUMNS]]

    result = df.reset_index(drop=True)
    return result.loc[:, list(COMPLEX_COLUMNS)]


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


def sanity_check_complex(path: Path = DUMP_PATH_COMPLEX) -> None:
    if not path.exists():
        print(f"  Skipping complex sanity check: {path} not found.")
        return

    legacy = harp_python_dataframe_complex(path, include_timestamp=False)
    current = harp_data_dataframe(
        path,
        ComplexConfiguration,
        PayloadType.TIMESTAMPED_U8,
        include_timestamp=False,
    )

    assert len(current) == len(legacy), (
        f"row count mismatch: harp-python={len(legacy)}, harp.data={len(current)}"
    )

    np.testing.assert_array_equal(
        legacy["byte_0"].to_numpy(),
        current["pwm_port"].to_numpy().astype(np.uint8),
        err_msg="pwm_port (byte_0) differs between harp-python and harp.data",
    )

    legacy_ts = harp_python_dataframe_complex(path, include_timestamp=True)
    current_ts = harp_data_dataframe(
        path,
        ComplexConfiguration,
        PayloadType.TIMESTAMPED_U8,
        include_timestamp=True,
    )

    np.testing.assert_allclose(
        legacy_ts["timestamp"].to_numpy(),
        current_ts["timestamp"].to_numpy(),
        err_msg="timestamp column differs between harp-python and harp.data (complex)",
    )

    print(
        f"  Sanity check (complex) passed: {len(legacy_ts):,} rows, "
        f"pwm_port and timestamps match."
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
            name="harp_python_no_ts_complex",
            label="harp-python  read() without timestamp - complex (raw U8)",
            baseline_name=None,
            run=lambda path=DUMP_PATH_COMPLEX: harp_python_dataframe_complex(
                path, include_timestamp=False
            ),
        ),
        BenchmarkCase(
            name="harp_python_ts_complex",
            label="harp-python  read() + timestamp - complex (raw U8)",
            baseline_name=None,
            run=lambda path=DUMP_PATH_COMPLEX: harp_python_dataframe_complex(
                path, include_timestamp=True
            ),
        ),
        BenchmarkCase(
            name="harp_data_no_ts_no_copy_complex",
            label="harp.data    load + DataFrame without timestamp (no copy) - complex",
            baseline_name="harp_python_no_ts_complex",
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
            baseline_name="harp_python_no_ts_complex",
            run=lambda path=DUMP_PATH_COMPLEX: harp_data_dataframe(
                path,
                ComplexConfiguration,
                PayloadType.TIMESTAMPED_U8,
                include_timestamp=False,
                copy=True,
            ),
        ),
        BenchmarkCase(
            name="harp_data_ts_no_copy_complex",
            label="harp.data    load + DataFrame + timestamp (no copy) - complex",
            baseline_name="harp_python_ts_complex",
            run=lambda path=DUMP_PATH_COMPLEX: harp_data_dataframe(
                path,
                ComplexConfiguration,
                PayloadType.TIMESTAMPED_U8,
                include_timestamp=True,
                copy=False,
            ),
        ),
        BenchmarkCase(
            name="harp_data_ts_copy_complex",
            label="harp.data    load + DataFrame + timestamp (copy) - complex",
            baseline_name="harp_python_ts_complex",
            run=lambda path=DUMP_PATH_COMPLEX: harp_data_dataframe(
                path,
                ComplexConfiguration,
                PayloadType.TIMESTAMPED_U8,
                include_timestamp=True,
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
