import argparse, json, time
from pathlib import Path
import pandas as pd
from download_stage_a import get_chunk

p=argparse.ArgumentParser()
p.add_argument("--prices", required=True)
p.add_argument("--audit", required=True)
p.add_argument("--out", required=True)
p.add_argument("--sleep", type=float, default=3.0)
p.add_argument("--retries", type=int, default=4)
a=p.parse_args()

base=pd.read_csv(a.prices, low_memory=False)
base["date"]=pd.to_datetime(base["date"], errors="coerce")
base["symbol"]=base["symbol"].astype(str).str.strip().str.upper()

audit=json.loads(Path(a.audit).read_text())
failed=audit.get("failure_examples", [])

if not failed:
    base.to_csv(a.out,index=False)
    print(json.dumps({"status":"nothing_to_repair","rows":len(base),"symbols":int(base.symbol.nunique())},indent=2))
    raise SystemExit(0)

parts=[base]
results=[]
for n,item in enumerate(failed,1):
    sym=str(item["symbol"]).upper()
    a0=pd.Timestamp(item["chunk_start"])
    b0=pd.Timestamp(item["chunk_end"])
    repaired=False
    last_error=None
    for attempt in range(a.retries+1):
        d,last_error=get_chunk(sym,a0,b0,retries=1)
        if len(d):
            d["requested_symbol"]=sym
            d["source_symbol"]=sym
            parts.append(d)
            results.append({**item,"status":"repaired","rows":len(d),"attempt":attempt+1})
            repaired=True
            break
        time.sleep(min(90,5*(2**attempt)))
    if not repaired:
        results.append({**item,"status":"failed","rows":0,"error":last_error})
    if n % 5 == 0 or n == len(failed):
        print(f"repair {n}/{len(failed)} repaired={sum(x['status']=='repaired' for x in results)}",flush=True)
    time.sleep(a.sleep)

out=pd.concat(parts,ignore_index=True)
out=out.dropna(subset=["date","symbol"]).drop_duplicates(["date","symbol"]).sort_values(["date","symbol"])
Path(a.out).parent.mkdir(parents=True,exist_ok=True)
out.to_csv(a.out,index=False)
Path(a.out).with_suffix(".repair.json").write_text(json.dumps({
    "base_rows":len(base),"final_rows":len(out),"failed_chunks":len(failed),
    "repaired_chunks":sum(x["status"]=="repaired" for x in results),
    "remaining_failed_chunks":sum(x["status"]=="failed" for x in results),
    "results":results
},indent=2))
print(json.dumps({
    "base_rows":len(base),"final_rows":len(out),
    "repaired_chunks":sum(x["status"]=="repaired" for x in results),
    "remaining_failed_chunks":sum(x["status"]=="failed" for x in results)
},indent=2))
