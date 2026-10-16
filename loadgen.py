"""
loadgen.py - Phase 1: a single open-loop HTTP load generator.

"Open-loop" means requests are sent on a fixed schedule (e.g. one every 5 ms
for 200 RPS) NO MATTER how slow the target responds. A closed-loop generator
waits for each response before sending the next request, so when the target
slows down the generator silently slows down too, and the latency you
measure looks better than reality (this is "coordinated omission").

Usage:
    python loadgen.py --url http://localhost:8000/work --rps 200 --duration 10
"""
import argparse
import asyncio
import os
import time
from collections import Counter

import httpx


async def fire(client, url, intended_start, timeout, results):
    """Send ONE request and record how long it took.

    Latency is measured from the time the request was SUPPOSED to start
    (intended_start), not from when we actually sent it. If our own event
    loop falls behind schedule, that delay counts against latency instead
    of being hidden.
    """
    try:
        resp = await client.get(url, timeout=timeout)
        status = resp.status_code
        is_error = status >= 400
    except httpx.HTTPError as exc:
        # Timeouts, connection refused, pool exhaustion, etc.
        status = type(exc).__name__
        is_error = True
    latency = time.perf_counter() - intended_start
    results.append((latency, status, is_error))


async def run(url, rps, duration, timeout):
    total = int(rps * duration)  # how many requests we will send in total
    interval = 1.0 / rps  # gap between scheduled sends, in seconds
    results = []  # filled in by fire(): (latency, status, is_error)
    tasks = []
    max_lag = 0.0  # worst case of "how late were we vs. the schedule"

    # Allow lots of simultaneous connections so the client itself doesn't
    # become the limit. Reusing connections (keep-alive) is also much cheaper
    # than opening a new TCP connection per request.
    limits = httpx.Limits(max_connections=2000, max_keepalive_connections=2000)

    async with httpx.AsyncClient(limits=limits) as client:
        start = time.perf_counter()

        for i in range(total):
            # The i-th request has a fixed intended time, calculated from the
            # start. We never compute it from "now", so errors don't drift.
            intended = start + i * interval

            delay = intended - time.perf_counter()
            if delay > 0:
                await asyncio.sleep(delay)  # wait until it's time
            else:
                # We're behind schedule. Record how far behind, then yield
                # to the event loop so already-created tasks can make progress.
                max_lag = max(max_lag, -delay)
                await asyncio.sleep(0)

            # create_task starts the request in the background and returns
            # immediately. THIS is what makes the loop open: we do not wait
            # for the response before scheduling the next request.
            tasks.append(
                asyncio.create_task(fire(client, url, intended, timeout, results))
            )

        send_elapsed = time.perf_counter() - start

        # Only now do we wait for all in-flight requests to finish.
        await asyncio.gather(*tasks)

    return results, send_elapsed, max_lag


def percentile(sorted_values, p):
    """Nearest-rank percentile of an already-sorted list."""
    if not sorted_values:
        return 0.0
    idx = min(len(sorted_values) - 1, round(p / 100 * (len(sorted_values) - 1)))
    return sorted_values[idx]


def report(results, send_elapsed, max_lag, target_rps):
    latencies = sorted(r[0] for r in results)
    errors = sum(1 for r in results if r[2])
    statuses = Counter(r[1] for r in results)
    n = len(results)

    print("\n=== Results ===")
    print(f"Requests sent:     {n}")
    print(f"Target RPS:        {target_rps}")
    print(f"Achieved send RPS: {n / send_elapsed:.1f}")
    print(f"Errors:            {errors} ({100 * errors / n:.1f}%)")
    print(f"Status counts:     {dict(statuses)}")
    print("Latency (ms):")
    print(f"  p50 {percentile(latencies, 50) * 1000:8.1f}")
    print(f"  p95 {percentile(latencies, 95) * 1000:8.1f}")
    print(f"  p99 {percentile(latencies, 99) * 1000:8.1f}")
    print(f"  max {latencies[-1] * 1000:8.1f}")
    print(f"Max schedule lag:  {max_lag * 1000:.1f} ms")
    if max_lag > 0.05:
        print(
            "WARNING: the generator fell behind its own schedule. "
            "Results are unreliable: this machine/process is the bottleneck, "
            "not the target."
        )


def main():
    parser = argparse.ArgumentParser(description="Open-loop HTTP load generator")
    # In Docker we pass the target via the TARGET_URL environment variable,
    # so the container needs no extra arguments for it. --url still works.
    parser.add_argument("--url", default=os.getenv("TARGET_URL"),
                        help="target URL (or set the TARGET_URL env var)")
    parser.add_argument("--rps", type=float, default=100, help="requests per second")
    parser.add_argument("--duration", type=float, default=10, help="seconds")
    parser.add_argument("--timeout", type=float, default=5, help="per-request timeout (s)")
    args = parser.parse_args()
    if not args.url:
        parser.error("--url is required (or set TARGET_URL)")

    print(f"Sending {args.rps} RPS for {args.duration}s to {args.url} ...")
    results, send_elapsed, max_lag = asyncio.run(
        run(args.url, args.rps, args.duration, args.timeout)
    )
    report(results, send_elapsed, max_lag, args.rps)


if __name__ == "__main__":
    main()
