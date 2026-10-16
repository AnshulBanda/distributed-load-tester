# Checkpoint: Distributed Load Testing Platform

**Last updated:** 2026-10-16
**Current phase:** Phases 1 and 2 complete. Phase 3 (coordinator + multiple workers) not started.
**Next action:** (Recommended before Phase 3) find the container ceiling with a 300 / 400 / 600 RPS sweep and `docker stats`. Then start Phase 3.

---

## How to resume with Claude

Paste or upload this file at the start of a new conversation, along with `load-testing-platform-design.md` if the design matters for the task, and the code files if the code matters. Then say which phase you're on and what you're stuck on. Update this file at the end of each work session.

---

## Project Summary

A distributed load testing platform built to learn system design. Workers generate open-loop HTTP load, a coordinator splits and synchronizes the work, metrics are aggregated using mergeable histograms, and an autoscaler adjusts the worker count.

**Developer background:** Beginner with Docker and Kubernetes; has not used Go. Develops on Windows (PowerShell, venv, Docker Desktop). Wants to understand every piece of code, not just run it. After Phase 2 felt like they were "vibe coding" and asked for slow, simple, beginner-level explanations.

## Stack (decided)

| Layer | Choice |
|-------|--------|
| Language | Python 3.12 (asyncio) |
| Coordinator API | FastAPI |
| HTTP client | httpx (in use); aiohttp comparison deferred |
| Coordination + metrics | Redis |
| Containers | Docker Compose only (Kubernetes is a stretch goal) |
| Histograms | HdrHistogram or fixed-bucket (undecided) |
| Dashboards | None at first; Grafana is a stretch goal |

## Progress

Legend: `[ ]` not started, `[~]` in progress, `[x]` done

### Planning
- [x] Project idea and scope defined
- [x] Stack trimmed to Python + Docker Compose + Redis
- [x] Design doc written (`load-testing-platform-design.md`, now v0.3)
- [x] Checkpoint file created
- [x] Walkthrough of ideation, Phase 1 and Phase 2 given in plain language

### Implementation
- [x] **Phase 1:** Single open-loop async load generator with latency recording (`loadgen.py`, with `target.py` as the test target)
- [x] **Phase 2:** Generator and target in Docker, run together with Compose (`Dockerfile.target`, `Dockerfile.loadgen`, `docker-compose.yml`, `.dockerignore`); healthcheck + `depends_on`; `TARGET_URL` env var; open-loop proof and concurrency-cap test run
- [ ] **Phase 3:** Coordinator + multiple workers: registry, heartbeats, assignments, synchronized start (est. 3-4 days)
- [ ] **Phase 4:** Histogram-based metric aggregation and live global percentiles (est. 2-3 days)
- [ ] **Phase 5:** Autoscaler using the Docker SDK (est. 2 days)
- [ ] **Phase 6:** Failure injection and handling policy (est. 1-2 days)
- [ ] **Phase 7:** Update design doc with results, diagrams, and final tradeoffs (est. 1-2 days)

### Before Phase 3 (recommended)
- [ ] Container ceiling sweep: 300 / 400 / 600 RPS with `docker compose run --rm loadgen --rps N --duration 10`, plus `docker stats --no-stream` in a second window during each run to see which container is saturated (generator: high lag and loadgen near 100% CPU; target: p50 climbs while lag stays low and target near 100% CPU)

### Optional follow-ups (deferred, not blocking)
- [ ] Compare against an aiohttp version of `fire()`
- [ ] Try the Windows selector event loop policy for native runs
- [ ] Break something on purpose: replace `create_task(fire(...))` with `await fire(...)` in `loadgen.py` (makes it closed-loop) and rerun the 500 ms target test to see the difference
- [ ] Improve the lag warning: report p95 lag or share of requests sent more than 50 ms late, instead of only max lag
- [ ] Report latency for successes and errors separately

### Stretch goals
- [ ] Grafana dashboard
- [ ] Ramp profiles (step, spike)
- [ ] Kubernetes with HPA or KEDA
- [ ] Persistent run history

## Findings So Far

