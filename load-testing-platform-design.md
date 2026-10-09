# Distributed Load Testing Platform: Design Document

**Status:** Draft v0.1
**Author:** Anshul
**Goal:** Learn system design by building a small distributed load generator with coordination, scaling, and metrics aggregation.

---

## 1. Overview

A platform that lets a user define a load test (target URL, request rate, duration), runs it across multiple containerized workers, scales the worker count automatically, and reports global latency and error metrics in near real time.

The project is intentionally small. Its purpose is to expose real distributed-systems problems (coordination, failure, aggregation, scaling) at a scale one laptop can run.

## 2. Goals and Non-Goals

### Goals
- Generate a configurable, open-loop request load against a target HTTP endpoint.
- Distribute that load across N worker containers.
- Aggregate metrics from all workers into correct global percentiles (p50/p95/p99).
- Autoscale the worker count based on required RPS and worker saturation.
- Detect and handle worker failure mid-test.
- Document every major design decision and its tradeoffs.

### Non-Goals
- Kubernetes deployment (stretch goal only).
- Multi-protocol support (HTTP only).
- Multi-tenant auth, billing, or a polished UI.
- Competing with k6, Locust, or Gatling.

## 3. Requirements

### Functional
| ID | Requirement |
|----|-------------|
| F1 | Create a test with target URL, method, headers, body, target RPS (or ramp profile), and duration. |
| F2 | Start, stop, and query a test run via an HTTP API. |
| F3 | Split the target RPS across available workers. |
| F4 | Start all workers at a synchronized timestamp. |
| F5 | Report live global throughput, error rate, and p50/p95/p99 latency. |
| F6 | Scale workers up or down during a run. |
| F7 | Mark a run as degraded or redistribute load if a worker dies. |

### Non-Functional
| ID | Requirement |
|----|-------------|
| N1 | Load generation must be open-loop (no coordinated omission). |
| N2 | Metrics must be mergeable across workers without losing percentile accuracy. |
| N3 | Metric reporting delay under ~2 seconds. |
| N4 | Runs on a single machine with `docker compose up`. |
| N5 | A worker or aggregator failure must not corrupt other workers' results. |

## 4. Tech Stack and Rationale

| Component | Choice | Why |
|-----------|--------|-----|
| Language | Python 3.11+ | Already known; asyncio is enough for the target scale. |
| Coordinator API | FastAPI | Quick to build, automatic docs, async-native. |
| Worker HTTP client | httpx or aiohttp | Async, supports connection pooling. |
| Coordination + metrics store | Redis | One dependency covers registry, pub/sub, streams, and aggregation. |
| Containers | Docker Compose | Scaling with `--scale` and the Docker SDK, with no Kubernetes learning cost. |
| Histograms | HdrHistogram (or fixed-bucket histogram) | Mergeable percentile data. |

**Tradeoff:** Redis is not a durable message queue or a real time-series DB. It is chosen for simplicity. See Section 12 for what changes at scale.

## 5. High-Level Architecture

```
                +-------------------+
   User/CLI --> |  API / Coordinator| <---- Autoscaler loop
                |     (FastAPI)     |            |
                +---------+---------+            | Docker SDK
                          |                      v
                          v              +---------------+
                     +---------+         |  Worker 1..N  |
                     |  Redis  | <-----> |  (containers) |
                     +---------+         +-------+-------+
                          ^                      |
                          |                      v
                  Aggregated metrics     +---------------+
                  (read by coordinator)  | Target service|
                                         +---------------+
```

### Components

1. **Coordinator (API service):** Owns test lifecycle. Creates runs, computes work shares, publishes start commands, serves live metrics.
2. **Workers:** Stateless containers. Register with Redis, send heartbeats, receive assignments, generate load, and push per-second histogram snapshots.
3. **Redis:** Worker registry, command channel, per-second metric buckets, run state.
4. **Autoscaler:** A loop (inside or beside the coordinator) that compares required vs. actual capacity and adds or removes worker containers.
5. **Target service:** A small FastAPI app with configurable artificial latency, random failure rate, and a concurrency cap. Used for demos and validation.

## 6. Data Model (Redis)

