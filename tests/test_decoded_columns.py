from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np
import pytest
from harp.data import ValidationMode, load_register_dump
from harp.protocol import HarpMessage, MessageType

from harp.benchmarks._registers import BENCHMARK_REGISTERS
from harp.benchmarks.generate import _resolve_payload_type, generate_one
from harp.benchmarks.register_models import (
    AnalogData,
    AnalogDataPayload,
    BitmaskSplitter,
    BitmaskSplitterPayload,
    ComplexConfiguration,
    ComplexConfigurationPayload,
    Counter0,
    CustomMemberConverter,
    CustomMemberConverterPayload,
    CustomPayload,
    CustomRawPayload,
    DigitalInputs,
    EncoderMode,
    EncoderModeMask,
    HarpVersion,
    PortDIOSet,
    PortDigitalIOS,
    PulseDO0,
    PulseDOPort0,
    PwmPort,
    StartPulse,
    StartPulsePayload,
    StartPulseTrain,
    StartPulseTrainPayload,
    Version,
    VersionPayload,
)


N_ENTRIES = 50


@pytest.fixture(scope="module")
def corpus_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


def _generate_and_load(reg, corpus_dir):
    from harp.benchmarks._registers import BenchmarkedRegister

    path = corpus_dir / f"{reg.name}_{reg.register.address}.bin"

    import harp.benchmarks._registers as mod

    original_data_dir = mod.DATA_DIR
    mod.DATA_DIR = corpus_dir
    try:
        generate_one(reg, N_ENTRIES, seed=42)
    finally:
        mod.DATA_DIR = original_data_dir

    payload_type = _resolve_payload_type(reg.register)
    return load_register_dump(
        path, reg.register, payload_type, validation=ValidationMode.HEADER
    )


def _get_reg(name):
    return next(r for r in BENCHMARK_REGISTERS if r.name == name)


class TestMaskedFields:
    def test_bitmask_splitter_decoded(self, corpus_dir):
        reg = _get_reg("BitmaskSplitter")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(include_timestamp=True, timestamp="float", decode=True)

        assert "Low" in cols
        assert "High" in cols
        assert cols["Low"].ndim == 1
        assert cols["High"].ndim == 1

        raw_cols = dump.payload_columns(decode=False)
        raw_low = raw_cols["Low"]
        raw_high = raw_cols["High"]
        np.testing.assert_array_equal(cols["Low"], raw_low & 0x0F)
        np.testing.assert_array_equal(cols["High"], (raw_high & 0xF0) >> 4)

    def test_start_pulse_masks(self, corpus_dir):
        reg = _get_reg("StartPulse")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        assert "PulseWidth" in cols
        assert "DigitalOutput" in cols
        assert cols["PulseWidth"].ndim == 1
        assert cols["DigitalOutput"].ndim == 1

    def test_start_pulse_train_masks(self, corpus_dir):
        reg = _get_reg("StartPulseTrain")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        assert "PulseWidth" in cols
        assert "DigitalOutput" in cols
        assert "PulseCount" in cols
        assert "Frequency" in cols
        for name in ("PulseWidth", "DigitalOutput", "PulseCount", "Frequency"):
            assert cols[name].ndim == 1


class TestBoolField:
    def test_complex_config_bool_decoded(self, corpus_dir):
        reg = _get_reg("ComplexConfiguration")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        assert "EventsEnabled" in cols
        assert cols["EventsEnabled"].dtype == np.bool_

    def test_complex_config_enum_stays_int(self, corpus_dir):
        reg = _get_reg("ComplexConfiguration")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        assert "PwmPort" in cols
        assert np.issubdtype(cols["PwmPort"].dtype, np.integer)


class TestMultiElementNamedTuple:
    def test_version_harp_version_single_column(self, corpus_dir):
        reg = _get_reg("Version")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        for field_name in ("HardwareVersion", "FirmwareVersion", "CoreVersion"):
            assert field_name in cols, f"Missing column {field_name}"
            assert cols[field_name].dtype == object
            assert isinstance(cols[field_name][0], HarpVersion)

    def test_version_values_match_per_message(self, corpus_dir):
        reg = _get_reg("Version")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        for i in range(min(10, len(dump))):
            parsed = reg.register.parse(HarpMessage(dump.records[i].tobytes()))
            assert cols["HardwareVersion"][i] == parsed.HardwareVersion
            assert cols["FirmwareVersion"][i] == parsed.FirmwareVersion
            assert cols["CoreVersion"][i] == parsed.CoreVersion


class TestMultiElementPlainArray:
    def test_version_hash_expanded(self, corpus_dir):
        reg = _get_reg("Version")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        for i in range(20):
            key = f"Hash_{i}"
            assert key in cols, f"Missing column {key}"
            assert cols[key].ndim == 1

        assert "Hash" not in cols

    def test_hash_values_match(self, corpus_dir):
        reg = _get_reg("Version")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        for i in range(min(10, len(dump))):
            parsed = reg.register.parse(HarpMessage(dump.records[i].tobytes()))
            for j in range(20):
                assert cols[f"Hash_{j}"][i] == parsed.Hash[j]


