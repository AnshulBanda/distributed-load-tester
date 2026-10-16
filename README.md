# Distributed Load Tester

A learning project: a distributed HTTP load testing platform, built phase by phase to practice system design (coordination, scaling, metrics aggregation, failure handling).

**Status:** work in progress. Phases 1 and 2 are done (a single open-loop load generator and a test target, both running in Docker). The distributed parts (coordinator, multiple workers, metric aggregation, autoscaling) are not built yet.

## What exists today

- `loadgen.py`: an open-loop load generator. It sends requests on a fixed schedule regardless of how fast the target responds, and measures latency from the intended send time, so an overloaded generator shows up in the numbers instead of being hidden.
- `target.py`: a small FastAPI service to test against, with adjustable latency, random error rate, and a concurrency limit.
- Docker Compose setup to run both on a private network.

## Run it

Requires Docker Desktop.

```powershell
docker compose --profile loadtest build
docker compose up -d target
docker compose run --rm loadgen --rps 100 --duration 10
docker compose down
```

Make the target slower or flakier with environment variables before starting it (PowerShell syntax):

```powershell
$env:LATENCY_MS = 500
$env:ERROR_RATE = 0.05
$env:MAX_CONCURRENCY = 10
docker compose up -d target
```

Clear them afterwards with `Remove-Item Env:LATENCY_MS, Env:ERROR_RATE, Env:MAX_CONCURRENCY`.

## Run without Docker

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn target:app --port 8000
python loadgen.py --url http://127.0.0.1:8000/work --rps 100 --duration 10
```

## Documentation

- [Design document](docs/load-testing-platform-design.md): architecture, decisions and tradeoffs, failure modes, validation plan, measured results.
- [Checkpoint](docs/checkpoint.md): progress, findings, decisions log, and session history.

## Roadmap

1. Single open-loop load generator (done)
2. Containerize generator and target (done)
3. Coordinator + multiple workers
4. Histogram-based metric aggregation
5. Autoscaler
6. Failure injection and handling
7. Final write-up
