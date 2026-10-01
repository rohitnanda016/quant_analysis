import argparse, json
from pathlib import Path
import pandas as pd
import numpy as np

p=argparse.ArgumentParser()
p.add_argument("--prices",required=True); p.add_argument("--actions",required=True); p.add_argument("--out",required=True)
a=p.parse_args()
actions=pd.read_csv(a.actions)
actions["symbol"]=actions.symbol.astype(str).str.upper().str.strip()
actions["ex_date"]=pd.to_datetime(actions.ex_date,errors="coerce")
actions["factor"]=pd.to_numeric(actions.factor,errors="coerce")
actions=actions.dropna(subset=["symbol","ex_date","factor"])
# Back-adjust prices before each ex-date. Factors in the action table are
# price adjustment multipliers (e.g. 0.1 for a 1:10 split).
actions=actions.sort_values(["symbol","ex_date"])
valid=[]
for s,g in actions.groupby("symbol"):
    if (g.factor<=0).any(): raise SystemExit(f"Invalid factor for {s}")
    valid.append(g)
actions=pd.concat(valid,ignore_index=True) if valid else actions

def factor_for(sym,dt):
    g=actions[(actions.symbol==sym)&(actions.ex_date>dt)]
    return float(g.factor.prod()) if len(g) else 1.0

# Build per-symbol event arrays for vectorized chunk adjustment.
events={s:(g.ex_date.to_numpy(),g.factor.to_numpy()) for s,g in actions.groupby("symbol")}
outp=Path(a.out); outp.parent.mkdir(parents=True,exist_ok=True)
first=True; adjusted_rows=0
price_cols=["prev_close","open","high","low","close","vwap"]
for ch in pd.read_csv(a.prices,chunksize=250000,low_memory=False):
    if "canonical_symbol" not in ch.columns: ch["canonical_symbol"]=ch["symbol"]
    ch["date"]=pd.to_datetime(ch["date"],errors="coerce")
    if "turnover_₹" not in ch.columns and "turnover ₹" in ch.columns: ch["turnover_₹"]=ch["turnover ₹"]
    for c in price_cols+["volume","turnover_₹"]:
        if c in ch: ch[c]=pd.to_numeric(ch[c].astype(str).str.replace(",","",regex=False).str.replace("₹","",regex=False).str.strip(),errors="coerce")
    factors=np.ones(len(ch),dtype=float)
    for sym,idx in ch.groupby("canonical_symbol").groups.items():
        if sym not in events: continue
        dates,fs=events[sym]
        vals=np.ones(len(idx),dtype=float)
        d=ch.loc[idx,"date"].to_numpy()
        for ex,f in zip(dates,fs):
            vals[d<ex] *= f
        factors[list(ch.index.get_indexer(idx))]=vals
    mask=factors!=1
    if mask.any():
        for c in price_cols:
            if c in ch: ch.loc[mask,c]=ch.loc[mask,c]*factors[mask]
        if "volume" in ch: ch.loc[mask,"volume"]=ch.loc[mask,"volume"]/factors[mask]
        adjusted_rows += int(mask.sum())
    ch["adjustment_factor"]=factors
    ch["adjustment_method"]="verified_split_bonus_proxy"
    ch["dividend_adjustment"]="not_applied"
    ch.to_csv(outp,index=False,mode="w" if first else "a",header=first)
    first=False
summary={"input":a.prices,"actions":a.actions,"output":a.out,"verified_actions":len(actions),
"adjusted_rows":adjusted_rows,"dividend_adjustment_applied":False,
"warning":"The action file is incomplete for 2014-2026. This output is a research proxy and must not be used as a production total-return series."}
Path(str(outp)+".summary.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
