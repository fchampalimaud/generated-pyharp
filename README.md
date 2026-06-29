# pyharp

This project includes three main packages:

- **harp-protocol**: Provides the core protocol definitions and utilities for the Harp protocol.
   See [Protocol API Documentation](https://fchampalimaud.github.io/pyharp/api/protocol) for details.

- **harp-serial**: Implements serial communication functionalities for generic Harp devices.
   See [Serial API Documentation](https://fchampalimaud.github.io/pyharp/api/serial) for more information.
  
- **harp-data**: Provides data handling and processing utilities for Harp devices.
   See [Data API Documentation](https://fchampalimaud.github.io/pyharp/api/data) for details.

For specific Harp devices' packages please select the corresponding Harp device under the Devices section on the menu.

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

```bash
=== harp.data benchmark (timeit) ===
  File  : behavior_44.bin  (123.6 MiB)
  Frames: 7,198,751  |  stride=18 bytes

  File  : complex_config_34.bin  (100.5 MiB)
  Frames: 1,700,000  |  stride=62 bytes

Sanity check:
  Sanity check passed: 7,198,751 rows, payload columns and timestamps match.

Benchmark (20 repeats):
  harp-python  read() + timestamp                     min=0.131731s  mean=0.133631s  max=0.136590s  stdev=0.001537s  (n=20, loops=4)
  harp-python  read() without timestamp               min=0.120633s  mean=0.122861s  max=0.124794s  stdev=0.001183s  (n=20, loops=8)
  harp.data    load + DataFrame + timestamp (no copy) min=0.083849s  mean=0.085447s  max=0.088346s  stdev=0.001298s  (n=20, loops=10)
  harp.data    load + DataFrame + timestamp (copy)    min=0.109528s  mean=0.111659s  max=0.116807s  stdev=0.001781s  (n=20, loops=8)
  harp.data    load + DataFrame without timestamp (no copy)min=0.044665s  mean=0.045887s  max=0.047312s  stdev=0.000742s  (n=20, loops=20)
  harp.data    load + DataFrame without timestamp (copy)min=0.070778s  mean=0.072063s  max=0.076010s  stdev=0.001235s  (n=20, loops=10)
  harp.data    load + DataFrame without timestamp (no copy) - complexmin=0.053969s  mean=0.055900s  max=0.061715s  stdev=0.001575s  (n=20, loops=10)
  harp.data    load + DataFrame without timestamp (copy) - complexmin=0.069307s  mean=0.071235s  max=0.073789s  stdev=0.001096s  (n=20, loops=10)

Ratios vs harp-python baseline:
  harp.data    load + DataFrame + timestamp (no copy) min=0.64x  mean=0.64x  (faster by 36% on mean)
  harp.data    load + DataFrame + timestamp (copy)    min=0.83x  mean=0.84x  (faster by 16% on mean)
  harp.data    load + DataFrame without timestamp (no copy)min=0.37x  mean=0.37x  (faster by 63% on mean)
  harp.data    load + DataFrame without timestamp (copy)min=0.59x  mean=0.59x  (faster by 41% on mean)
```

### Profiling

The `scripts/profile_complex.py` script compares homogeneous (AnalogData) and structured (ComplexConfiguration) payloads:

```bash
uv run scripts/profile_complex.py
```

```bash
=== AnalogData (homogeneous) ===
  load_register_dump: 39.39 ms  (7198751 entries)
  payload_columns:    0.02 ms  (3 columns)
  DataFrame(copy=False):  0.36 ms  dtypes=[dtype('int16'), dtype('int16'), dtype('int16')]
  DataFrame(copy=True):   23.45 ms
  TOTAL (copy=False): 39.77 ms
  TOTAL (copy=True):  62.85 ms

=== ComplexConfig (struct) ===
  load_register_dump: 32.95 ms  (1700000 entries)
  payload_columns:    18.39 ms  (6 columns)
  DataFrame(copy=False):  0.26 ms
  DataFrame(copy=True):   14.22 ms
  TOTAL (copy=False): 51.59 ms
  TOTAL (copy=True):  65.55 ms

=== Comparison (per-entry) ===
  --- copy=False ---
  AnalogData:     0.006 us/entry  (7,198,751 entries)
  ComplexConfig:  0.030 us/entry  (1,700,000 entries)
  Slowdown:       5.5x per entry
  ComplexConfig @ 7,198,751 entries (estimate): 218 ms
  --- copy=True ---
  AnalogData:     0.009 us/entry  (7,198,751 entries)
  ComplexConfig:  0.039 us/entry  (1,700,000 entries)
  Slowdown:       4.4x per entry
  ComplexConfig @ 7,198,751 entries (estimate): 278 ms
```

Structured payload extraction uses threaded chunk extraction. The `copy=True` default uses numpy-level copies which are significantly faster than letting pandas copy from what we tested.

## Complex registers

A first attempt to support complex registers with heterogeneous payloads is available in the `harp-data` package. The `payload_struct` attribute of the `RegisterSpec` class allows defining a structured payload for registers that contain multiple fields of different types.

> [!WARNING]
> There are clearly places where we can remove duplication (i.e., most likely it will be possible to define the `encode` and `decode` methods in the `RegisterSpec` class automatically.
>
> I believe that we can further improve it by also handling the homogeneous payloads using the same `StructField` defined here.

We used the `ComplexConfiguration` register example on the information on <https://github.com/harp-tech/generators/pull/87> and added a string payload member to it. We tried to follow the definition available in <https://github.com/harp-tech/protocol/pull/215/>.

> [!NOTE]
> We didn't test it yet with arrays on payload members.

To test it, we created a dump file generator script that creates a dump file with the `ComplexConfiguration` register and some frames. The script is available in the `scripts` folder as `generate_dump.py`. You can run it to generate a dump file for testing.

Please check the script for more details on the arguments and usage. The default output file is `complex_config_34.bin` in the `scripts/data` folder, with a size of ~100MB, with 1.7 million messages. Timestamps are generated roughly to 1Khz frequency.