| Key | Type | Purpose |
|-----|------|---------|
| `workers:{id}` | Hash + TTL | Worker info (status, capacity, last heartbeat). TTL expiry means the worker is presumed dead. |
| `run:{run_id}` | Hash | Run config and state (`pending`, `running`, `degraded`, `done`, `failed`). |
| `run:{run_id}:assign` | Hash | `worker_id -> assigned RPS`. |
| `run:{run_id}:metrics:{second}` | Hash per worker | Serialized histogram plus request/error counts for that second. |
| `cmd:{worker_id}` | Stream or pub/sub | Commands: `start_at`, `stop`, `update_rps`. |

## 7. Key Flows

### 7.1 Starting a test
1. User calls `POST /runs` with test config.
2. Coordinator reads live workers from the registry, computes shares (`target_rps / n_workers`), and writes assignments.
3. Coordinator picks `start_at = now + 3s` and sends a `start` command to each worker. Workers wait until that timestamp (a simple barrier).
4. Workers begin generating load.

### 7.2 Metrics reporting
1. Each worker records latencies into a local histogram, rolled over every second.
2. At each second boundary, the worker writes `{histogram, count, errors}` to Redis keyed by run and second.
3. Coordinator merges all workers' histograms for a given second, producing global percentiles.
4. Live endpoint (`GET /runs/{id}/metrics`) returns the merged series.

### 7.3 Autoscaling
1. Autoscaler runs every few seconds.
2. `desired = ceil(target_rps / per_worker_capacity)`.
3. If `desired > current`, start containers via the Docker SDK. If lower, drain and stop extras.
4. Coordinator rebalances assignments after any change.

### 7.4 Worker failure
1. Worker TTL expires in Redis (missed heartbeats).
2. Coordinator detects the missing worker and applies the configured policy.
3. Policy options: **redistribute** the share across survivors, **mark degraded** and continue, or **abort**. Default: redistribute, then flag the run as degraded in the timeline.

## 8. Critical Design Decisions

### 8.1 Open-loop load generation
A closed-loop generator waits for each response before sending the next request, so it slows down exactly when the target slows down and hides the latency it should be measuring (coordinated omission).

**Decision:** Workers send requests on a fixed schedule independent of response time. Latency is measured from the *intended* send time.

### 8.2 Histograms instead of per-worker percentiles
Percentiles cannot be averaged. The p99 of combined data is not the mean of each worker's p99.

**Decision:** Workers send mergeable histograms. The coordinator merges them and computes percentiles from the merged result.

**Tradeoff:** Slightly larger metric payloads and bucket-resolution error, in exchange for correctness.

### 8.3 Scaling signal
**Decision:** Primary signal is required capacity (`target_rps / per_worker_capacity`). Secondary signal is worker CPU: above ~70%, mark the run as "load generator saturated" because results become unreliable.

**Tradeoff:** Requires measuring per-worker capacity up front. A purely reactive CPU-based scaler is simpler but reacts late and is less predictable.

### 8.4 Redis as the single coordination layer
**Decision:** Use Redis for registry, commands, and metrics.

**Tradeoff:** Fewer moving parts and faster build, but Redis is a single point of failure, and pub/sub does not guarantee delivery. Streams with acknowledgment improve this.

### 8.5 Synchronized start
**Decision:** Coordinator sends an absolute `start_at` timestamp rather than "start now."

**Tradeoff:** Depends on reasonably aligned clocks. Containers on one host share a clock, so this is fine locally. Across machines, NTP skew would matter.

## 9. Failure Modes and Handling

| Failure | Detection | Response |
|---------|-----------|----------|
| Worker crashes mid-test | Heartbeat TTL expiry | Redistribute load, mark run degraded |
| Worker too slow (saturated) | CPU > threshold, achieved RPS < assigned RPS | Scale up; flag results if unresolved |
| Redis unavailable | Connection errors | Workers buffer metrics locally for a limited time, then drop with a counter |
| Aggregator/coordinator slow | Metric backlog grows | Drop or coarsen oldest buckets; never block load generation |
| Target service fails completely | Error rate near 100% | Continue and report; optional circuit-breaker to stop the run |
| Duplicate start command | Run state check | Commands are idempotent per `run_id` |

