"""
target.py - a small service to load test against.
 
You control how it misbehaves with environment variables:
    LATENCY_MS       base response time in milliseconds   (default 50)
    ERROR_RATE       fraction of requests that fail, 0-1  (default 0)
    MAX_CONCURRENCY  max requests in flight at once       (default 100)
                     Above this it returns 503 immediately (load shedding).
 
Run:
    uvicorn target:app --port 8000
    LATENCY_MS=300 ERROR_RATE=0.05 uvicorn target:app --port 8000
"""
import asyncio
import os
import random
 
from fastapi import FastAPI, HTTPException

LATENCY_MS = float(os.getenv("LATENCY_MS", "50"))
ERROR_RATE = float(os.getenv("ERROR_RATE", "0"))
MAX_CONCURRENCY = int(os.getenv("MAX_CONCURRENCY", "100"))
 
app = FastAPI()
inflight = 0  # how many requests are being handled right now
 
 
@app.get("/work")
async def work():
    global inflight
 
    # Over capacity: reject right away instead of queueing. This is how real
    # services protect themselves, and it gives you 503s to look at.
    if inflight >= MAX_CONCURRENCY:
        raise HTTPException(status_code=503, detail="overloaded")
 
    inflight += 1
    try:
        # Simulate work: base latency plus +/-20% random jitter.
        await asyncio.sleep(LATENCY_MS / 1000 * random.uniform(0.8, 1.2))
        if random.random() < ERROR_RATE:
            raise HTTPException(status_code=500, detail="random failure")
        return {"ok": True}
    finally:
        inflight -= 1

@app.get("/health")
async def health():
    return {"status": "up"}