import argparse,io,time,json
from pathlib import Path
import requests,pandas as pd
URL="https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData"
MEM="data/input/nifty500_membership.csv"
def cc(c):
 c=str(c).replace("\ufeff","").replace("\xa0"," ").strip().strip('"'); return " ".join(c.split()).lower()
def get(s,sym,a,b):
 p={"symbol":sym,"from":a.strftime("%d-%m-%Y"),"to":b.strftime("%d-%m-%Y"),"series":"EQ","type":"priceVolumeDeliverable","csv":"true"}
 for i in range(4):
  try:
   r=s.get(URL,params=p,timeout=45)
   if r.status_code==200 and len(r.content)>100:
    d=pd.read_csv(io.StringIO(r.content.decode("utf-8-sig",errors="replace")),skipinitialspace=True)
    d.columns=[cc(x) for x in d.columns]
    mp={"prev close":"prev_close","open price":"open","high price":"high","low price":"low","last price":"last","close price":"close","average price":"vwap","total traded quantity":"volume","turnover":"traded_value","no. of trades":"num_trades","deliverable qty":"deliverable_qty","% dly qt to traded qty":"deliverable_pct"}
    d=d.rename(columns=mp); d["date"]=pd.to_datetime(d["date"],errors="coerce",dayfirst=True); d["symbol"]=d["symbol"].astype(str).str.strip().str.upper()
    return d
  except Exception: pass
  time.sleep(2**i)
 return pd.DataFrame()
p=argparse.ArgumentParser(); p.add_argument("--start",required=True); p.add_argument("--end",required=True); p.add_argument("--membership",default=MEM); p.add_argument("--out",default="data/raw/stage_a_prices.csv"); p.add_argument("--sleep",type=float,default=1.0)
a=p.parse_args(); start=pd.Timestamp(a.start); end=pd.Timestamp(a.end)
m=pd.read_csv(a.membership); m.columns=[str(c).strip().lower().replace(" ","_") for c in m.columns]; m.symbol=m.symbol.astype(str).str.strip().str.upper(); m.valid_from=pd.to_datetime(m.valid_from,errors="coerce"); m.valid_to=pd.to_datetime(m.valid_to,errors="coerce").fillna(end)
syms=sorted(m.loc[(m.valid_from<=end)&(m.valid_to>=start),"symbol"].unique())
s=requests.Session(); s.headers.update({"User-Agent":"Mozilla/5.0","Accept":"*/*","Referer":"https://www.nseindia.com/"}); s.get("https://www.nseindia.com/report-detail/eq_security",timeout=30)
parts=[]; failures=[]
for i,sym in enumerate(syms,1):
 d=get(s,sym,start,end)
 if len(d): parts.append(d)
 else: failures.append(sym)
 if i%25==0: print(f"processed {i}/{len(syms)} rows={sum(len(x) for x in parts)} failures={len(failures)}",flush=True)
 time.sleep(a.sleep)
x=pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
if len(x): x=x.dropna(subset=["date","symbol"]).drop_duplicates(["date","symbol"]).sort_values(["date","symbol"])
Path(a.out).parent.mkdir(parents=True,exist_ok=True); x.to_csv(a.out,index=False)
Path(a.out).with_suffix(".audit.json").write_text(json.dumps({"start":a.start,"end":a.end,"symbols_requested":len(syms),"symbols_returned":int(x.symbol.nunique()) if len(x) else 0,"rows":len(x),"failed_symbols":failures},indent=2))
print(json.dumps({"rows":len(x),"symbols":int(x.symbol.nunique()) if len(x) else 0,"failed_symbols":failures},indent=2))

# Pipeline trigger: 2026-09-30
