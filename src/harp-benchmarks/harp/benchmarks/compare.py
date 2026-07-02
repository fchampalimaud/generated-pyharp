from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class DatasetRow:
    name: str
    addr: int
    frames: int
    payload_bytes: int
    stride: int
    file_mib: float


@dataclass
class TimingRow:
    name: str
    pre_mean: float | None = None
    pre_min: float | None = None
    re_mean: float | None = None
    mean: float | None = None
    min: float | None = None


@dataclass
class DecompRow:
    name: str
    load: float
    to_columns: float
    df: float
    residual: float


@dataclass
class ReportData:
    env: dict[str, str] = field(default_factory=dict)
    datasets: dict[str, DatasetRow] = field(default_factory=dict)
    load: dict[str, TimingRow] = field(default_factory=dict)
    df: dict[str, TimingRow] = field(default_factory=dict)
    to_columns: dict[str, TimingRow] = field(default_factory=dict)
    decomp: dict[str, DecompRow] = field(default_factory=dict)


def _parse_table_rows(text: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.split("|")]
        cells = cells[1:-1]
        if cells and all(re.fullmatch(r"-+:?|:?-+:?", c) for c in cells):
            continue
        rows.append(cells)
    return rows


def _parse_float(s: str) -> float:
    return float(s.replace(",", ""))


def _parse_int(s: str) -> int:
    return int(s.replace(",", ""))


def parse_report(text: str) -> ReportData:
    data = ReportData()

    sections: list[tuple[str, str]] = []
    parts = re.split(r"^## ", text, flags=re.MULTILINE)
    for part in parts[1:]:
        title_end = part.find("\n")
        title = part[:title_end].strip() if title_end > 0 else part.strip()
        body = part[title_end:] if title_end > 0 else ""
        sections.append((title, body))

    stage_index = 0
    for title, body in sections:
        rows = _parse_table_rows(body)
        if not rows:
            continue

        title_lower = title.lower()

        if "environment" in title_lower:
            for row in rows[1:]:
                if len(row) >= 2:
                    data.env[row[0]] = row[1]

        elif "dataset" in title_lower:
            for row in rows[1:]:
                if len(row) >= 6:
                    ds = DatasetRow(
                        name=row[0],
                        addr=_parse_int(row[1]),
                        frames=_parse_int(row[2]),
                        payload_bytes=_parse_int(row[3]),
                        stride=_parse_int(row[4]),
                        file_mib=_parse_float(row[5]),
                    )
                    data.datasets[ds.name] = ds

        elif "decomposition" in title_lower:
            for row in rows[1:]:
                if len(row) >= 5:
                    data.decomp[row[0]] = DecompRow(
                        name=row[0],
                        load=_parse_float(row[1]),
                        to_columns=_parse_float(row[2]),
                        df=_parse_float(row[3]),
                        residual=_parse_float(row[4]),
                    )

        elif "to_columns" in title_lower or "decode only" in title_lower:
            for row in rows[1:]:
                if len(row) >= 4:
                    data.to_columns[row[0]] = TimingRow(
                        name=row[0],
                        mean=_parse_float(row[2]),
                        min=_parse_float(row[3]),
                    )

        elif any(
            kw in title_lower
            for kw in ("dataframe", "full path", "parse_to_dataframe")
        ):
            for row in rows[1:]:
                if len(row) >= 7:
                    data.df[row[0]] = TimingRow(
                        name=row[0],
                        pre_mean=_parse_float(row[2]),
                        pre_min=_parse_float(row[3]),
                        re_mean=_parse_float(row[6]),
                    )

        elif any(
            kw in title_lower
            for kw in ("load", "parse_bulk", "core parse", "core zero-copy")
        ):
            for row in rows[1:]:
                if len(row) >= 7:
                    data.load[row[0]] = TimingRow(
                        name=row[0],
                        pre_mean=_parse_float(row[2]),
                        pre_min=_parse_float(row[3]),
                        re_mean=_parse_float(row[6]),
                    )

    return data