1. **Open-loop measurement catches real saturation.** Because latency is measured from the intended send time, overloaded runs expose that the generator, not the target, is the bottleneck. A closed-loop tool would hide this. Confirmed again in Phase 2: with the target at 500 ms, achieved RPS stayed at 100.1 while p50 rose to 508 ms.
2. **Native Windows has a cliff around 150-200 RPS.** Max schedule lag was 0 / 12 / 26 ms at 50 / 100 / 150 RPS, then 2,097 ms at 200 RPS. A feedback loop (falling behind causes bursts, bursts cost CPU) is a hypothesis, not confirmed.
3. **That ceiling is a native-Windows limit, not a general one.** In containers the generator held 150 and 200 RPS (max lag 66 ms and 28 ms). The container ceiling is above 200 and not yet found. Why Linux containers do better is untested (possible: faster event loop, simpler network path).
4. **On Windows, use `127.0.0.1`, not `localhost`,** for native runs. It improved the 200 RPS run from 109 to 165 achieved RPS. Likely cause: IPv6-first resolution (not verified).
5. **Do not load test through Docker's published port from Windows.** A native generator hitting the container's published port got 72 RPS at a 100 RPS target with 3.8 s lag. Run the generator inside the Compose network. Cause unverified (probably port-forwarding overhead).
6. **Max schedule lag is a noisy signal.** It was 66 ms at 150 RPS but 28 ms at 200 RPS. The earlier idea that lag rises smoothly before saturation does not hold for the max. A smoother statistic (p95 lag, share of late sends) is the candidate autoscaling signal. Still a hypothesis.
7. **The lag warning (50 ms on max lag) is too sensitive.** It fired on runs where p50 and p95 were fine; a brief hiccup inflates only p99 and max.
8. **Load shedding matches theory.** Cap of 10 in flight with ~100 ms requests at 150 RPS: 38.3% got 503. Erlang-B predicts about 41%.
9. **Mixed latency can mislead.** In the cap test, p50 (93 ms) was below the 100 ms service time because instant 503s pull the median down. Report successes and errors separately.
10. **The target is a single process,** so at higher aggregate RPS it will saturate too. Distinguish "generator saturated" from "target saturated" before trusting results.
11. **A healthcheck did its job.** The missing `/health` route made Docker mark the target unhealthy and Compose refused to start the load generator.

## Decisions Log

Record each decision with the date, the options considered, and the reason.

| Date | Decision | Alternatives considered | Reason |
|------|----------|------------------------|--------|
| 2026-10-09 | Python instead of Go | Go | Avoid learning a new language alongside system design |
| 2026-10-09 | Docker Compose instead of Kubernetes | Kubernetes (kind/minikube) | Avoid orchestration learning curve; `--scale` is enough |
| 2026-10-09 | Redis as single coordination layer | Message queue + separate DB | Fewer dependencies; revisit at scale (see design doc Section 12) |
| 2026-10-09 | Open-loop load model | Closed-loop | Avoid coordinated omission |
| 2026-10-09 | Mergeable histograms for metrics | Per-worker percentiles | Percentiles cannot be averaged |
| 2026-10-11 | Use `127.0.0.1`, not `localhost`, for native local runs on Windows | `localhost` | 109 to 165 achieved RPS at 200 RPS target |
| 2026-10-11 | Stop tuning the native single worker and move on to Phase 2 | Keep optimizing (aiohttp, selector loop) | Optimizations deferred |
| Phase 2 | Run the generator inside the Compose network (`http://target:8000`) | Hit the published port from the host | Published-port path was far too slow on Windows (72 RPS at a 100 target) |
| Phase 2 | Pass the target URL via the `TARGET_URL` env var | Hardcoded or CLI-only | Matches how workers will be configured in Phase 3 |
| Phase 2 | Healthcheck + `depends_on: service_healthy`; loadgen under a Compose profile | Start everything together | Don't test against a service that isn't ready; run the generator on demand |
| Phase 2 | `cpus: 1.0` on each container | No limits | More reproducible and closer to how workers will run |
| Phase 2 | **Superseded:** earlier provisional `per_worker_capacity` = 120 RPS | n/a | Based on native Windows runs. Re-measure in containers before using it in the autoscaler |

## Measured Results

### Phase 1: native Windows (httpx, target on same machine, 50 ms nominal target latency)

| Client URL | Target RPS | Achieved send RPS | Max lag | p50 | p95 | p99 | Valid? |
|-----------|-----------|-------------------|---------|-----|-----|-----|--------|
| `localhost` | 200 | 109.3 | 8,298 ms | 5,460 ms | 8,952 ms | 9,837 ms | No |
| `127.0.0.1` | 200 | 165.3 | 2,097 ms | 704 ms | 3,158 ms | 4,005 ms | No |
| `127.0.0.1` | 50 | 50.1 | 0 ms | 69 ms | 79 ms | 81 ms | Yes |
| `127.0.0.1` | 100 | 100.1 | 12 ms | 67 ms | 78 ms | 79 ms | Yes |
| `127.0.0.1` | 150 | 150.0 | 26 ms | 66 ms | 80 ms | 84 ms | Yes |

### Phase 2: Docker containers (each capped at 1 CPU, generator to target over the Compose network)

