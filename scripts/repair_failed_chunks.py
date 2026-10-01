import argparse, json, time
from pathlib import Path
import pandas as pd
from download_stage_a import get_chunk

p = argparse.ArgumentParser(description="Repair explicitly failed historical NSE chunks.")
p.add_argument("--prices", required=True)
p.add_argument("--out", required=True)
p.add_argument("--start", required=True)
p.add_argument("--end", required=True)
p.add_argument("--symbols", required=True)
p.add_argument("--chunk-days", type=int, default=365)
p.add_argument("--sleep", type=float, default=3.0)
p.add_argument("--retries", type=int, default=4)
a = p.parse_args()

base = pd.read_csv(a.prices, low_memory=False)
base["date"] = pd.to_datetime(base["date"], errors="coerce")
base["symbol"] = base["symbol"].astype(str).str.strip().str.upper()

start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
symbols = [s.strip().upper() for s in a.symbols.split(",") if s.strip()]
parts, results = [base], []

for sym in symbols:
    cur = start
    while cur <= end:
        chunk_end = min(cur + pd.Timedelta(days=a.chunk_days - 1), end)
        repaired = False
        last_error = None
        for attempt in range(1, a.retries + 2):
            try:
                d, last_error = get_chunk(sym, cur, chunk_end, retries=1)
                if len(d):
                    d["requested_symbol"] = sym
                    d["source_symbol"] = sym
                    parts.append(d)
                    results.append({"symbol": sym, "chunk_start": str(cur.date()), "chunk_end": str(chunk_end.date()),
                                    "status": "repaired", "rows": len(d), "attempt": attempt})
                    repaired = True
                    break
            except Exception as exc:
                last_error = str(exc)
            if attempt <= a.retries:
                time.sleep(min(90, 5 * (2 ** (attempt - 1))))
        if not repaired:
            results.append({"symbol": sym, "chunk_start": str(cur.date()), "chunk_end": str(chunk_end.date()),
                            "status": "failed", "rows": 0, "error": str(last_error)})
        time.sleep(a.sleep)
        cur = chunk_end + pd.Timedelta(days=1)

out = pd.concat(parts, ignore_index=True)
out = out.dropna(subset=["date", "symbol"]).drop_duplicates(["date", "symbol"]).sort_values(["date", "symbol"])
Path(a.out).parent.mkdir(parents=True, exist_ok=True)
out.to_csv(a.out, index=False)
summary = {"base_rows": len(base), "final_rows": len(out), "symbols": symbols,
           "chunks": len(results), "repaired_chunks": sum(x["status"] == "repaired" for x in results),
           "remaining_failed_chunks": sum(x["status"] == "failed" for x in results), "results": results}
Path(a.out).with_suffix(".repair.json").write_text(json.dumps(summary, indent=2))
print(json.dumps({k: v for k, v in summary.items() if k != "results"}, indent=2))