def _speedup_label(
    val_a: float, val_b: float, label_a: str, label_b: str
) -> tuple[str, str]:
    if val_a <= 0 or val_b <= 0:
        return ("n/a", "")
    ratio = val_b / val_a
    if 0.95 <= ratio <= 1.05:
        delta_pct = ((val_a - val_b) / val_b) * 100
        return (f"{delta_pct:+.1f}%", "~same")
    if ratio > 1.0:
        delta_pct = ((val_b - val_a) / val_a) * 100
        return (f"-{delta_pct:.1f}%", f"{label_a} {ratio:.2f}x")
    else:
        inv = val_a / val_b
        delta_pct = ((val_a - val_b) / val_b) * 100
        return (f"+{delta_pct:.1f}%", f"{label_b} {inv:.2f}x")


def _build_footnotes(
    common: list[str],
    ds_a: dict[str, DatasetRow],
    ds_b: dict[str, DatasetRow],
    label_a: str,
    label_b: str,
) -> dict[str, str]:
    notes: dict[str, str] = {}
    for name in common:
        a, b = ds_a.get(name), ds_b.get(name)
        if a is None or b is None:
            continue
        if a.payload_bytes != b.payload_bytes or a.stride != b.stride:
            notes[name] = (
                f"Payload size differs ({label_a}: {a.payload_bytes}B / "
                f"{a.stride}B stride, {label_b}: {b.payload_bytes}B / "
                f"{b.stride}B stride). The two implementations encode "
                f"this register differently, so timing comparison is not "
                f"directly meaningful."
            )
    return notes


def _footnote_block(
    footnotes: dict[str, str],
    used: set[str],
) -> list[str]:
    relevant = {k: v for k, v in footnotes.items() if k in used}
    if not relevant:
        return []
    out: list[str] = []
    for name, text in relevant.items():
        out.append(f"*\\* {name}: {text}*")
    out.append("")
    return out


