"""Minimal deployed-service smoke/performance probe."""
import os, statistics, time, urllib.request
base=os.environ.get("DINA_BASE_URL","").rstrip("/")
token=os.environ.get("DINA_TOKEN","")
if not base or not token:
    raise SystemExit("DINA_BASE_URL and DINA_TOKEN are required")
samples=[]
for path in ("/health/live","/health/ready"):
    req=urllib.request.Request(base+path,headers={"Authorization":"Bearer "+token})
    t=time.perf_counter()
    with urllib.request.urlopen(req,timeout=10) as response:
        if response.status != 200: raise SystemExit(f"{path}: HTTP {response.status}")
    samples.append((path,(time.perf_counter()-t)*1000))
print("health latency ms:",samples)
print("p50 ms:",statistics.median(v for _,v in samples))
