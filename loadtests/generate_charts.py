from __future__ import annotations

import csv
import math
import re
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt


@dataclass
class ResultPoint:
    scenario: str
    users: int
    rps: float
    p95_ms: float
    avg_ms: float
    fail_rate_pct: float


def _safe_float(value: str | None) -> float:
    if value is None:
        return math.nan
    raw = value.strip()
    if not raw or raw.upper() == "N/A":
        return math.nan
    try:
        return float(raw)
    except ValueError:
        return math.nan


def _parse_users(file_name: str) -> int | None:
    match = re.match(r"u(\d+)_stats\.csv$", file_name)
    if not match:
        return None
    return int(match.group(1))


def _collect_points(results_root: Path) -> list[ResultPoint]:
    points: list[ResultPoint] = []

    for stats_path in sorted(results_root.rglob("u*_stats.csv")):
        users = _parse_users(stats_path.name)
        if users is None:
            continue

        rel_parent = stats_path.parent.relative_to(results_root)
        scenario = rel_parent.as_posix() if str(rel_parent) != "." else "root"

        with stats_path.open("r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row.get("Name") != "Aggregated":
                    continue

                req_count = _safe_float(row.get("Request Count"))
                fail_count = _safe_float(row.get("Failure Count"))
                rps = _safe_float(row.get("Requests/s"))
                p95 = _safe_float(row.get("95%"))
                avg = _safe_float(row.get("Average Response Time"))

                if math.isnan(req_count) or req_count <= 0:
                    break

                if math.isnan(fail_count):
                    fail_rate_pct = math.nan
                else:
                    fail_rate_pct = (fail_count / req_count) * 100.0

                points.append(
                    ResultPoint(
                        scenario=scenario,
                        users=users,
                        rps=rps,
                        p95_ms=p95,
                        avg_ms=avg,
                        fail_rate_pct=fail_rate_pct,
                    )
                )
                break

    return points


def _plot_metric(points: list[ResultPoint], metric: str, ylabel: str, title: str, output: Path) -> None:
    fig, ax = plt.subplots(figsize=(10, 6))

    scenarios = sorted({p.scenario for p in points})
    for scenario in scenarios:
        subset = sorted((p for p in points if p.scenario == scenario), key=lambda x: x.users)
        xs = [p.users for p in subset]
        ys = [getattr(p, metric) for p in subset]
        ax.plot(xs, ys, marker="o", linewidth=2, label=scenario)

    ax.set_title(title)
    ax.set_xlabel("Users")
    ax.set_ylabel(ylabel)
    ax.grid(True, alpha=0.3)
    ax.legend(title="Scenario")
    fig.tight_layout()
    fig.savefig(output, dpi=150)
    plt.close(fig)


def _plot_dashboard(points: list[ResultPoint], output: Path) -> None:
    scenarios = sorted({p.scenario for p in points})
    fig, axes = plt.subplots(2, 2, figsize=(13, 8))
    metric_map = [
        ("rps", "RPS", "Throughput (RPS)"),
        ("p95_ms", "ms", "P95 Latency"),
        ("avg_ms", "ms", "Average Latency"),
        ("fail_rate_pct", "%", "Failure Rate"),
    ]

    for ax, (metric, unit, title) in zip(axes.flatten(), metric_map, strict=True):
        for scenario in scenarios:
            subset = sorted((p for p in points if p.scenario == scenario), key=lambda x: x.users)
            xs = [p.users for p in subset]
            ys = [getattr(p, metric) for p in subset]
            ax.plot(xs, ys, marker="o", linewidth=2, label=scenario)

        ax.set_title(title)
        ax.set_xlabel("Users")
        ax.set_ylabel(unit)
        ax.grid(True, alpha=0.3)

    handles, labels = axes[0, 0].get_legend_handles_labels()
    if handles:
        fig.legend(handles, labels, loc="upper center", ncol=min(4, len(labels)))

    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(output, dpi=150)
    plt.close(fig)


def main() -> int:
    loadtests_dir = Path(__file__).resolve().parent
    results_root = loadtests_dir / "results"

    points = _collect_points(results_root)
    if not points:
        print("No valid aggregated benchmark points found.")
        return 1

    _plot_metric(
        points,
        metric="rps",
        ylabel="Requests per second",
        title="Load Test Throughput",
        output=loadtests_dir / "chart_rps.png",
    )
    _plot_metric(
        points,
        metric="p95_ms",
        ylabel="ms",
        title="Load Test P95 Latency",
        output=loadtests_dir / "chart_p95_latency.png",
    )
    _plot_metric(
        points,
        metric="avg_ms",
        ylabel="ms",
        title="Load Test Average Latency",
        output=loadtests_dir / "chart_avg_latency.png",
    )
    _plot_metric(
        points,
        metric="fail_rate_pct",
        ylabel="%",
        title="Load Test Failure Rate",
        output=loadtests_dir / "chart_failure_rate.png",
    )
    _plot_dashboard(points, output=loadtests_dir / "chart_dashboard.png")

    print(f"Built charts from {len(points)} aggregated points.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
