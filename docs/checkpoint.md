# Checkpoint: Distributed Load Testing Platform

**Last updated:** 2026-10-11
**Current phase:** Phase 1 complete. Phase 2 (Dockerize + target service) not started.
**Next action:** Put `loadgen.py` and `target.py` in Docker containers and run them together with Docker Compose.

---

## How to resume with Claude

Paste or upload this file at the start of a new conversation, along with `load-testing-platform-design.md` if the design matters for the task, and `loadgen.py` / `target.py` if the code matters. Then say which phase you're on and what you're stuck on. Update this file at the end of each work session.

---

## Project Summary

A distributed load testing platform built to learn system design. Workers generate open-loop HTTP load, a coordinator splits and synchronizes the work, metrics are aggregated using mergeable histograms, and an autoscaler adjusts the worker count.

**Developer background:** Beginner with Docker and Kubernetes; has not used Go. Wants to understand every piece of code, so explanations matter as much as the code. Develops on Windows (PowerShell, venv).

## Stack (decided)

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ (asyncio) |
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
- [x] Design doc written (`load-testing-platform-design.md`, now v0.2)
- [x] Checkpoint file created

### Implementation
- [x] **Phase 1:** Single open-loop async load generator with latency recording (`loadgen.py`, plus `target.py` used as the test target)
- [ ] **Phase 2:** Dockerize generator and target; tunable latency, error rate, and concurrency cap (target service code already exists; needs Dockerfiles + Compose) (est. 1-2 days)
- [ ] **Phase 3:** Coordinator + multiple workers: registry, heartbeats, assignments, synchronized start (est. 3-4 days)
- [ ] **Phase 4:** Histogram-based metric aggregation and live global percentiles (est. 2-3 days)
- [ ] **Phase 5:** Autoscaler using the Docker SDK (est. 2 days)
- [ ] **Phase 6:** Failure injection and handling policy (est. 1-2 days)
- [ ] **Phase 7:** Update design doc with results, diagrams, and final tradeoffs (est. 1-2 days)

### Optional Phase 1 follow-ups (deferred, not blocking)
- [ ] Pin the ceiling more precisely (try 175 RPS)
- [ ] Check CPU in Task Manager during a 200 RPS run (is `loadgen.py` pinned at one core?)
- [ ] Try the Windows selector event loop policy (`WindowsSelectorEventLoopPolicy`)
- [ ] Compare against an aiohttp version of `fire()`
- [ ] Run the open-loop proof: restart the target with `LATENCY_MS=500` and confirm achieved RPS stays near target while latency rises
- [ ] Run the concurrency-cap test: `MAX_CONCURRENCY=10 LATENCY_MS=100` at 500 RPS, expect many 503s

### Stretch goals
- [ ] Grafana dashboard
- [ ] Ramp profiles (step, spike)
- [ ] Kubernetes with HPA or KEDA
- [ ] Persistent run history

## Findings So Far

1. **Open-loop measurement caught real saturation.** Because latency is measured from the intended send time, the 200 RPS run exposed that the generator, not the target, was the bottleneck. A closed-loop tool would have hidden this.
2. **Single-worker behavior has a cliff, not a slope.** Schedule lag was 0 / 12 / 26 ms at 50 / 100 / 150 RPS, then 2,097 ms at 200 RPS. Likely feedback loop (falling behind causes bursts, bursts cost CPU, which causes more lag). The mechanism is a hypothesis, not confirmed.
3. **On Windows, use `127.0.0.1`, not `localhost`.** Switching improved the 200 RPS run from 109 to 165 achieved RPS and cut max lag from 8.3 s to 2.1 s. Likely cause: IPv6-first resolution against an IPv4-only server (not directly verified).
4. **Schedule lag is a candidate autoscaling signal.** It rose before anything visibly broke. Hypothesis to test in Phase 5: scale up when per-worker max lag crosses a threshold, instead of waiting for CPU.
5. **The target is a single process,** so at higher aggregate RPS it will saturate too. Later, distinguish "generator saturated" from "target saturated" before trusting results.

## Decisions Log

Record each decision with the date, the options considered, and the reason.

