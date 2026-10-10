import argparse, json, time
from pathlib import Path
import pandas as pd
from download_stage_a import get_chunk

p=argparse.ArgumentParser(description="Repair verified held-symbol price gaps from NSE daily history.")
p.add_argument("--prices", required=True)
p.add_argument("--out", required=True)
p.add_argument("--sleep", type=float, default=1.0)
a=p.parse_args()

base=pd.read_csv(a.prices, low_memory=False)
base["date"]=pd.to_datetime(base["date"], errors="coerce")
base["symbol"]=base["symbol"].astype(str).str.strip().str.upper()

# Windows bracket the two reproducible held-symbol failures. Replacing matching
# date/symbol rows with NSE archive observations also repairs rows whose close
# was present but null/corrupt in the source dataset.
windows=[
    ("IIFL", pd.Timestamp("2017-08-01"), pd.Timestamp("2017-12-31")),
    ("IBVENTURES", pd.Timestamp("2018-06-01"), pd.Timestamp("2018-11-15")),
]
parts=[base]
report=[]
for symbol,start,end in windows:
    cur=start
    while cur<=end:
        stop=min(cur+pd.Timedelta(days=59),end)
        frame,error=get_chunk(symbol,cur,stop,retries=4)
        if frame is None or frame.empty:
            report.append({"symbol":symbol,"start":str(cur.date()),"end":str(stop.date()),
                           "status":"no_rows","error":str(error)})
        else:
            frame["requested_symbol"]=symbol
            frame["source_symbol"]=symbol
            parts.append(frame)
            report.append({"symbol":symbol,"start":str(cur.date()),"end":str(stop.date()),
                           "status":"fetched","rows":int(len(frame))})
        cur=stop+pd.Timedelta(days=1)
        time.sleep(a.sleep)

merged=pd.concat(parts,ignore_index=True,sort=False)
# Base is first, fetched authoritative NSE rows are appended last.
merged=merged.dropna(subset=["date","symbol"]).drop_duplicates(["date","symbol"],keep="last")
merged=merged.sort_values(["date","symbol"])
out=Path(a.out); out.parent.mkdir(parents=True,exist_ok=True)
merged.to_csv(out,index=False)
summary={"base_rows":int(len(base)),"final_rows":int(len(merged)),
         "rows_added":int(len(merged)-len(base)),"windows":report,
         "note":"Fetched NSE archive rows supersede original rows for matching date/symbol. This repair is limited to documented held-symbol gap windows."}
out.with_suffix(".repair.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
if not any(x["status"]=="fetched" for x in report):
    raise SystemExit("No NSE observations fetched; refusing to publish a repaired dataset")
