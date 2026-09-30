import argparse, io, json, time
from pathlib import Path
import pandas as pd, requests

FLAGGED = ["ALOKINDS","JSWENERGY","FLUOROCHEM","TRIDENT","TTML","BCG","ATGL","ADANITRANS","ADANIENSOL","HAPPSTMNDS","SUPPETRO","CGPOWER","NAZARA"]
URL = "https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData"

def clean(c):
    c=str(c).replace("\ufeff","").replace("\xa0"," ").strip().strip('"')
    return " ".join(c.split()).lower()

MAP={"symbol":"symbol","series":"series","date":"date","prev close":"prev_close",
"open price":"open","high price":"high","low price":"low","last price":"last",
"close price":"close","average price":"vwap","total traded quantity":"volume",
"turnover":"traded_value","no. of trades":"num_trades","deliverable qty":"deliverable_qty",
"% dly qt to traded qty":"deliverable_pct"}

def fetch(s, sym, a, b):
    p={"symbol":sym,"from":a.strftime("%d-%m-%Y"),"to":b.strftime("%d-%m-%Y"),
       "series":"EQ","type":"priceVolumeDeliverable","csv":"true","dataType":"priceVolumeDeliverable"}
    for attempt in range(4):
        try:
            r=s.get(URL,params=p,timeout=60)
            if r.status_code==200 and len(r.content)>100:
                d=pd.read_csv(io.StringIO(r.content.decode("utf-8-sig",errors="replace")),skipinitialspace=True)
                d.columns=[clean(c) for c in d.columns]
                d=d.rename(columns=MAP)
                if "date" not in d or "close" not in d: return pd.DataFrame()
                d["date"]=pd.to_datetime(d["date"],errors="coerce",dayfirst=True)
                d["symbol"]=d["symbol"].astype(str).str.strip().str.upper()
                return d
        except Exception:
            pass
        time.sleep(2**attempt)
    return pd.DataFrame()

ap=argparse.ArgumentParser()
ap.add_argument("--input",required=True); ap.add_argument("--output",required=True)
ap.add_argument("--start",required=True); ap.add_argument("--end",required=True)
ap.add_argument("--chunk-days",type=int,default=31); ap.add_argument("--sleep",type=float,default=0.5)
args=ap.parse_args()
x=pd.read_csv(args.input)
x["date"]=pd.to_datetime(x["date"],errors="coerce")
x["symbol"]=x["symbol"].astype(str).str.strip().str.upper()
start,end=pd.Timestamp(args.start),pd.Timestamp(args.end)
s=requests.Session(); s.headers.update({"User-Agent":"Mozilla/5.0","Accept":"*/*","Referer":"https://www.nseindia.com/"})
s.get("https://www.nseindia.com/report-detail/eq_security",timeout=30)
parts=[]
for sym in FLAGGED:
    if sym=="ADANITRANS":
        query="ADANITRANS"
    elif sym=="ADANIENSOL":
        query="ADANITRANS"
    else:
        query=sym
    cur=start
    while cur<=end:
        nxt=min(cur+pd.Timedelta(days=args.chunk_days-1),end)
        d=fetch(s,query,cur,nxt)
        if len(d):
            d["requested_symbol"]=sym
            d["repair_source"]="nse_chunked"
            parts.append(d)
        cur=nxt+pd.Timedelta(days=1)
        time.sleep(args.sleep)
rep=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
if len(rep):
    rep=rep.dropna(subset=["date","symbol"]).drop_duplicates(["date","symbol"])
    # Preserve the original dataset and only add missing date/symbol observations.
    repkeys=set(zip(rep["date"],rep["symbol"]))
    keep=[]
    for _,r in rep.iterrows():
        keep.append((r["date"],r["symbol"]) not in set(zip(x["date"],x["symbol"])))
    add=rep.loc[keep].copy()
    x=pd.concat([x,add],ignore_index=True)
else:
    add=pd.DataFrame()
x=x.drop_duplicates(["date","symbol"]).sort_values(["date","symbol"])
Path(args.output).parent.mkdir(parents=True,exist_ok=True)
x.to_csv(args.output,index=False)
Path(args.output).with_suffix(".repair.json").write_text(json.dumps({
    "flagged_symbols":FLAGGED,"repair_rows_fetched":int(len(rep)),
    "new_rows_added":int(len(add)),"total_rows":int(len(x)),
    "start":args.start,"end":args.end
},indent=2))
print(json.dumps({"repair_rows_fetched":len(rep),"new_rows_added":len(add),"total_rows":len(x)},indent=2))
