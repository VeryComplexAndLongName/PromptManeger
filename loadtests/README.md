# Load Testing

This folder provides repeatable load testing for Prompt Manager using Locust.

## What you get

- `locustfile.py`: mixed workload users (`GET /prompts`, search, CRUD, optional optimize).
- `benchmark_rps.py`: runs Locust headless on several user levels and estimates sustainable RPS.
- CSV artifacts per run in `loadtests/results/`.

## Install

```powershell
pip install locust
```

or use project dev dependencies:

```powershell
uv sync --extra dev
```

## Run interactive Locust UI

```powershell
locust -f loadtests/locustfile.py -H http://127.0.0.1:8000
```

Then open: http://127.0.0.1:8089

## Run automated benchmark (RPS + p95 + failures)

```powershell
python loadtests/benchmark_rps.py --host http://127.0.0.1:8000 --duration 45s --users 10 20 40 80
```

## Build charts from benchmark CSV

```powershell
python loadtests/generate_charts.py
```

Generated files:

- `loadtests/chart_rps.png`
- `loadtests/chart_p95_latency.png`
- `loadtests/chart_avg_latency.png`
- `loadtests/chart_failure_rate.png`
- `loadtests/chart_dashboard.png`

Default pass criteria:

- failure rate <= 1%
- p95 <= 500 ms

Override thresholds:

```powershell
python loadtests/benchmark_rps.py --max-failure-rate 0.02 --max-p95-ms 800
```

## Notes

- For realistic data, pre-seed prompts before testing.
- Run server without auto-reload for cleaner numbers (`uvicorn main:app`).
- Keep optimize endpoints in a separate run if you need clean CRUD capacity numbers.