def compare_reports(
    a: ReportData,
    b: ReportData,
    *,
    label_a: str = "A",
    label_b: str = "B",
) -> str:
    lines: list[str] = []
    lines.append(f"# Benchmark comparison: {label_a} vs {label_b}\n")

    lines.append("## Environment\n")
    all_keys = list(dict.fromkeys(list(a.env.keys()) + list(b.env.keys())))
    lines.append(f"| Key | {label_a} | {label_b} |")
    lines.append("| --- | --- | --- |")
    for key in all_keys:
        lines.append(f"| {key} | {a.env.get(key, '-')} | {b.env.get(key, '-')} |")
    lines.append("")

    all_reg_names = list(
        dict.fromkeys(list(a.datasets.keys()) + list(b.datasets.keys()))
    )
    only_a = [n for n in all_reg_names if n in a.datasets and n not in b.datasets]
    only_b = [n for n in all_reg_names if n not in a.datasets and n in b.datasets]
    common = [n for n in all_reg_names if n in a.datasets and n in b.datasets]

    footnotes = _build_footnotes(common, a.datasets, b.datasets, label_a, label_b)

    if only_a or only_b:
        lines.append("## Register coverage\n")
        if only_a:
            lines.append(f"Registers only in **{label_a}**: {', '.join(only_a)}\n")
        if only_b:
            lines.append(f"Registers only in **{label_b}**: {', '.join(only_b)}\n")

    lines.append("## Datasets\n")
    lines.append(
        f"| Register | {label_a} Payload (B) | {label_b} Payload (B) | "
        f"{label_a} Stride (B) | {label_b} Stride (B) | |"
    )
    lines.append("| --- | ---: | ---: | ---: | ---: | --- |")
    for name in common:
        da, db = a.datasets[name], b.datasets[name]
        mark = " \\*" if name in footnotes else ""
        lines.append(
            f"| {name} | {da.payload_bytes} | {db.payload_bytes} | "
            f"{da.stride} | {db.stride} |{mark} |"
        )
    lines.append("")
    lines.extend(_footnote_block(footnotes, set(common)))

    def _timing_table(
        title: str,
        get_a: dict[str, TimingRow],
        get_b: dict[str, TimingRow],
        value_attr: str,
    ) -> None:
        lines.append(f"## {title}\n")
        lines.append(
            f"| Register | {label_a} (ms) | {label_b} (ms) | Delta | Speedup | |"
        )
        lines.append("| --- | ---: | ---: | ---: | --- | --- |")
        used: set[str] = set()
        for name in common:
            row_a = get_a.get(name)
            row_b = get_b.get(name)
            if row_a is None or row_b is None:
                continue
            va = getattr(row_a, value_attr, None)
            vb = getattr(row_b, value_attr, None)
            if va is None or vb is None:
                continue
            delta, speedup = _speedup_label(va, vb, label_a, label_b)
            mark = ""
            if name in footnotes:
                mark = " \\*"
                used.add(name)
            lines.append(
                f"| {name} | {va:.2f} | {vb:.2f} | {delta} | {speedup} |{mark} |"
            )
        lines.append("")
        lines.extend(_footnote_block(footnotes, used))

    _timing_table("Load / parse (pre-read)", a.load, b.load, "pre_mean")
    _timing_table("Load / parse (re-read)", a.load, b.load, "re_mean")
    _timing_table("DataFrame (pre-read)", a.df, b.df, "pre_mean")
    _timing_table("DataFrame (re-read)", a.df, b.df, "re_mean")
    _timing_table("to_columns (decode only)", a.to_columns, b.to_columns, "mean")

    if a.decomp and b.decomp:
        lines.append("## Decomposition (pre-read means, ms)\n")
        lines.append(
            f"| Register "
            f"| {label_a} load | {label_b} load | load Delta "
            f"| {label_a} cols | {label_b} cols | cols Delta "
            f"| {label_a} df | {label_b} df | df Delta "
            f"| {label_a} resid | {label_b} resid | |"
        )
        lines.append(
            "| --- "
            "| ---: | ---: | ---: "
            "| ---: | ---: | ---: "
            "| ---: | ---: | ---: "
            "| ---: | ---: | --- |"
        )
        used: set[str] = set()
        for name in common:
            da = a.decomp.get(name)
            db = b.decomp.get(name)
            if da is None or db is None:
                continue
            _, load_spd = _speedup_label(da.load, db.load, label_a, label_b)
            _, cols_spd = _speedup_label(
                da.to_columns, db.to_columns, label_a, label_b
            )
            _, df_spd = _speedup_label(da.df, db.df, label_a, label_b)
            mark = ""
            if name in footnotes:
                mark = " \\*"
                used.add(name)
            lines.append(
                f"| {name} "
                f"| {da.load:.2f} | {db.load:.2f} | {load_spd} "
                f"| {da.to_columns:.2f} | {db.to_columns:.2f} | {cols_spd} "
                f"| {da.df:.2f} | {db.df:.2f} | {df_spd} "
                f"| {da.residual:.2f} | {db.residual:.2f} |{mark} |"
            )
        lines.append("")
        lines.extend(_footnote_block(footnotes, used))

    return "\n".join(lines)


def _use_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main() -> None:
    _use_utf8_console()
    parser = argparse.ArgumentParser(
        description="Compare two harp benchmark reports side-by-side."
    )
    parser.add_argument("report_a", type=Path, help="First report.md")
    parser.add_argument("report_b", type=Path, help="Second report.md")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Output comparison file (default: stdout)",
    )
    parser.add_argument("--label-a", default="A", help="Label for first report")
    parser.add_argument("--label-b", default="B", help="Label for second report")
    args = parser.parse_args()

    text_a = args.report_a.read_text(encoding="utf-8")
    text_b = args.report_b.read_text(encoding="utf-8")

    data_a = parse_report(text_a)
    data_b = parse_report(text_b)

    result = compare_reports(
        data_a, data_b, label_a=args.label_a, label_b=args.label_b
    )

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
        print(f"Comparison written to {args.output}")
    else:
        print(result)


if __name__ == "__main__":
    main()
