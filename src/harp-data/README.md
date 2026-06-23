# harp-data

[![PyPI version](https://badge.fury.io/py/harp-data.svg)](https://badge.fury.io/py/harp-data)

A Python library for handling data related to Harp devices, including data parsing, formatting, and storage.

## Loading Register Dump Files

The `harp-data` package provides a generic NumPy-based loader for `.bin` dump files of a specific register.

Dump files are assumed to contain timestamped Harp messages by default. If needed, non-timestamped messages can still be loaded by setting `timestamped=False`.

### Load a dump file

```python
from harp.data import load_register_dump
from harp.protocol.registers import AnalogData

dump = load_register_dump("analog_data.bin", AnalogData)

print(len(dump))
print(dump.field_names)
print(dump.payload.shape)
print(dump.timestamp_s)
```

The returned object exposes:

- `records`: the raw structured NumPy memmap
- `payload`: the register payload as a NumPy array
- `field_names`: payload field names when available
- `timestamp_s`: timestamps in seconds, or None for non-timestamped dumps

### Create a pandas DataFrame

```python
import pandas as pd

from harp.data import load_register_dump
from harp.protocol.registers import AnalogData

dump = load_register_dump("analog_data.bin", AnalogData)

df = pd.DataFrame(dump.columns())
print(df.head())
```

### Create a Polar DataFrame

```python
import polars as pl

from harp.data import load_register_dump
from harp.protocol.registers import AnalogData

dump = load_register_dump("analog_data.bin", AnalogData)

df = pl.DataFrame(dump.columns())
print(df.head())
```

### Load a non-timestamped dump file

```python
from harp.data import ValidationMode, load_register_dump
from harp.protocol.registers import AnalogData

dump = load_register_dump(
    "analog_data_legacy.bin",
    AnalogData,
    timestamped=False,
    validation=ValidationMode.ALL,
)
print(len(dump))
print(dump.field_names)
print(dump.payload.shape)
```

### Fast header-only validation

```python
from harp.data import ValidationMode, load_register_dump
from harp.protocol.registers import AnalogData

dump = load_register_dump(
    "analog_data.bin",
    AnalogData,
    validation=ValidationMode.HEADER,
)
print(len(dump))
print(dump.field_names)
print(dump.payload.shape)
```
