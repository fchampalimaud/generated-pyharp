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

## Current results

On Windows 11, Python 3.14.2, running on a Intel i7-12700H CPU @ 2.30GHz:

```bash
=== AnalogData benchmark (timeit) ===
  File  : behavior_44.bin  (123.6 MiB)
  Frames: 7,198,751  |  stride=18 bytes

Sanity check:
  Sanity check passed: 7,198,751 rows, payload columns and timestamps match across all implementations.

Benchmark (20 repeats):
  harp-python  read() + timestamp                     min=0.131806s  mean=0.136367s  max=0.144516s  stdev=0.003573s  (n=20, loops=4)
  harp-python  read() without timestamp               min=0.119500s  mean=0.122200s  max=0.125672s  stdev=0.001913s  (n=20, loops=4)
  harp.data    load + DataFrame + timestamp (no copy) min=0.094385s  mean=0.096316s  max=0.099935s  stdev=0.001378s  (n=20, loops=10)
  harp.data    load + DataFrame + timestamp (copy)    min=0.120710s  mean=0.123593s  max=0.127209s  stdev=0.001799s  (n=20, loops=4)
  harp.data    load + DataFrame without timestamp (no copy)min=0.000346s  mean=0.000367s  max=0.000390s  stdev=0.000012s  (n=20, loops=2000)
  harp.data    load + DataFrame without timestamp (copy)min=0.069380s  mean=0.071791s  max=0.074032s  stdev=0.001576s  (n=20, loops=10)

Ratios vs harp-python baseline:
  harp.data    load + DataFrame + timestamp (no copy) min=0.72x  mean=0.71x  (faster by 29% on mean)
  harp.data    load + DataFrame + timestamp (copy)    min=0.92x  mean=0.91x  (faster by 9% on mean)
  harp.data    load + DataFrame without timestamp (no copy)min=0.00x  mean=0.00x  (faster by 100% on mean)
  harp.data    load + DataFrame without timestamp (copy)min=0.58x  mean=0.59x  (faster by 41% on mean)
```

On Windows 11, WSL2 (repo + data on WSL side), Python 3.14.2, running on a Intel i7-12700H CPU @ 2.30GHz:

```bash
❯ uv run scripts/benchmark_timeit.py

=== AnalogData benchmark (timeit) ===
  File  : behavior_44.bin  (123.6 MiB)
  Frames: 7,198,751  |  stride=18 bytes

Sanity check:
  Sanity check passed: 7,198,751 rows, payload columns and timestamps match across all implementations.

Benchmark (20 repeats):
  harp-python  read() + timestamp                     min=0.088860s  mean=0.093142s  max=0.103037s  stdev=0.003950s  (n=20, loops=10)
  harp-python  read() without timestamp               min=0.082666s  mean=0.085505s  max=0.090446s  stdev=0.002152s  (n=20, loops=10)
  harp.data    load + DataFrame + timestamp (no copy) min=0.039636s  mean=0.041556s  max=0.044959s  stdev=0.001613s  (n=20, loops=20)
  harp.data    load + DataFrame + timestamp (copy)    min=0.061788s  mean=0.064478s  max=0.067853s  stdev=0.001641s  (n=20, loops=10)
  harp.data    load + DataFrame without timestamp (no copy)min=0.000100s  mean=0.000104s  max=0.000112s  stdev=0.000004s  (n=20, loops=8000)
  harp.data    load + DataFrame without timestamp (copy)min=0.024169s  mean=0.024674s  max=0.025157s  stdev=0.000299s  (n=20, loops=40)

Ratios vs harp-python baseline:
  harp.data    load + DataFrame + timestamp (no copy) min=0.45x  mean=0.45x  (faster by 55% on mean)
  harp.data    load + DataFrame + timestamp (copy)    min=0.70x  mean=0.69x  (faster by 31% on mean)
  harp.data    load + DataFrame without timestamp (no copy)min=0.00x  mean=0.00x  (faster by 100% on mean)
  harp.data    load + DataFrame without timestamp (copy)min=0.29x  mean=0.29x  (faster by 71% on mean)
```

On Ubuntu 24.04, Python 3.14.12, running on a Intel i5-10400F CPU:

```bash
=== AnalogData benchmark (timeit) ===
  File  : behavior_44.bin  (123.6 MiB)
  Frames: 7,198,751  |  stride=18 bytes

Sanity check:
  Sanity check passed: 7,198,751 rows, payload columns and timestamps match across all implementations.

Benchmark (20 repeats):
  harp-python  read() + timestamp                     min=0.101571s  mean=0.105609s  max=0.114565s  stdev=0.003887s  (n=20, loops=8)
  harp-python  read() without timestamp               min=0.091759s  mean=0.093261s  max=0.096031s  stdev=0.001355s  (n=20, loops=10)
  harp.data    load + DataFrame + timestamp (no copy) min=0.053172s  mean=0.054543s  max=0.057306s  stdev=0.001105s  (n=20, loops=10)
  harp.data    load + DataFrame + timestamp (copy)    min=0.080585s  mean=0.082260s  max=0.085017s  stdev=0.001438s  (n=20, loops=10)
  harp.data    load + DataFrame without timestamp (no copy)min=0.000189s  mean=0.000192s  max=0.000195s  stdev=0.000002s  (n=20, loops=4000)
  harp.data    load + DataFrame without timestamp (copy)min=0.033110s  mean=0.033994s  max=0.035620s  stdev=0.000826s  (n=20, loops=20)

Ratios vs harp-python baseline:
  harp.data    load + DataFrame + timestamp (no copy) min=0.52x  mean=0.52x  (faster by 48% on mean)
  harp.data    load + DataFrame + timestamp (copy)    min=0.79x  mean=0.78x  (faster by 22% on mean)
  harp.data    load + DataFrame without timestamp (no copy)min=0.00x  mean=0.00x  (faster by 100% on mean)
  harp.data    load + DataFrame without timestamp (copy)min=0.36x  mean=0.36x  (faster by 64% on mean)
```
