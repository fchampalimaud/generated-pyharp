from __future__ import annotations

from statistics import mean, stdev
from timeit import Timer

from benchmark_common import (
    BenchmarkCase,
    comparison_cases,
    dataset_summary,
    print_ratio_summary,
    print_sample_output,
    sanity_check,
)

SHOW_SAMPLE_OUTPUT = True

RUNS = 20
MIN_TIME = 0.5


def run_benchmark(case: BenchmarkCase) -> dict[str, float]:
    timer = Timer(case.run)

    loops, total = timer.autorange()
    while total < MIN_TIME:
        loops *= 2
        total = timer.timeit(number=loops)

    samples = timer.repeat(repeat=RUNS, number=loops)
    per_run = [sample / loops for sample in samples]

    stats = {
        "mean": mean(per_run),
        "stdev": stdev(per_run) if len(per_run) > 1 else 0.0,
        "min": min(per_run),
        "max": max(per_run),
        "loops": float(loops),
    }

    print(
        f"  {case.label:<52s}"
        f"min={stats['min']:.6f}s  "
        f"mean={stats['mean']:.6f}s  "
        f"max={stats['max']:.6f}s  "
        f"stdev={stats['stdev']:.6f}s  "
        f"(n={RUNS}, loops={loops})"
    )
    return stats


def main() -> None:
    summary = dataset_summary()
    path = summary["path"]
    size_mib = summary["size_mib"]
    rows = summary["rows"]
    stride = summary["stride"]

    cases = comparison_cases()

    print("\n=== AnalogData benchmark (timeit) ===")
    print(f"  File  : {path.name}  ({size_mib:.1f} MiB)")
    print(f"  Frames: {rows:,}  |  stride={stride} bytes")

    # show summary for complex config payload
    summary_complex = dataset_summary(path=path.parent / "complex_config_34.bin")
    path = summary_complex["path"]
    size_mib = summary_complex["size_mib"]
    rows = summary_complex["rows"]
    stride = summary_complex["stride"]
    print(f"\n  File  : {path.name}  ({size_mib:.1f} MiB)")
    print(f"  Frames: {rows:,}  |  stride={stride} bytes")

    print("\nSanity check:")
    sanity_check()

    if SHOW_SAMPLE_OUTPUT:
        print_sample_output()

    print(f"\nBenchmark ({RUNS} repeats):")
    results: dict[str, dict[str, float]] = {}
    for case in cases:
        results[case.name] = run_benchmark(case)

    print_ratio_summary(
        "Ratios vs harp-python baseline:",
        results,
        cases,
    )


if __name__ == "__main__":
    main()
