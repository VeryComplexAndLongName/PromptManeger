from __future__ import annotations

import argparse
import csv
import math
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class RunResult:
    users: int
    requests_per_s: float
    failure_rate: float
    p95_ms: float
    avg_ms: float
    passed: bool


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Estimate sustainable RPS with Locust step runs.")
    parser.add_argument("--host", default="http://127.0.0.1:8000", help="Base URL for tested API")
    parser.add_argument("--duration", default="45s", help="Duration for each step run, e.g. 45s, 2m")
    parser.add_argument("--users", nargs="+", type=int, default=[10, 20, 40, 80], help="User levels")
    parser.add_argument("--spawn-rate", type=int, default=5, help="Locust spawn rate")
    parser.add_argument("--max-failure-rate", type=float, default=0.01, help="Pass threshold for failure ratio")
    parser.add_argument("--max-p95-ms", type=float, default=500.0, help="Pass threshold for p95 latency")
    parser.add_argument(
        "--locustfile",
        default="loadtests/locustfile.py",
        help="Path to locustfile",
    )
    parser.add_argument(
        "--outdir",
        default="loadtests/results",
        help="Directory where Locust CSV files are written",
    )
    return parser.parse_args()


def _load_aggregated_stats(stats_csv: Path) -> tuple[float, float, float, float] | None:
    with stats_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Name") == "Aggregated":
                req_count = float(row["Request Count"])
                fail_count = float(row["Failure Count"])
                rps = float(row["Requests/s"])
                p95_raw = row["95%"]
                avg_raw = row["Average Response Time"]
                if req_count <= 0 or p95_raw == "N/A" or avg_raw == "N/A":
                    continue
                p95 = float(p95_raw)
                avg = float(avg_raw)
                failure_rate = (fail_count / req_count) if req_count else 0.0
                return rps, failure_rate, p95, avg
    return None


def _fmt(value: float) -> str:
    return f"{value:.2f}"


def main() -> int:
    args = parse_args()

    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    results: list[RunResult] = []

    for users in args.users:
        prefix = outdir / f"u{users}"
        cmd = [
            sys.executable,
            "-m",
            "locust",
            "-f",
            args.locustfile,
            "--headless",
            "--host",
            args.host,
            "-u",
            str(users),
            "-r",
            str(args.spawn_rate),
            "-t",
            args.duration,
            "--only-summary",
            "--csv",
            str(prefix),
        ]

        print(f"\n== Running users={users}, duration={args.duration} ==")
        completed = subprocess.run(cmd, check=False)
        if completed.returncode != 0:
            print(f"Locust run failed for users={users} (exit={completed.returncode})")
            break

        stats_csv = Path(f"{prefix}_stats.csv")
        if not stats_csv.exists():
            print(f"Stats CSV missing for users={users}: {stats_csv}")
            break

        parsed_stats = _load_aggregated_stats(stats_csv)
        if parsed_stats is None:
            print(f"No valid aggregated stats for users={users}; marking as failed step.")
            results.append(
                RunResult(
                    users=users,
                    requests_per_s=0.0,
                    failure_rate=1.0,
                    p95_ms=float("inf"),
                    avg_ms=float("inf"),
                    passed=False,
                )
            )
            continue

        rps, failure_rate, p95, avg = parsed_stats
        passed = failure_rate <= args.max_failure_rate and p95 <= args.max_p95_ms

        results.append(
            RunResult(
                users=users,
                requests_per_s=rps,
                failure_rate=failure_rate,
                p95_ms=p95,
                avg_ms=avg,
                passed=passed,
            )
        )

        print(
            "users={users} rps={rps} failure_rate={failure_rate} p95={p95}ms avg={avg}ms pass={passed}".format(
                users=users,
                rps=_fmt(rps),
                failure_rate=_fmt(failure_rate * 100) + "%",
                p95=_fmt(p95),
                avg=_fmt(avg),
                passed=passed,
            )
        )

    if not results:
        print("No successful runs were completed.")
        return 1

    passed_results = [r for r in results if r.passed]
    best = max(passed_results, key=lambda item: item.requests_per_s) if passed_results else None

    finite_avg = [r.avg_ms for r in results if math.isfinite(r.avg_ms)]
    rms_latency = math.sqrt(sum(v * v for v in finite_avg) / len(finite_avg)) if finite_avg else float("inf")

    print("\n== Summary ==")
    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(
            f"{status} users={r.users} rps={_fmt(r.requests_per_s)} "
            f"p95={_fmt(r.p95_ms)}ms fail={_fmt(r.failure_rate * 100)}%"
        )

    print(f"RMS(avg_latency_ms) across runs: {_fmt(rms_latency)}")

    if best:
        print(
            "Estimated sustainable throughput: "
            f"{_fmt(best.requests_per_s)} RPS at users={best.users} "
            f"(p95={_fmt(best.p95_ms)}ms, fail={_fmt(best.failure_rate * 100)}%)"
        )
        return 0

    print("No run satisfied thresholds. Reduce load or loosen SLO thresholds.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