| Date | Decision | Alternatives considered | Reason |
|------|----------|------------------------|--------|
| 2026-10-09 | Python instead of Go | Go | Avoid learning a new language alongside system design |
| 2026-10-09 | Docker Compose instead of Kubernetes | Kubernetes (kind/minikube) | Avoid orchestration learning curve; `--scale` is enough |
| 2026-10-09 | Redis as single coordination layer | Message queue + separate DB | Fewer dependencies; revisit at scale (see design doc Section 12) |
| 2026-10-09 | Open-loop load model | Closed-loop | Avoid coordinated omission |
| 2026-10-09 | Mergeable histograms for metrics | Per-worker percentiles | Percentiles cannot be averaged |
| 2026-10-11 | Use `127.0.0.1`, not `localhost`, for local targets on Windows | `localhost` | 109 to 165 achieved RPS at 200 RPS target; lag 8.3 s to 2.1 s |
| 2026-10-11 | Stop tuning the single worker and move on to Phase 2 | Keep optimizing (aiohttp, selector loop) | ~150 RPS per worker is enough; a lower ceiling makes the autoscaling demo more visible. Optimizations deferred |
| 2026-10-11 | Provisional `per_worker_capacity` = 120 RPS | Using the raw ~150 ceiling | About 80% of the measured clean ceiling, to leave headroom. Revisit after Docker runs, since container CPU limits will change it |

## Measured Results

Environment: Windows laptop, Python venv, httpx client, target on the same machine (shared CPU), target at 50 ms nominal latency, 0% errors.

### Phase 1 run log

| Client URL | Target RPS | Achieved send RPS | Max lag | p50 | p95 | p99 | Valid? |
|-----------|-----------|-------------------|---------|-----|-----|-----|--------|
| `localhost` | 200 | 109.3 | 8,298 ms | 5,460 ms | 8,952 ms | 9,837 ms | No (generator behind) |
| `127.0.0.1` | 200 | 165.3 | 2,097 ms | 704 ms | 3,158 ms | 4,005 ms | No (generator behind) |
| `127.0.0.1` | 50 | 50.1 | 0 ms | 69 ms | 79 ms | 81 ms | Yes |
| `127.0.0.1` | 100 | 100.1 | 12 ms | 67 ms | 78 ms | 79 ms | Yes |
| `127.0.0.1` | 150 | 150.0 | 26 ms | 66 ms | 80 ms | 84 ms | Yes |

### Summary table

| Metric | Value | Date | Notes |
|--------|-------|------|-------|
| Max clean RPS per worker (httpx, Windows, shared CPU) | ~150 (fails by 200) | 2026-10-11 | Ceiling is between 150 and ~180 |
| Max RPS per worker (aiohttp) | Not tested | | Deferred |
| Baseline latency vs. nominal | p50 ~67 ms vs. 50 ms nominal | 2026-10-11 | Unexplained. Hypothesis: Windows timer granularity in the target's `asyncio.sleep`. Unverified |
| Worker failure detection time | | | |
| Autoscaler reaction time | | | |
| Percentile error vs. raw logs | | | |

## Open Questions

- Does aiohttp raise the per-worker ceiling over httpx? (Deferred, not blocking)
- Is the 20 ms extra baseline latency from Windows timer granularity, or from HTTP overhead?
- Is the feedback-loop explanation for the cliff correct? What is the exact ceiling between 150 and 200?
- Will per-worker schedule lag work as a leading autoscaling signal, and at what threshold?
- Histogram format: fixed-bucket vs. HdrHistogram vs. t-digest?
- Autoscaler placement: inside the coordinator or a separate service?
- Redis Streams vs. pub/sub for worker commands?
- How to handle ramp profiles given container start-up lead time?
- How will container CPU limits change the per-worker ceiling?

## Blockers / Bugs

*None.*

## Session Log

Add one entry per work session: what you did, what worked, what broke, and what's next.

### 2026-10-09
- Defined project scope and trimmed the stack for a beginner-friendly build.
- Wrote design doc v0.1 and this checkpoint file.
- Received Phase 1 code (`loadgen.py`, `target.py`, `requirements.txt`).
- **Next:** Run Phase 1.

### 2026-10-11
- Ran Phase 1. First 200 RPS run on `localhost` could not hold its schedule (109 achieved RPS, 8.3 s lag).
- Switched to `127.0.0.1`: improved to 165 RPS, 2.1 s lag, still behind.
- Ran a sweep at 50 / 100 / 150 RPS: all clean. Single-worker ceiling is about 150 RPS on this laptop.
- Decided to stop tuning and move on. Updated this file and the design doc (v0.2).
- **Next:** Phase 2, containerize the generator and target with Docker Compose.

---

## Files in this project

Suggested repo layout:

```
distributed-load-tester/
├── docs/
│   ├── load-testing-platform-design.md
│   └── checkpoint.md
├── loadgen.py
├── target.py
└── requirements.txt
```

| File | Purpose |
|------|---------|
| `load-testing-platform-design.md` | Architecture, decisions, failure modes, validation plan |
| `checkpoint.md` | Progress tracking and session history (this file) |
| `loadgen.py` | Phase 1 open-loop load generator (httpx, asyncio) |
| `target.py` | FastAPI target with tunable latency, error rate, concurrency cap |
| `requirements.txt` | `httpx`, `fastapi`, `uvicorn` |
