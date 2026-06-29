from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field, fields, is_dataclass
from enum import StrEnum
from os import PathLike
from pathlib import Path
from typing import Literal, TypeVar

import numpy as np
from harp.protocol import PayloadType
from harp.protocol.registers import IRegister, RegisterSpec, StructField
from harp.protocol.utils import PayloadTypeFlag

T = TypeVar("T")

TIMESTAMP_TICK_SECONDS = 32e-6
TIMESTAMP_TICK_NS = 32_000

TimestampMode = Literal["parts", "float", "ns", "timedelta64[ns]"]


class ValidationMode(StrEnum):
    HEADER = "header"
    ALL = "all"
    CHECKSUM = "checksum"


@dataclass(frozen=True)
class TimestampView:
    seconds: np.ndarray
    ticks: np.ndarray

    def __len__(self) -> int:
        return len(self.seconds)

    def as_ns(self, out: np.ndarray | None = None) -> np.ndarray:
        if out is None:
            out = np.empty(self.seconds.shape, dtype=np.int64)
        elif out.dtype != np.int64 or out.shape != self.seconds.shape:
            raise ValueError(
                "Output array for nanosecond timestamps must match shape and use int64 dtype."
            )

        np.multiply(self.seconds, 1_000_000_000, out=out, dtype=np.int64)
        np.add(out, np.multiply(self.ticks, TIMESTAMP_TICK_NS, dtype=np.int64), out=out)
        return out

    def as_timedelta64_ns(self, out: np.ndarray | None = None) -> np.ndarray:
        return self.as_ns(out=out).view("timedelta64[ns]")

    def as_float_seconds(self, out: np.ndarray | None = None) -> np.ndarray:
        if out is None:
            out = self.seconds.astype(np.float64)
        elif out.dtype != np.float64 or out.shape != self.seconds.shape:
            raise ValueError(
                "Output array for float-second timestamps must match shape and use float64 dtype."
            )
        else:
            np.copyto(out, self.seconds, casting="unsafe")

        np.add(
            out,
            np.multiply(self.ticks, TIMESTAMP_TICK_SECONDS, dtype=np.float64),
            out=out,
        )
        return out


_MIN_BYTES_FOR_THREADING = 1_000_000


def _extract_chunk_range(
    raw: np.ndarray,
    field_specs: list[tuple[int, int, np.ndarray]],
    chunk_entries: int,
    range_start: int,
    range_end: int,
) -> None:
    for start in range(range_start, range_end, chunk_entries):
        end = min(start + chunk_entries, range_end)
        chunk = raw[start:end]
        for col_start, byte_size, out_bytes in field_specs:
            out_bytes[start:end] = chunk[:, col_start : col_start + byte_size]


