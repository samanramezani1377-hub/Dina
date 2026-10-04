"""Smoke check for a running Dina backend used by the Codespaces E2E workflow."""

import os
import statistics
import time
import urllib.request

base = os.environ.get("DINA_BASE_URL", "").strip().rstrip("/")
if not base:
    raise SystemExit("DINA_BASE_URL is required")
if not base.startswith("https://"):
    raise SystemExit("DINA_BASE_URL must be an HTTPS URL")

samples = []
for path in ("/health/live", "/health/ready"):
    request = urllib.request.Request(base + path, headers={"Accept": "application/json"})
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status != 200:
                raise SystemExit(f"{path}: HTTP {response.status}")
    except Exception as exc:
        raise SystemExit(f"{path}: backend is not reachable: {exc}") from exc
    samples.append((path, (time.perf_counter() - started) * 1000))

print("Dina backend:", base)
print("health latency ms:", samples)
print("p50 ms:", statistics.median(value for _, value in samples))
