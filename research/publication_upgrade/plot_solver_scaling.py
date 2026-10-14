#!/usr/bin/env python3
"""Render deterministic SVG and PDF figures from saved solver-study JSON.

Matplotlib is an optional figure-generation dependency. Solver production and
replay continue to use only the Python standard library.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import statistics
import sys
from typing import Any


MIB = 1024 * 1024
COLORS = {
    ("updated", "producer"): "#1769aa",
    ("updated", "replay"): "#c45120",
    ("baseline", "producer"): "#75a9d1",
    ("baseline", "replay"): "#e4a579",
}


def _summary_by_size(data: dict[str, Any]) -> dict[int, dict[str, Any]]:
    rows = data.get("summaries")
    if not isinstance(rows, list) or not rows:
        raise ValueError("input JSON has no nonempty summaries array")
    result = {}
    for row in rows:
        size = row.get("calls_per_arm")
        if type(size) is not int or size <= 0 or size in result:
            raise ValueError("summary sizes must be unique positive integers")
        result[size] = row
    return result


def _median_run_values(data: dict[str, Any], size: int, worker: str,
                       field: str) -> tuple[float, float, float] | None:
    values = []
    for sample in data.get("samples", []):
        if sample.get("calls_per_arm") != size:
            continue
        row = sample.get(worker, {})
        if worker == "producer":
            if row.get("status") not in ("proved_equal", "unequal"):
                continue
        elif row.get("status") != "verified":
            continue
        value = row.get(field)
        if type(value) in (int, float) and math.isfinite(value) and value > 0:
            values.append(float(value))
    if not values:
        return None
    return statistics.median(values), min(values), max(values)


def _rss_median(data: dict[str, Any], size: int, worker: str) -> float | None:
    values = []
    for sample in data.get("samples", []):
        if sample.get("calls_per_arm") != size:
            continue
        row = sample.get(worker, {})
        if worker == "producer":
            if row.get("status") not in ("proved_equal", "unequal"):
                continue
        elif row.get("status") != "verified":
            continue
        value = row.get("peak_rss_bytes")
        if type(value) is int and value > 0:
            values.append(value / MIB)
    return statistics.median(values) if values else None


def _status_unknown(data: dict[str, Any], size: int) -> bool:
    row = _summary_by_size(data)[size]
    return row.get("producer_status_counts", {}).get("unknown", 0) > 0


def _dataset_identity(data: dict[str, Any]) -> tuple[Any, ...]:
    inputs = data.get("inputs", {})
    return (
        inputs.get("kernel_sha256"),
        tuple((row.get("calls_per_arm"), row.get("sha256"))
              for row in inputs.get("graphs", [])),
    )


def _draw(optimized: dict[str, Any], baseline: dict[str, Any] | None):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.lines import Line2D
    except ImportError as error:
        raise SystemExit(
            "figure generation requires optional Matplotlib; install it in the "
            "plotting environment (the solver itself has no plotting dependency)"
        ) from error

    # Stable SVG element IDs and date-free vector metadata make rerenders of
    # the same JSON byte-for-byte reproducible under the same Matplotlib.
    matplotlib.rcParams["svg.hashsalt"] = "orchlang-solver-scaling-figure-v1"
    matplotlib.rcParams["svg.fonttype"] = "none"
    matplotlib.rcParams["pdf.fonttype"] = 42
    matplotlib.rcParams["font.family"] = "DejaVu Sans"

    optimized_rows = _summary_by_size(optimized)
    datasets: list[tuple[str, str, dict[str, Any]]] = [
        ("updated", "Updated", optimized),
    ]
    all_sizes = set(optimized_rows)
    if baseline is not None:
        if _dataset_identity(optimized) != _dataset_identity(baseline):
            raise ValueError("baseline and optimized JSON must bind the same frozen inputs")
        all_sizes.update(_summary_by_size(baseline))
        datasets.insert(0, ("baseline", "Original", baseline))
    sizes = sorted(all_sizes)

    figure, (time_axis, rss_axis) = plt.subplots(
        2, 1, figsize=(10, 7.2), sharex=True,
        gridspec_kw={"height_ratios": [1.15, 1]},
    )
    figure.suptitle("OrchLang exact trace-equivalence solver scaling",
                    x=0.08, y=0.99, ha="left", fontsize=16, fontweight="bold")
    figure.text(
        0.08, 0.946,
        "Symmetric deterministic call chains · median of five isolated workers · one warmup per size",
        fontsize=9, color="#53636d",
    )

    worker_specs = (
        ("producer", "analysis_seconds", "analysis", "o"),
        ("replay", "replay_seconds", "independent replay", "s"),
    )
    for version, version_label, data in datasets:
        for worker, field, worker_label, marker in worker_specs:
            x_values: list[int] = []
            medians: list[float] = []
            minima: list[float] = []
            maxima: list[float] = []
            for size in sizes:
                measured = _median_run_values(data, size, worker, field)
                if measured is None:
                    continue
                median, low, high = measured
                x_values.append(size)
                medians.append(median * 1000)
                minima.append(low * 1000)
                maxima.append(high * 1000)
            if not x_values:
                continue
            color = COLORS[(version, worker)]
            line_style = "--" if version == "baseline" else "-"
            time_axis.plot(
                x_values, medians, color=color, linestyle=line_style,
                marker=marker, markersize=5, linewidth=1.8,
                label=f"{version_label} {worker_label}",
            )
            time_axis.vlines(x_values, minima, maxima, color=color, linewidth=1.0,
                             alpha=0.8)

    time_axis.set_xscale("log", base=2)
    time_axis.set_yscale("log")
    time_axis.set_ylabel("Worker time (ms)")
    time_axis.set_title("Exact result time", loc="left", fontsize=11)
    time_axis.grid(True, which="major", color="#dce3e7", linewidth=0.8)
    time_axis.grid(True, which="minor", axis="y", color="#eef1f3", linewidth=0.5)
    # Reserve a status strip above every measured time value. UNKNOWN markers
    # occupy this strip but have no encoded y-value and never join the lines.
    lower, upper = time_axis.get_ylim()
    time_axis.set_ylim(lower, upper * 4)

    # UNKNOWN has no certified runtime result. Mark it at a fixed panel height
    # with no numerical y-value and never connect it to successful points.
    unknown_legend = []
    for size in sizes:
        for version, label, data in datasets:
            if not _status_unknown(data, size):
                continue
            y_position = 0.96 if version == "baseline" else 0.86
            color = COLORS[(version, "producer")]
            time_axis.scatter(
                [size], [y_position], transform=time_axis.get_xaxis_transform(),
                marker="x", s=44, linewidths=1.8, color=color, zorder=6,
                clip_on=False,
            )
            legend_label = f"{label} UNKNOWN (marker has no time value)"
            if legend_label not in [item.get_label() for item in unknown_legend]:
                unknown_legend.append(Line2D(
                    [], [], color=color, marker="x", linestyle="None",
                    label=legend_label,
                ))

    time_handles, _time_labels = time_axis.get_legend_handles_labels()
    time_axis.legend(handles=time_handles + unknown_legend, frameon=False,
                     ncols=2, loc="upper left", fontsize=8)

    for version, version_label, data in datasets:
        for worker, _field, worker_label, marker in worker_specs:
            x_values, y_values = [], []
            for size in sizes:
                value = _rss_median(data, size, worker)
                if value is None:
                    continue
                x_values.append(size)
                y_values.append(value)
            if x_values:
                rss_axis.plot(
                    x_values, y_values, color=COLORS[(version, worker)],
                    linestyle="--" if version == "baseline" else "-",
                    marker=marker, markersize=5, linewidth=1.8,
                    label=f"{version_label} {worker_label}",
                )
    rss_axis.set_ylabel("Peak worker RSS (MiB)")
    rss_axis.set_xlabel("Calls per arm")
    rss_axis.set_title("Peak RSS for successful analyses and verified replays",
                       loc="left", fontsize=11)
    rss_axis.grid(True, which="major", color="#dce3e7", linewidth=0.8)
    rss_axis.legend(frameon=False, ncols=2, loc="upper left", fontsize=8)
    rss_axis.set_xticks(sizes, [str(size) for size in sizes])
    rss_axis.set_xlim(min(sizes) * 0.82, max(sizes) * 1.38)
    figure.tight_layout(rect=(0.07, 0.045, 0.98, 0.925), h_pad=1.5)
    return figure, matplotlib


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, nargs="?",
                        default=Path(__file__).with_name("solver_scaling.json"))
    parser.add_argument("output_base", type=Path, nargs="?",
                        default=Path(__file__).with_name("solver_scaling"),
                        help="output path base; writes both .svg and .pdf")
    parser.add_argument("--baseline", type=Path,
                        help="optional original-version JSON for a paired comparison")
    args = parser.parse_args()
    optimized_path = args.input.resolve()
    optimized = json.loads(optimized_path.read_text(encoding="utf-8"))
    baseline_path = args.baseline.resolve() if args.baseline else None
    baseline = (json.loads(baseline_path.read_text(encoding="utf-8"))
                if baseline_path else None)
    output_base = args.output_base.resolve()
    if output_base.suffix.lower() in {".svg", ".pdf"}:
        output_base = output_base.with_suffix("")
    output_base.parent.mkdir(parents=True, exist_ok=True)
    figure, matplotlib = _draw(optimized, baseline)
    svg_path, pdf_path = output_base.with_suffix(".svg"), output_base.with_suffix(".pdf")
    metadata = {
        "format": "orchlang-solver-scaling-figure-metadata",
        "version": 1,
        "plotting_dependency": "Matplotlib",
        "plotting_dependency_version": importlib.metadata.version("matplotlib"),
        "plot_script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "inputs": {
            "optimized_json": str(optimized_path),
            "optimized_json_sha256": hashlib.sha256(optimized_path.read_bytes()).hexdigest(),
            "baseline_json": str(baseline_path) if baseline_path else None,
            "baseline_json_sha256": (
                hashlib.sha256(baseline_path.read_bytes()).hexdigest()
                if baseline_path else None
            ),
        },
        "outputs": {"svg": str(svg_path), "pdf": str(pdf_path)},
    }
    figure.savefig(
        svg_path, format="svg", metadata={"Date": None, "Creator": f"Matplotlib {matplotlib.__version__}"},
    )
    figure.savefig(
        pdf_path, format="pdf", metadata={
            "Creator": f"Matplotlib {matplotlib.__version__}",
            "CreationDate": None, "ModDate": None,
        },
    )
    import matplotlib.pyplot as plt
    plt.close(figure)
    metadata["outputs"]["svg_sha256"] = hashlib.sha256(svg_path.read_bytes()).hexdigest()
    metadata["outputs"]["pdf_sha256"] = hashlib.sha256(pdf_path.read_bytes()).hexdigest()
    metadata_path = output_base.with_name(output_base.name + "_plot_metadata.json")
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n",
                             encoding="utf-8")
    print(f"wrote {svg_path}")
    print(f"wrote {pdf_path}")
    print(f"wrote {metadata_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
