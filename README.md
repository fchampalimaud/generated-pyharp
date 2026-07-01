# pyharp

This project includes three main packages:

- **harp-protocol**: Provides the core protocol definitions and utilities for the Harp protocol.
   See [Protocol API Documentation](https://fchampalimaud.github.io/pyharp/api/protocol) for details.

- **harp-serial**: Implements serial communication functionalities for generic Harp devices.
   See [Serial API Documentation](https://fchampalimaud.github.io/pyharp/api/serial) for more information.
  
- **harp-data**: Provides data handling and processing utilities for Harp devices.
   See [Data API Documentation](https://fchampalimaud.github.io/pyharp/api/data) for details.

For specific Harp devices' packages please select the corresponding Harp device under the Devices section on the menu.

## Changes since last update

### Register unification

- Merged `IRegister` and `RegisterSpec` into a single `RegisterBase` class with automatic `encode`/`decode` derivation from the type parameter (supports `StructPayload`, `MaskPayload`, `IntEnum`, `IntFlag`, scalar `int`/`float`, and raw `bytes`).
- Added `MaskField` and `MaskPayload` base classes for bitmask registers (e.g. `OperationControl`).
- Added bitmask support to `StructPayload` via `mask` and `mask_type` parameters on `payload_field`.
- `StructPayload` fields are now defined inline using `payload_field()` descriptors, which are collected and converted to `StructField` tuples at class creation time.

### Performance improvements (harp-protocol)

- Cached `struct.Struct` objects on `StructPayload.__init_subclass__` per field. `HarpMessage._get_raw_payload` and `_get_payload` use a struct cache to prevent format string construction on every call.
- Removed unnecessary copies and allocations in `from_payload` for Checksum and Timestamp.
- Supported types are cached as a `frozenset` to prevent computations on every call.

### Benchmarking & testing

- Added per-message encode/decode microbenchmark (`scripts/benchmark_message.py`) comparing register framework overhead vs raw `struct.pack`/`unpack`.
- Added per-operation profilers (`scripts/profile_message.py`, `scripts/profile_message_complex.py`) for showing hot paths of `format()`/`parse()` calls.
- Added tests for bitmasks, `IntEnum`/`float` auto-derivation, group masks, and kitchen-sink structs.

## Benchmarking

The `scripts/benchmark_timeit.py` file contains the current benchmark using a Behavior Analog data dump file. *For simplicity, the AnalogData register and its payload are defined locally*.

The current `pyproject.toml` already includes `pandas` as a dependency, which is only used in the benchmark script.

> [!WARNING]
> The data dump file is not included in the repository. You will need to provide your own data file for benchmarking.
> The script expects the binary dump file to be located in `scripts/data` folder, with the name `behavior_44.bin`. You can change the path in the script if your file is located elsewhere.

We have been using a ~123MB Behavior AnalogData dump file from a ~2h session for our benchmarks.

The current benchmark script can be run using the following command:

```bash
uv run scripts/benchmark_timeit.py
```

### Current results

On Windows 11, Python 3.14.2, running on a Intel i7-12700H CPU @ 2.30GHz:

```text
=== harp.data benchmark (timeit) ===
  File  : behavior_44.bin  (123.6 MiB)
  Frames: 7,198,751  |  stride=18 bytes

  File  : complex_config_34.bin  (100.5 MiB)
  Frames: 1,700,000  |  stride=62 bytes

Benchmark (20 repeats):
  harp-python  read() + timestamp                     min=0.131929s  mean=0.136200s  max=0.142334s  stdev=0.002566s  (n=20, loops=4)
  harp-python  read() without timestamp               min=0.121127s  mean=0.123361s  max=0.125579s  stdev=0.001043s  (n=20, loops=8)
  harp.data    load + DataFrame + timestamp (no copy) min=0.084385s  mean=0.085693s  max=0.087964s  stdev=0.000958s  (n=20, loops=10)
  harp.data    load + DataFrame + timestamp (copy)    min=0.109831s  mean=0.111706s  max=0.116582s  stdev=0.001604s  (n=20, loops=8)
  harp.data    load + DataFrame without timestamp (no copy)min=0.043945s  mean=0.045242s  max=0.048271s  stdev=0.001120s  (n=20, loops=10)
  harp.data    load + DataFrame without timestamp (copy)min=0.069768s  mean=0.071532s  max=0.075868s  stdev=0.001396s  (n=20, loops=10)
  harp-python  read() without timestamp - complex (raw U8)min=0.256345s  mean=0.262019s  max=0.271932s  stdev=0.004011s  (n=20, loops=2)
  harp-python  read() + timestamp - complex (raw U8)  min=0.260763s  mean=0.267445s  max=0.286380s  stdev=0.007207s  (n=20, loops=2)
  harp.data    load + DataFrame without timestamp (no copy) - complexmin=0.053623s  mean=0.055718s  max=0.060170s  stdev=0.001721s  (n=20, loops=10)
  harp.data    load + DataFrame without timestamp (copy) - complexmin=0.069732s  mean=0.071470s  max=0.077100s  stdev=0.001900s  (n=20, loops=10)
  harp.data    load + DataFrame + timestamp (no copy) - complexmin=0.069933s  mean=0.072467s  max=0.076497s  stdev=0.001594s  (n=20, loops=10)
  harp.data    load + DataFrame + timestamp (copy) - complexmin=0.085812s  mean=0.087738s  max=0.092643s  stdev=0.001614s  (n=20, loops=10)

Ratios vs harp-python baseline:
  harp.data    load + DataFrame + timestamp (no copy) min=0.64x  mean=0.63x  (faster by 37% on mean)
  harp.data    load + DataFrame + timestamp (copy)    min=0.83x  mean=0.82x  (faster by 18% on mean)
  harp.data    load + DataFrame without timestamp (no copy)min=0.36x  mean=0.37x  (faster by 63% on mean)
  harp.data    load + DataFrame without timestamp (copy)min=0.58x  mean=0.58x  (faster by 42% on mean)
  harp.data    load + DataFrame without timestamp (no copy) - complexmin=0.21x  mean=0.21x  (faster by 79% on mean)
  harp.data    load + DataFrame without timestamp (copy) - complexmin=0.27x  mean=0.27x  (faster by 73% on mean)
  harp.data    load + DataFrame + timestamp (no copy) - complexmin=0.27x  mean=0.27x  (faster by 73% on mean)
  harp.data    load + DataFrame + timestamp (copy) - complexmin=0.33x  mean=0.33x  (faster by 67% on mean)
```

### Per-message encode/decode

The `scripts/benchmark_message.py` measures `format()` and `parse()` for each register pattern, reporting times per operation in microseconds, with raw `struct.pack`/`unpack` baselines for comparison:

```bash
uv run python scripts/benchmark_message.py
```

```text
Pattern                                        encode     decode  roundtrip raw_struct overhead
-----------------------------------------------------------------------------------------------
  Scalar int (WhoAmI U16)                       1.72      0.09      1.81
  IntFlag (ResetDevice U8)                      1.73      0.29      2.02
  MaskPayload (OperationControl)                2.59      2.02      4.60
  StructPayload homog (AnalogData S16x3)        2.44      0.78      3.22       0.15    21.6x
  StructPayload hetero (ComplexConfig)          3.81      1.65      5.46       1.10     4.9x
  Masked struct (StartPulseTrain U16x2)         3.02      1.57      4.59       0.20    22.7x
  Raw bytes (DeviceName U8x25)                  1.97      0.09      2.06

All times in microseconds (min-of-repeats, lower is better).
raw_struct = bare struct.pack/unpack without register framework or message framing.
overhead   = roundtrip / raw_struct.
```

Per-operation profilers are also available:

```bash
uv run python scripts/profile_message.py          # AnalogData (homogeneous S16x3)
uv run python scripts/profile_message_complex.py   # ComplexConfig (heterogeneous struct)
```

### Bulk data profiling

The `scripts/profile_complex.py` script compares homogeneous (AnalogData) and structured (ComplexConfiguration) payloads:

```bash
uv run python scripts/profile_complex.py
```

Results on Windows 11, Python 3.14.2, running on a Intel i7-12700H CPU @ 2.30GHz:

```text
=== AnalogData (homogeneous) ===
  load_register_dump: 40.03 ms  (7198751 entries)
  payload_columns:    0.03 ms  (3 columns)
  DataFrame(copy=False):  0.49 ms  dtypes=[dtype('int16'), dtype('int16'), dtype('int16')]
  DataFrame(copy=True):   24.85 ms
  TOTAL (copy=False): 40.55 ms
  TOTAL (copy=True):  64.91 ms

=== ComplexConfig (struct) ===
  load_register_dump: 34.20 ms  (1700000 entries)
  payload_columns:    16.43 ms  (6 columns)
  DataFrame(copy=False):  0.43 ms  dtypes=[dtype('uint8'), dtype('float32'), dtype('float32'), dtype('uint8'), dtype('uint32'), dtype('S33')]
  DataFrame(copy=True):   14.58 ms
  TOTAL (copy=False): 51.06 ms
  TOTAL (copy=True):  65.21 ms

=== Comparison (per-entry) ===
  --- copy=False ---
  AnalogData:     0.006 µs/entry  (7,198,751 entries)
  ComplexConfig:  0.030 µs/entry  (1,700,000 entries)
  Slowdown:       5.3x per entry
  ComplexConfig @ 7,198,751 entries (estimate): 216 ms
  --- copy=True ---
  AnalogData:     0.009 µs/entry  (7,198,751 entries)
  ComplexConfig:  0.038 µs/entry  (1,700,000 entries)
  Slowdown:       4.3x per entry
  ComplexConfig @ 7,198,751 entries (estimate): 276 ms
```

Structured payload extraction uses threaded chunk extraction. The `copy=True` default uses numpy-level copies which are significantly faster than letting pandas copy from what we tested.

## Complex registers

Complex registers with heterogeneous payloads are supported via the `StructPayload` base class. Fields are defined using `payload_field()` descriptors with explicit `PayloadType`, `offset`, and optional `length`, `mask`, and `is_string` parameters. `RegisterBase` automatically derives `encode`/`decode` from the type parameter.

We used the `ComplexConfiguration` register example on the information on <https://github.com/harp-tech/generators/pull/87> and added a string payload member to it. We tried to follow the definition available in <https://github.com/harp-tech/protocol/pull/215/>.

> [!NOTE]
> We didn't test it yet with arrays on payload members.

To test it, we created a dump file generator script that creates a dump file with the `ComplexConfiguration` register and some frames. The script is available in the `scripts` folder as `generate_dump.py`. You can run it to generate a dump file for testing.

Please check the script for more details on the arguments and usage. The default output file is `complex_config_34.bin` in the `scripts/data` folder, with a size of ~100MB, with 1.7 million messages. Timestamps are generated roughly to 1Khz frequency.
