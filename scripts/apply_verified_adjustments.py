import argparse, json
from pathlib import Path
import pandas as pd
import numpy as np

p=argparse.ArgumentParser()
p.add_argument("--prices",required=True)
p.add_argument("--actions",required=True)
p.add_argument("--out",required=True)
p.add_argument("--symbol-map",default="")
a=p.parse_args()

actions=pd.read_csv(a.actions)
actions["symbol"]=actions.symbol.astype(str).str.upper().str.strip()
actions["ex_date"]=pd.to_datetime(actions.ex_date,errors="coerce")
actions["factor"]=pd.to_numeric(actions.factor,errors="coerce")
actions=actions.dropna(subset=["symbol","ex_date","factor"])
if (actions.factor<=0).any():
    raise SystemExit("Invalid adjustment factor generated")

aliases={}
if a.symbol_map and Path(a.symbol_map).exists():
    sm=pd.read_csv(a.symbol_map)
    for _,r in sm.iterrows():
        old=str(r.get("old_symbol","")).strip().upper()
        new=str(r.get("new_symbol","")).strip().upper()
        if old and new and old!="NAN" and new!="NAN":
            aliases[old]=new
            aliases[new]=new

actions=actions.sort_values(["symbol","ex_date"])
events={s:(g.ex_date.to_numpy(),g.factor.to_numpy()) for s,g in actions.groupby("symbol")}

outp=Path(a.out); outp.parent.mkdir(parents=True,exist_ok=True)
first=True; adjusted_rows=0; nonunit_rows=0; mapped_rows=0; total_rows=0
price_cols=["prev_close","open","high","low","close","vwap"]

for ch in pd.read_csv(a.prices,chunksize=250000,low_memory=False):
    total_rows += len(ch)
    ch["raw_symbol"]=ch["symbol"].astype(str).str.upper().str.strip()
    ch["canonical_symbol"]=ch["raw_symbol"].map(lambda s: aliases.get(s,s))
    mapped_rows += int((ch["canonical_symbol"] != ch["raw_symbol"]).sum())
    ch["date"]=pd.to_datetime(ch["date"],errors="coerce")
    if "turnover_₹" not in ch.columns and "turnover ₹" in ch.columns:
        ch["turnover_₹"]=ch["turnover ₹"]
    for c in price_cols+["volume","turnover_₹"]:
        if c in ch:
            ch[c]=pd.to_numeric(ch[c].astype(str).str.replace(",","",regex=False).str.replace("₹","",regex=False).str.strip(),errors="coerce")

    factors=np.ones(len(ch),dtype=float)
    prev_factors=np.ones(len(ch),dtype=float)
    for sym,idx in ch.groupby("canonical_symbol",sort=False).groups.items():
        if sym not in events:
            continue
        dates,fs=events[sym]
        positions=ch.index.get_indexer(idx)
        d=ch["date"].iloc[positions].to_numpy()
        vals=np.ones(len(positions),dtype=float)
        prev_vals=np.ones(len(positions),dtype=float)
        for ex,f in zip(dates,fs):
            vals[d<ex] *= f
            prev_vals[d<=ex] *= f
        factors[positions]=vals
        prev_factors[positions]=prev_vals

    mask=factors!=1
    nonunit_rows += int(mask.sum())
    if mask.any():
        for c in price_cols:
            if c in ch:
                ch.loc[mask,c]=ch.loc[mask,c]*factors[mask]
        if "prev_close" in ch:
            prev_mask=prev_factors!=1
            ch.loc[prev_mask,"prev_close"]=ch.loc[prev_mask,"prev_close"]*prev_factors[prev_mask]
        if "volume" in ch:
            ch["volume"]=ch["volume"].astype(float)
            ch.loc[mask,"volume"]=ch.loc[mask,"volume"].to_numpy(dtype=float)/factors[mask]
        adjusted_rows += int(mask.sum())

    ch["adjustment_factor"]=factors
    ch["prev_close_adjustment_factor"]=prev_factors
    ch["adjustment_method"]="verified_split_bonus_proxy"
    ch["dividend_adjustment"]="not_applied"
    ch.to_csv(outp,index=False,mode="w" if first else "a",header=first)
    first=False

summary={"input":a.prices,"actions":a.actions,"output":a.out,"verified_actions":len(actions),
"adjusted_rows":adjusted_rows,"nonunit_factor_rows":nonunit_rows,
"historical_symbol_rows_mapped":mapped_rows,"total_rows":total_rows,
"dividend_adjustment_applied":False,
"warning":"The action file is incomplete for 2014-2026. This output is a research proxy and must not be used as a production total-return series."}
Path(str(outp)+".summary.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
