from __future__ import annotations

import argparse
import statistics
import timeit

import pandas as pd
from harp.data import ValidationMode, load_register_dump

from harp.benchmarks._registers import (
    BENCHMARK_REGISTERS,
    BenchmarkedRegister,
    REPORT_PATH,
    corpus_path,
)
from harp.benchmarks.generate import _resolve_payload_type, ensure_corpus


def _benchmark_register(
    reg: BenchmarkedRegister,
    runs: int,
) -> dict[str, dict[str, float]] | None:
    path = corpus_path(reg)
    if not path.exists():
        print(f"  {reg.name}: corpus not found, skipping.")
        return None

    register_cls = reg.register
    payload_type = _resolve_payload_type(register_cls)
    file_size = path.stat().st_size

    results: dict[str, dict[str, float]] = {}

    # -- load_register_dump (re-read from disk each run) --
    def load_reread():
        return load_register_dump(
            path, register_cls, payload_type, validation=ValidationMode.HEADER
        )

    timeit.Timer(load_reread).timeit(1)  # warm-up
    times = timeit.Timer(load_reread).repeat(runs, 1)
    results["load_reread"] = _summarize(times)

    # -- columns -> DataFrame --
    dump = load_reread()
    n_frames = len(dump)
    actual_frame_size = file_size / n_frames if n_frames else 0

    def columns_to_df():
        data = dump.columns(include_timestamp=True, timestamp="float")
        return pd.DataFrame(data, copy=False)

    try:
        timeit.Timer(columns_to_df).timeit(1)
        times = timeit.Timer(columns_to_df).repeat(runs, 1)
        results["to_dataframe"] = _summarize(times)
    except ValueError:
        print(f"    to_dataframe   : skipped (multi-dim columns)")

    # -- full path: load + DataFrame --
    def full_path():
        d = load_register_dump(
            path, register_cls, payload_type, validation=ValidationMode.HEADER
        )
        data = d.columns(include_timestamp=True, timestamp="float")
        return pd.DataFrame(data, copy=False)

    try:
        timeit.Timer(full_path).timeit(1)
        times = timeit.Timer(full_path).repeat(runs, 1)
        results["full_path"] = _summarize(times)
    except ValueError:
        pass

    results["_meta"] = {
        "frames": float(n_frames),
        "file_mib": file_size / (1024**2),
        "frame_size": actual_frame_size,
    }

    return results


def _summarize(times: list[float]) -> dict[str, float]:
    return {
        "min": min(times),
        "mean": statistics.mean(times),
        "max": max(times),
        "stdev": statistics.stdev(times) if len(times) > 1 else 0.0,
    }


def _format_row(name: str, stage: str, stats: dict[str, float], meta: dict[str, float]) -> str:
    frames = meta["frames"]
    mib = meta["file_mib"]
    t = stats["min"]
    mframes_s = (frames / t / 1e6) if t > 0 else 0
    mib_s = (mib / t) if t > 0 else 0

    return (
        f"| {name:<25s} | {stage:<16s} "
        f"| {stats['min']*1000:8.2f} | {stats['mean']*1000:8.2f} "
        f"| {stats['max']*1000:8.2f} | {stats['stdev']*1000:8.2f} "
        f"| {mframes_s:8.2f} | {mib_s:8.1f} |"
    )


def _write_report(
    all_results: dict[str, dict[str, dict[str, float]]],
    runs: int,
    entries: int,
) -> None:
    lines = [
        "# Harp Benchmark Report",
        "",
        f"- Runs: {runs}",
        f"- Entries per register: {entries:,}",
        "",
        "| Register                  | Stage            |  min(ms) | mean(ms) |  max(ms) | stdev(ms) | Mframes/s |  MiB/s |",
        "|---------------------------|------------------|----------|----------|----------|-----------|-----------|--------|",
    ]

    for name, results in all_results.items():
        meta = results["_meta"]
        for stage in ("load_reread", "to_dataframe", "full_path"):
            if stage in results:
                lines.append(_format_row(name, stage, results[stage], meta))
        lines.append(
            f"|                           |                  |          |          |          |           |           |        |"
        )

    report = "\n".join(lines) + "\n"
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report)
    print(f"\nReport written to {REPORT_PATH}")


def main():
    parser = argparse.ArgumentParser(description="Run harp benchmarks.")
    parser.add_argument("--runs", type=int, default=5)
    parser.add_argument("--entries", type=int, default=1_000_000)
    parser.add_argument("--only", nargs="*", default=None)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--head", action="store_true", help="Only run first 3 registers.")
    args = parser.parse_args()

    registers = BENCHMARK_REGISTERS
    if args.only:
        names = set(args.only)
        registers = [r for r in registers if r.name in names]
    if args.head:
        registers = registers[:3]

    print(f"Ensuring corpus ({args.entries:,} entries)...")
    for reg in registers:
        ensure_corpus(reg, args.entries, force=args.force)

    print(f"\nBenchmarking ({args.runs} runs)...")
    all_results: dict[str, dict[str, dict[str, float]]] = {}

    for reg in registers:
        print(f"  {reg.name}...")
        result = _benchmark_register(reg, args.runs)
        if result is not None:
            all_results[reg.name] = result

            meta = result["_meta"]
            for stage in ("load_reread", "to_dataframe", "full_path"):
                if stage in result:
                    s = result[stage]
                    print(
                        f"    {stage:<16s}: "
                        f"min={s['min']*1000:.2f}ms  "
                        f"mean={s['mean']*1000:.2f}ms"
                    )

    _write_report(all_results, args.runs, args.entries)


if __name__ == "__main__":
    main()