class TestStringField:
    def test_version_tag_string(self, corpus_dir):
        reg = _get_reg("Version")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        assert "Tag" in cols
        assert cols["Tag"].ndim == 1


class TestHomogeneousStruct:
    def test_analog_data_decode_passthrough(self, corpus_dir):
        reg = _get_reg("AnalogData")
        dump = _generate_and_load(reg, corpus_dir)
        cols_decoded = dump.columns(decode=True)
        cols_raw = dump.columns(decode=False)

        assert set(cols_decoded.keys()) == set(cols_raw.keys())
        for name in cols_raw:
            assert cols_decoded[name].ndim == 1


class TestScalarRegister:
    def test_digital_inputs_decode_passthrough(self, corpus_dir):
        reg = _get_reg("DigitalInputs")
        dump = _generate_and_load(reg, corpus_dir)
        cols_decoded = dump.columns(decode=True)
        cols_raw = dump.columns(decode=False)

        assert set(cols_decoded.keys()) == set(cols_raw.keys())
        assert "DigitalInputs" in cols_decoded

    def test_counter0_decode_passthrough(self, corpus_dir):
        reg = _get_reg("Counter0")
        dump = _generate_and_load(reg, corpus_dir)
        cols_decoded = dump.columns(decode=True)
        cols_raw = dump.columns(decode=False)

        assert set(cols_decoded.keys()) == set(cols_raw.keys())
        assert "Counter0" in cols_decoded


class TestNamedTupleRegister:
    def test_custom_payload_single_column(self, corpus_dir):
        reg = _get_reg("CustomPayload")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.payload_columns(decode=True)

        assert list(cols.keys()) == ["HarpVersion"]
        assert cols["HarpVersion"].dtype == object
        assert isinstance(cols["HarpVersion"][0], HarpVersion)

    def test_custom_payload_values_match_parse(self, corpus_dir):
        reg = _get_reg("CustomPayload")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.payload_columns(decode=True)

        for i in range(min(10, len(dump))):
            parsed = reg.register.parse(HarpMessage(dump.records[i].tobytes()))
            assert cols["HarpVersion"][i] == parsed

    def test_custom_payload_raw_has_three_columns(self, corpus_dir):
        reg = _get_reg("CustomPayload")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.payload_columns(decode=False)

        assert len(cols) == 3


class TestDecodedColumnNames:
    def test_version_decoded_names(self, corpus_dir):
        reg = _get_reg("Version")
        dump = _generate_and_load(reg, corpus_dir)
        names = dump.decoded_column_names()

        assert "HardwareVersion" in names
        assert "FirmwareVersion" in names
        assert "CoreVersion" in names
        assert "Hash_0" in names
        assert "Hash_19" in names
        assert "Tag" in names

    def test_bitmask_splitter_decoded_names(self, corpus_dir):
        reg = _get_reg("BitmaskSplitter")
        dump = _generate_and_load(reg, corpus_dir)
        names = dump.decoded_column_names()

        assert names == ("Low", "High")

    def test_scalar_register_decoded_names(self, corpus_dir):
        reg = _get_reg("DigitalInputs")
        dump = _generate_and_load(reg, corpus_dir)
        names = dump.decoded_column_names()
        raw_names = dump.column_names()

        assert names == raw_names


class TestDataFrameCreation:
    def test_all_registers_create_dataframe(self, corpus_dir):
        import pandas as pd

        for reg in BENCHMARK_REGISTERS:
            dump = _generate_and_load(reg, corpus_dir)
            cols = dump.columns(
                include_timestamp=True, timestamp="float", decode=True
            )
            df = pd.DataFrame(cols, copy=False)
            assert len(df) == N_ENTRIES, f"{reg.name}: wrong row count"
            assert df.shape[1] > 0, f"{reg.name}: no columns"


class TestRoundTripConsistency:
    def test_masked_values_match_parse(self, corpus_dir):
        reg = _get_reg("BitmaskSplitter")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        for i in range(min(10, len(dump))):
            parsed = reg.register.parse(HarpMessage(dump.records[i].tobytes()))
            assert cols["Low"][i] == parsed.Low
            assert cols["High"][i] == parsed.High

    def test_bool_values_match_raw(self, corpus_dir):
        reg = _get_reg("ComplexConfiguration")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)
        raw = dump.payload_columns(decode=False)

        np.testing.assert_array_equal(
            cols["EventsEnabled"], raw["EventsEnabled"].astype(np.bool_)
        )

    def test_custom_member_converter_match(self, corpus_dir):
        reg = _get_reg("CustomMemberConverter")
        dump = _generate_and_load(reg, corpus_dir)
        cols = dump.columns(decode=True)

        for i in range(min(10, len(dump))):
            parsed = reg.register.parse(HarpMessage(dump.records[i].tobytes()))
            assert cols["Header"][i] == parsed.Header
            assert cols["Data"][i] == parsed.Data