| Scenario | Achieved RPS | Max lag | p50 | p95 | p99 | Valid? |
|----------|--------------|---------|-----|-----|-----|--------|
| 100 RPS, 50 ms target | 100.1 | 15 ms | 56 ms | 65 ms | 68 ms | Yes |
| 150 RPS | 150.1 | 66 ms | 57 ms | 67 ms | 128 ms | Mostly (tail inflated, warning fired) |
| 200 RPS | 200.1 | 28 ms | 57 ms | 67 ms | 73 ms | Yes |
| Target 500 ms, 100 RPS | 100.1 | 56 ms | 508 ms | 597 ms | 607 ms | Mostly (warning fired; median and p95 fine) |
| Target 100 ms, cap 10, 150 RPS | 150.1 | 26 ms | 93 ms | 123 ms | 126 ms | Yes (38.3% 503s) |
| Native generator to published port, 100 RPS | 72.4 | 3,809 ms | 3,355 ms | 5,185 ms | 6,316 ms | No |

### Summary table

| Metric | Value | Notes |
|--------|-------|-------|
| Max clean RPS per worker, native Windows (httpx) | ~150 (fails by 200) | Windows-specific limit |
| Max clean RPS per worker, container (httpx, 1 CPU) | At least 200; ceiling not found | Sweep at 300 / 400 / 600 pending |
| Max RPS per worker (aiohttp) | Not tested | Deferred |
| Baseline latency vs. nominal | p50 ~67 ms native, ~56 ms in containers, vs. 50 ms nominal | Unexplained. Hypothesis: Windows timer granularity. Unverified |
| Worker failure detection time | | |
| Autoscaler reaction time | | |
| Percentile error vs. raw logs | | |

## Open Questions

- What is the container ceiling at 1 CPU, and which fails first: the generator or the single-process target?
- Does aiohttp raise the per-worker ceiling over httpx? (Deferred)
- Is the baseline latency offset caused by Windows timer granularity?
- Will a smoothed schedule lag (p95 lag or share of late sends) work as an autoscaling signal, and at what threshold?
- Why is the published-port path so slow on Windows?
- Histogram format: fixed-bucket vs. HdrHistogram vs. t-digest?
- Autoscaler placement: inside the coordinator or a separate service?
- Redis Streams vs. pub/sub for worker commands?
- How to handle ramp profiles given container start-up lead time?

## Blockers / Bugs

*None.* (Fixed in Phase 2: `target.py` was missing the `/health` route.)

## Session Log

Add one entry per work session: what you did, what worked, what broke, and what's next.

### 2026-10-09
- Defined project scope and trimmed the stack for a beginner-friendly build.
- Wrote design doc v0.1 and this checkpoint file.
- Received Phase 1 code (`loadgen.py`, `target.py`, `requirements.txt`).

### 2026-10-11
- Ran Phase 1. Native 200 RPS on `localhost` could not hold its schedule; `127.0.0.1` improved it; sweep at 50 / 100 / 150 RPS was clean.
- Decided to stop tuning and move on. Updated docs to v0.2.

### Phase 2 (about 2026-10-11 to 2026-10-16)
- Containerized the generator and target; added Compose, healthcheck, `TARGET_URL`.
- Hit a failing healthcheck: `target.py` was missing `/health`. Added it; target became healthy.
- Ran experiments: containers held 100, 150, 200 RPS; open-loop proof passed (500 ms target, 100.1 RPS held); cap of 10 gave 38.3% 503s; native generator through the published port was far too slow.
- Found that max lag is noisy and the 50 ms warning is too sensitive; superseded the 120 RPS capacity number.
- Asked for a slow, plain-language walkthrough of everything so far; received it.
- Updated docs to v0.3 and added a README.
- **Next:** container ceiling sweep (300 / 400 / 600 RPS), then Phase 3.

---

## Files in this project

Repo layout:

```
distributed-load-tester/
├── docs/
│   ├── load-testing-platform-design.md
│   └── checkpoint.md
├── README.md
├── loadgen.py
├── target.py
├── requirements.txt
├── Dockerfile.target
├── Dockerfile.loadgen
├── docker-compose.yml
├── .dockerignore
└── .gitignore
```

| File | Purpose |
|------|---------|
| `README.md` | What the project is, current status, how to run it |
| `docs/load-testing-platform-design.md` | Architecture, decisions, failure modes, validation plan |
| `docs/checkpoint.md` | Progress tracking and session history (this file) |
| `loadgen.py` | Open-loop load generator (httpx, asyncio); target URL from `--url` or `TARGET_URL` |
| `target.py` | FastAPI target with tunable latency, error rate, concurrency cap, and `/health` |
| `requirements.txt` | `httpx`, `fastapi`, `uvicorn` |
| `Dockerfile.target`, `Dockerfile.loadgen` | Image recipes for the two services |
| `docker-compose.yml` | Runs the services together on a private network |
| `.dockerignore`, `.gitignore` | Files excluded from Docker builds and from Git |