**Principle:** Load generation must never block on metrics. Losing a metric is acceptable; distorting the load is not.

## 10. Bottlenecks in the Load Generator Itself

Things to measure and document during development:
- **Ephemeral ports:** limits concurrent outbound connections per worker.
- **File descriptors:** `ulimit -n` caps open sockets.
- **Connection pooling/keep-alive:** affects achievable RPS and realism.
- **Python event loop saturation:** one worker has a ceiling; this is why horizontal scaling matters.
- **Docker networking overhead** on the local machine.

Record the measured per-worker RPS ceiling. The autoscaler depends on it.

## 11. Implementation Plan

| Phase | Deliverable | Est. time |
|-------|-------------|-----------|
| 1 | Single open-loop async load generator with latency recording | 2-3 days |
| 2 | Dockerize generator; build target service with tunable latency/errors/capacity | 1-2 days |
| 3 | Coordinator + multiple workers: registry, heartbeats, assignments, synchronized start | 3-4 days |
| 4 | Histogram-based metric aggregation and live global percentiles | 2-3 days |
| 5 | Autoscaler using the Docker SDK | 2 days |
| 6 | Failure injection (kill workers mid-run) and handling policy | 1-2 days |
| 7 | Final design doc update, diagrams, results | 1-2 days |

**Stretch goals:** Grafana dashboard, ramp profiles (step/spike), Kubernetes with HPA or KEDA, persistent run history.

## 12. Scaling Beyond This Design (What Changes at 100x)

| Current choice | Limitation | At scale |
|----------------|------------|----------|
| Single Redis | SPOF, memory-bound, weak delivery guarantees | Kafka or NATS JetStream for commands and metrics; Redis only for ephemeral state |
| Coordinator merges histograms | Becomes a CPU and network bottleneck | Hierarchical aggregation (regional aggregators merge first) |
| Docker SDK autoscaling | Single host | Kubernetes with HPA/KEDA, node autoscaling |
| Clock sync by shared host | Skew across machines | NTP/PTP, or a coordinator-driven "go" signal with tolerance |
| Metrics stored in Redis | Short-lived, no history | Time-series DB (Prometheus, TimescaleDB, ClickHouse) |
| Single coordinator | SPOF | Leader election, replicated state in Postgres or etcd |
| One target endpoint | Limited realism | Scenarios, correlated multi-step flows, data feeders |

## 13. Validation Plan

- **Correctness of percentiles:** Compare merged-histogram p99 against p99 computed from raw latency logs on a small run.
- **Open-loop check:** Slow the target deliberately; confirm the generated RPS stays constant and reported latency rises.
- **Scaling test:** Ramp from 100 to 5,000+ RPS and verify the worker count follows the target.
- **Chaos test:** Kill 1, then 2 workers mid-run; verify detection time and recovery behavior.
- **Saturation test:** Push one worker past its ceiling; verify the "generator saturated" flag fires.

## 14. Demo Scenario

1. Start the platform with `docker compose up`.
2. Launch a test ramping from 100 to 5,000 RPS against the target service.
3. Watch workers scale up as the ramp progresses.
4. Watch the target's latency climb and errors appear as it hits its concurrency cap.
5. Kill a worker; observe redistribution and the degraded flag.
6. Show final merged p50/p95/p99 and the timeline.

## 15. Open Questions

- What per-worker RPS ceiling is realistic with httpx vs. aiohttp?
- Fixed-bucket histogram vs. HdrHistogram vs. t-digest for the metric payload?
- Should the autoscaler live inside the coordinator or run as its own service?
- How should ramp profiles interact with scaling lead time (containers take seconds to start)?
- Redis Streams vs. pub/sub for worker commands?

## 16. References to Study

- Gil Tene, "How NOT to Measure Latency" (coordinated omission)
- HdrHistogram documentation
- Designing Data-Intensive Applications (Kleppmann): chapters on replication, partitioning, and stream processing
- Docker SDK for Python documentation
- Redis Streams documentation

---

*Update this document as decisions change. Record measured numbers in Section 10 and test results in Section 13.*
