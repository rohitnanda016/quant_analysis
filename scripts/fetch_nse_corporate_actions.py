import argparse, json, time
from pathlib import Path
import requests
import pandas as pd

API = "https://www.nseindia.com/api/corporates-corporateActions"

def fetch_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131 Safari/537.36",
        "Accept":"application/json,text/plain,*/*",
        "Accept-Language":"en-US,en;q=0.9",
        "Referer":"https://www.nseindia.com/",
    })
    for _ in range(5):
        try:
            r=s.get("https://www.nseindia.com/",timeout=30)
            if r.ok: return s
        except Exception: pass
        time.sleep(2)
    raise RuntimeError("Could not establish NSE session")

def get_range(s,start,end):
    params={"index":"equities","from_date":start.strftime("%d-%m-%Y"),"to_date":end.strftime("%d-%m-%Y")}
    for attempt in range(5):
        try:
            r=s.get(API,params=params,timeout=60)
            if r.ok:
                obj=r.json()
                return pd.DataFrame(obj.get("data", obj if isinstance(obj,list) else []))
        except Exception:
            pass
        time.sleep(2**attempt)
    raise RuntimeError(f"NSE corporate-actions request failed for {start.date()}..{end.date()}")

p=argparse.ArgumentParser()
p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--out",required=True)
a=p.parse_args()
start,end=pd.Timestamp(a.start),pd.Timestamp(a.end)
s=fetch_session(); frames=[]; cur=start
while cur<=end:
    nxt=min(cur+pd.Timedelta(days=89),end)
    df=get_range(s,cur,nxt)
    if not df.empty: frames.append(df)
    cur=nxt+pd.Timedelta(days=1)
out=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
if not out.empty:
    out.columns=[str(c).strip().lower().replace(" ","_") for c in out.columns]
    out["symbol"]=out["symbol"].astype(str).str.upper().str.strip()
    out["ex_date"]=pd.to_datetime(out["ex_date"],errors="coerce")
    out=out.drop_duplicates().sort_values(["ex_date","symbol"],na_position="last")
Path(a.out).parent.mkdir(parents=True,exist_ok=True)
out.to_csv(a.out,index=False)
Path(a.out+".summary.json").write_text(json.dumps({"rows":int(len(out)),"start":str(start.date()),"end":str(end.date()),"source":API},indent=2))
print(json.dumps({"rows":int(len(out)),"out":a.out},indent=2))