def _threaded_extract(
    raw: np.ndarray,
    field_specs: list[tuple[int, int, np.ndarray]],
    chunk_entries: int,
    n: int,
) -> None:
    total_bytes = raw.shape[0] * raw.shape[1]
    num_workers = min(4, os.cpu_count() or 1)

    if num_workers <= 1 or total_bytes < _MIN_BYTES_FOR_THREADING:
        _extract_chunk_range(raw, field_specs, chunk_entries, 0, n)
        return

    per_worker = ((n + num_workers - 1) // num_workers // chunk_entries + 1) * chunk_entries
    with ThreadPoolExecutor(max_workers=num_workers) as pool:
        futures = []
        for w in range(num_workers):
            ws = w * per_worker
            we = min(ws + per_worker, n)
            if ws >= n:
                break
            futures.append(
                pool.submit(_extract_chunk_range, raw, field_specs, chunk_entries, ws, we)
            )
        for f in futures:
            f.result()


@dataclass(frozen=True)
class RegisterDump:
    records: np.ndarray
    payload_matrix: np.ndarray
    field_names: tuple[str, ...]
    timestamp: TimestampView | None
    _column_cache: dict[str, np.ndarray] = field(default_factory=dict, repr=False)
    _raw_2d: np.ndarray | None = field(default=None, repr=False)

    def __len__(self) -> int:
        return len(self.records)

    @property
    def width(self) -> int:
        if self.payload_matrix.dtype.names is not None:
            return len(self.payload_matrix.dtype.names)
        return self.payload_matrix.shape[1]

    def column_names(self, *, prefix: str = "value") -> tuple[str, ...]:
        if self.field_names:
            if len(self.field_names) != self.width:
                raise ValueError(
                    f"Field count {len(self.field_names)} does not match "
                    f"payload width {self.width}."
                )
            return self.field_names

        if self.payload_matrix.dtype.names is not None:
            return self.payload_matrix.dtype.names

        if self.width == 1:
            return ("value",)

        return tuple(f"{prefix}_{index}" for index in range(self.width))

    def column(self, key: int | str) -> np.ndarray:
        if self.payload_matrix.dtype.names is not None:
            if isinstance(key, int):
                names = self.column_names()
                if key < 0 or key >= len(names):
                    raise IndexError(
                        f"Payload column index {key} is out of bounds "
                        f"for width {len(names)}."
                    )
                key = names[key]
            if key not in self._column_cache:
                self._column_cache[key] = np.ascontiguousarray(
                    self.payload_matrix[key]
                )
            return self._column_cache[key]

        # 2D uniform array - homogeneous payload
        if isinstance(key, str):
            names = self.column_names()
            try:
                index = names.index(key)
            except ValueError as exc:
                raise KeyError(f"Unknown payload column {key!r}.") from exc
        else:
            index = key

        if index < 0 or index >= self.width:
            raise IndexError(
                f"Payload column index {index} is out of bounds for width {self.width}."
            )

        return self.payload_matrix[:, index]

    def payload_columns(self, *, prefix: str = "value") -> dict[str, np.ndarray]:
        names = self.column_names(prefix=prefix)
        if self.payload_matrix.dtype.names is not None and not self._column_cache:
            self._bulk_extract_columns()
        return {name: self.column(name) for name in names}

    def _bulk_extract_columns(self) -> None:
        n = len(self.records)
        if n == 0:
            return
        frame_size = self.records.dtype.itemsize
        payload_offset = self.records.dtype.fields["payload"][1]
        payload_dtype = self.payload_matrix.dtype
        if self._raw_2d is not None:
            raw = self._raw_2d
        else:
            raw = self.records.view(np.uint8).reshape(n, frame_size)

        field_specs: list[tuple[int, int, np.ndarray]] = []
        for name in payload_dtype.names:
            dt, offset = payload_dtype.fields[name][:2]
            col_start = payload_offset + offset
            byte_size = dt.itemsize
            arr = np.empty(n, dtype=dt)
            out_bytes = arr.view(np.uint8).reshape(n, byte_size)
            self._column_cache[name] = arr
            field_specs.append((col_start, byte_size, out_bytes))

        chunk_entries = max(1, (8 * 1024 * 1024) // frame_size)
        _threaded_extract(raw, field_specs, chunk_entries, n)

    def timestamp_values(
        self,
        mode: Literal["float", "ns", "timedelta64[ns]"] = "ns",
    ) -> np.ndarray:
        if self.timestamp is None:
            raise ValueError("Dump does not contain timestamp data.")

        if mode == "float":
            return self.timestamp.as_float_seconds()
        if mode == "ns":
            return self.timestamp.as_ns()
        if mode == "timedelta64[ns]":
            return self.timestamp.as_timedelta64_ns()

        raise ValueError(f"Unsupported timestamp mode {mode!r}.")

    def columns(
        self,
        *,
        include_timestamp: bool = False,
        timestamp: TimestampMode = "parts",
        prefix: str = "value",
    ) -> dict[str, np.ndarray]:
        columns = self.payload_columns(prefix=prefix)

        if not include_timestamp:
            return columns

        if self.timestamp is None:
            raise ValueError("Dump does not contain timestamp data.")

        if timestamp == "parts":
            return {
                "timestamp_seconds": self.timestamp.seconds,
                "timestamp_ticks": self.timestamp.ticks,
                **columns,
            }
        if timestamp == "float":
            return {
                "timestamp": self.timestamp.as_float_seconds(),
                **columns,
            }
        if timestamp == "ns":
            return {
                "timestamp": self.timestamp.as_ns(),
                **columns,
            }
        if timestamp == "timedelta64[ns]":
            return {
                "timestamp": self.timestamp.as_timedelta64_ns(),
                **columns,
            }

        raise ValueError(
            f"Unsupported timestamp mode {timestamp!r}. "
            "Expected one of: 'parts', 'float', 'ns', 'timedelta64[ns]'."
        )


def _struct_field_format(struct_field: StructField):
    if struct_field.is_string:
        return f"S{struct_field.byte_size}"
    scalar = numpy_scalar_dtype(struct_field.type)
    element_count = struct_field.byte_size // struct_field.type.type_size()
    if element_count > 1:
        return (scalar, (element_count,))
    return scalar


def _build_struct_dtype(spec: RegisterSpec, payload_type: PayloadType) -> np.dtype:
    payload_byte_size = spec.count * numpy_scalar_dtype(payload_type).itemsize
    return np.dtype(
        {
            "names": [f.name for f in spec.payload_struct],
            "formats": [_struct_field_format(f) for f in spec.payload_struct],
            "offsets": [f.offset for f in spec.payload_struct],
            "itemsize": payload_byte_size,
        }
    )



def register_spec(register_cls: type[IRegister[T]]) -> RegisterSpec[T]:
    return register_cls.spec


def register_field_names(register_cls: type[IRegister[T]]) -> tuple[str, ...]:
    spec = register_spec(register_cls)

    # payload_struct supersedes fields
    if spec.payload_struct is not None:
        return tuple(f.name for f in spec.payload_struct)

    if spec.fields is not None:
        if len(spec.fields) != spec.count:
            raise ValueError(
                f"{register_cls.__name__}: field count {len(spec.fields)} "
                f"does not match payload count {spec.count}."
            )
        return spec.fields

    dtype = getattr(register_cls, "dtype", None)
    if dtype is not None and is_dataclass(dtype):
        names = tuple(field.name for field in fields(dtype))
        if len(names) != spec.count:
            raise ValueError(
                f"{register_cls.__name__}: field count {len(names)} "
                f"does not match payload count {spec.count}."
            )
        return names

    return ()


def numpy_scalar_dtype(payload_type: PayloadType) -> np.dtype:
    itemsize = int(payload_type.type_size())

    if payload_type.is_float():
        if itemsize != 4:
            raise ValueError(f"Unsupported float payload size: {itemsize}.")
        return np.dtype("<f4")

    if itemsize not in (1, 2, 4, 8):
        raise ValueError(f"Unsupported integer payload size: {itemsize}.")

    kind = "i" if payload_type.is_signed() else "u"
    return np.dtype(f"<{kind}{itemsize}")


def resolve_dump_payload_type(
    register_cls: type[IRegister[T]],
    payload_type: PayloadType | None = None,
    *,
    timestamped: bool = True,
) -> PayloadType:
    if payload_type is not None:
        return payload_type

    raw = int(register_spec(register_cls).payload_type)
    if timestamped:
        raw |= int(PayloadTypeFlag.HAS_TIMESTAMP)
    else:
        raw &= ~int(PayloadTypeFlag.HAS_TIMESTAMP)

    return PayloadType(raw)


def payload_nbytes(
    register_cls: type[IRegister[T]],
    payload_type: PayloadType | None = None,
    *,
    timestamped: bool = True,
) -> int:
    actual_payload_type = resolve_dump_payload_type(
        register_cls,
        payload_type,
        timestamped=timestamped,
    )
    spec = register_spec(register_cls)
    return spec.count * numpy_scalar_dtype(actual_payload_type).itemsize


def frame_length(
    register_cls: type[IRegister[T]],
    payload_type: PayloadType,
) -> int:
    return (
        4
        + (6 if payload_type.has_timestamp() else 0)
        + payload_nbytes(
            register_cls,
            payload_type,
            timestamped=payload_type.has_timestamp(),
        )
    )


def build_frame_dtype(
    register_cls: type[IRegister[T]],
    payload_type: PayloadType,
) -> np.dtype:
    spec = register_spec(register_cls)

    descr: list[tuple] = [
        ("message_type", "u1"),
        ("length", "u1"),
        ("address", "u1"),
        ("port", "u1"),
        ("payload_type", "u1"),
    ]

    if payload_type.has_timestamp():
        descr.extend(
            [
                ("seconds", "<u4"),
                ("ticks", "<u2"),
            ]
        )

    if spec.payload_struct is not None:
        descr.append(("payload", _build_struct_dtype(spec, payload_type)))
    else:
        item_dtype = numpy_scalar_dtype(payload_type)
        descr.append(("payload", item_dtype, (spec.count,)))

    descr.append(("checksum", "u1"))
    return np.dtype(descr)


def coerce_validation_mode(value: ValidationMode | str) -> ValidationMode:
    if isinstance(value, ValidationMode):
        return value

    try:
        return ValidationMode(value)
    except ValueError as exc:
        valid_values = ", ".join(mode.value for mode in ValidationMode)
        raise ValueError(
            f"Unknown validation mode {value!r}. Expected one of: {valid_values}."
        ) from exc


def validate_dump_header(
    path: Path,
    register_cls: type[IRegister[T]],
    payload_type: PayloadType,
) -> int:
    with path.open("rb") as stream:
        header = stream.read(5)

    if len(header) < 5:
        raise ValueError("File is too small to contain a Harp frame header.")

    _, length, address, _, payload_type_raw = header
    spec = register_spec(register_cls)

    if address != spec.address:
        raise ValueError(f"Expected register {spec.address}, found register {address}.")

    if payload_type_raw != int(payload_type):
        try:
            found_payload_type = PayloadType(payload_type_raw).name
        except ValueError:
            found_payload_type = f"0x{payload_type_raw:02x}"

        raise ValueError(
            f"Expected payload type {payload_type.name}, found {found_payload_type}."
        )

    expected_length = frame_length(register_cls, payload_type)
    if length != expected_length:
        raise ValueError(
            f"Unexpected Harp length byte {length}; expected {expected_length}."
        )

    return expected_length


def validate_dump_records(
    records: np.ndarray,
    register_cls: type[IRegister[T]],
    payload_type: PayloadType,
    expected_length: int,
) -> None:
    spec = register_spec(register_cls)

    if not np.all(records["length"] == expected_length):
        raise ValueError("Not all frames have the expected Harp length.")
    if not np.all(records["address"] == spec.address):
        raise ValueError("File contains frames from other registers.")
    if not np.all(records["payload_type"] == int(payload_type)):
        raise ValueError("File contains mixed payload types.")


def validate_checksums(records: np.ndarray, frame_dtype: np.dtype) -> None:
    stride = frame_dtype.itemsize
    frame_view = records.view(np.uint8).reshape(len(records), stride)
    expected = frame_view[:, :-1].sum(axis=1, dtype=np.uint8)
    actual = frame_view[:, -1]
    bad = np.nonzero(expected != actual)[0]
    if len(bad):
        raise ValueError(
            f"Checksum validation failed on {len(bad):,} frame(s). "
            f"First bad frame index: {bad[0]}"
        )


def load_register_dump(
    path: str | PathLike[str],
    register_cls: type[IRegister[T]],
    payload_type: PayloadType | None = None,
    *,
    timestamped: bool = True,
    validation: ValidationMode | str = ValidationMode.ALL,
) -> RegisterDump:
    path = Path(path)
    validation_mode = coerce_validation_mode(validation)

    actual_payload_type = resolve_dump_payload_type(
        register_cls,
        payload_type,
        timestamped=timestamped,
    )
    expected_length = validate_dump_header(path, register_cls, actual_payload_type)
    frame_dtype = build_frame_dtype(register_cls, actual_payload_type)

    file_size = path.stat().st_size
    frame_size = frame_dtype.itemsize
    remainder = file_size % frame_size
    complete_frames = file_size // frame_size

    if remainder:
        import warnings

        warnings.warn(
            f"File size {file_size} is not a multiple of frame size "
            f"{frame_size}; last {remainder} bytes will be ignored "
            f"(truncated frame). Loading {complete_frames:,} complete frames.",
            stacklevel=2,
        )

    field_names = register_field_names(register_cls)
    spec = register_spec(register_cls)

    if complete_frames == 0:
        records = np.empty(0, dtype=frame_dtype)
        if spec.payload_struct is not None:
            empty_payload = np.empty(
                0, dtype=_build_struct_dtype(spec, actual_payload_type)
            )
        else:
            scalar_dtype = numpy_scalar_dtype(actual_payload_type)
            empty_payload = np.empty((0, spec.count), dtype=scalar_dtype)

        return RegisterDump(
            records=records,
            payload_matrix=empty_payload,
            field_names=field_names,
            timestamp=TimestampView(
                seconds=np.empty(0, dtype="<u4"),
                ticks=np.empty(0, dtype="<u2"),
            )
            if actual_payload_type.has_timestamp()
            else None,
        )

    raw_flat = np.fromfile(path, dtype=np.uint8, count=complete_frames * frame_size)
    records = raw_flat.view(frame_dtype)
    raw_2d = raw_flat.reshape(complete_frames, frame_size) if spec.payload_struct is not None else None

    if validation_mode is ValidationMode.ALL:
        validate_dump_records(
            records,
            register_cls,
            actual_payload_type,
            expected_length,
        )
    elif validation_mode is ValidationMode.CHECKSUM:
        validate_dump_records(
            records,
            register_cls,
            actual_payload_type,
            expected_length,
        )
        validate_checksums(records, frame_dtype)

    payload_matrix = records["payload"]
    if payload_matrix.ndim == 1 and spec.payload_struct is None:
        payload_matrix = payload_matrix.reshape(len(records), 1)

    timestamp = None
    if actual_payload_type.has_timestamp():
        timestamp = TimestampView(
            seconds=records["seconds"],
            ticks=records["ticks"],
        )

    return RegisterDump(
        records=records,
        payload_matrix=payload_matrix,
        field_names=field_names,
        timestamp=timestamp,
        _raw_2d=raw_2d,
    )


__all__ = [
    "RegisterDump",
    "TimestampView",
    "ValidationMode",
    "load_register_dump",
]
