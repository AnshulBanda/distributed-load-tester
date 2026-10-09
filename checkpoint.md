# Checkpoint: Distributed Load Testing Platform

**Last updated:** 2026-10-09
**Current phase:** Pre-Phase 1 (design complete, no code written yet)
**Next action:** Build the Phase 1 open-loop async load generator

---

## How to resume with Claude

Paste or upload this file at the start of a new conversation, along with `load-testing-platform-design.md` if the design matters for the task. Then say which phase you're on and what you're stuck on. Update this file at the end of each work session.

---

## Project Summary

A distributed load testing platform built to learn system design. Workers generate open-loop HTTP load, a coordinator splits and synchronizes the work, metrics are aggregated using mergeable histograms, and an autoscaler adjusts the worker count.

**Developer background:** Beginner with Docker and Kubernetes; has not used Go. Strong preference for fast progress and learning system design over learning new tooling.

## Stack (decided)

| Layer | Choice |
|-------|--------|
| Language | Python 3.11+ (asyncio) |
| Coordinator API | FastAPI |
| HTTP client | httpx or aiohttp (undecided) |
| Coordination + metrics | Redis |
| Containers | Docker Compose only (Kubernetes is a stretch goal) |
| Histograms | HdrHistogram or fixed-bucket (undecided) |
| Dashboards | None at first; Grafana is a stretch goal |

## Progress

Legend: `[ ]` not started, `[~]` in progress, `[x]` done

### Planning
- [x] Project idea and scope defined
- [x] Stack trimmed to Python + Docker Compose + Redis
- [x] Design doc written (`load-testing-platform-design.md`, v0.1)
- [x] Checkpoint file created

### Implementation
- [ ] **Phase 1:** Single open-loop async load generator with latency recording (est. 2-3 days)
- [ ] **Phase 2:** Dockerize generator; build target service with tunable latency, error rate, and concurrency cap (est. 1-2 days)
- [ ] **Phase 3:** Coordinator + multiple workers: registry, heartbeats, assignments, synchronized start (est. 3-4 days)
- [ ] **Phase 4:** Histogram-based metric aggregation and live global percentiles (est. 2-3 days)
- [ ] **Phase 5:** Autoscaler using the Docker SDK (est. 2 days)
- [ ] **Phase 6:** Failure injection and handling policy (est. 1-2 days)
- [ ] **Phase 7:** Update design doc with results, diagrams, and final tradeoffs (est. 1-2 days)

### Stretch goals
- [ ] Grafana dashboard
- [ ] Ramp profiles (step, spike)
- [ ] Kubernetes with HPA or KEDA
- [ ] Persistent run history

## Decisions Log

Record each decision with the date, the options considered, and the reason.

| Date | Decision | Alternatives considered | Reason |
|------|----------|------------------------|--------|
| 2026-10-09 | Python instead of Go | Go | Avoid learning a new language alongside system design |
| 2026-10-09 | Docker Compose instead of Kubernetes | Kubernetes (kind/minikube) | Avoid orchestration learning curve; `--scale` is enough |
| 2026-10-09 | Redis as single coordination layer | Message queue + separate DB | Fewer dependencies; revisit at scale (see design doc Section 12) |
| 2026-10-09 | Open-loop load model | Closed-loop | Avoid coordinated omission |
| 2026-10-09 | Mergeable histograms for metrics | Per-worker percentiles | Percentiles cannot be averaged |

## Measured Results

Fill these in as you build. They feed Sections 10 and 13 of the design doc.

| Metric | Value | Date | Notes |
|--------|-------|------|-------|
| Max RPS per worker (httpx) | | | |
| Max RPS per worker (aiohttp) | | | |
| Worker failure detection time | | | |
| Autoscaler reaction time | | | |
| Percentile error vs. raw logs | | | |

## Open Questions

- httpx vs. aiohttp: which gives the higher per-worker ceiling?
- Histogram format: fixed-bucket vs. HdrHistogram vs. t-digest?
- Autoscaler placement: inside the coordinator or a separate service?
- Redis Streams vs. pub/sub for worker commands?
- How to handle ramp profiles given container start-up lead time?

## Blockers / Bugs

*None yet.*

## Session Log

Add one entry per work session: what you did, what worked, what broke, and what's next.

### 2026-10-09
- Defined project scope and trimmed the stack for a beginner-friendly build.
- Wrote design doc v0.1 and this checkpoint file.
- **Next:** Start Phase 1 (open-loop load generator).

---

## Files in this project

| File | Purpose |
|------|---------|
| `load-testing-platform-design.md` | Architecture, decisions, failure modes, validation plan |
| `checkpoint.md` | Progress tracking and session history (this file) |
