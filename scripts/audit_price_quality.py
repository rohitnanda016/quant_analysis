import argparse, json
from pathlib import Path
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument("--prices",required=True)
p.add_argument("--outdir",default="results/price_quality")
p.add_argument("--extreme-pct",type=float,default=0.50)
a=p.parse_args()
out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)

def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",","",regex=False).str.replace("₹","",regex=False).str.strip(),errors="coerce")

cols=["canonical_symbol","symbol","date","prev_close","open","high","low","close","vwap","volume"]
total=0; missing_ohlc=nonpositive=ohlc_order=neg_volume=neg_turnover=duplicates=extreme=0
extreme_rows=[]; seen=set()

for ch in pd.read_csv(a.prices,usecols=lambda c: c in cols or c=="turnover_₹",chunksize=250000,low_memory=False):
    total += len(ch)
    ch["date"]=pd.to_datetime(ch["date"],errors="coerce")
    for c in ["prev_close","open","high","low","close","vwap","volume","turnover_₹"]:
        if c in ch: ch[c]=num(ch[c])
    missing_ohlc += int(ch[["open","high","low","close"]].isna().any(axis=1).sum())
    nonpositive += int((ch["close"]<=0).sum())
    ohlc_order += int(((ch["high"]<ch["low"])|(ch["high"]<ch["open"])|(ch["high"]<ch["close"])|(ch["low"]>ch["open"])|(ch["low"]>ch["close"])).sum())
    neg_volume += int((ch["volume"]<0).sum())
    neg_turnover += int((ch["turnover_₹"]<0).sum())
    keys=ch["canonical_symbol"].astype(str)+"|"+ch["date"].astype(str)
    duplicates += int(keys.duplicated().sum())
    denom=ch["prev_close"].abs()
    ret=(ch["close"]/ch["prev_close"]-1).where(denom>0)
    ex=ch.loc[ret.abs()>a.extreme_pct,["canonical_symbol","date","prev_close","close"]].copy()
    if len(ex):
        ex["return"]=ret.loc[ex.index]
        extreme_rows.append(ex)

ext=pd.concat(extreme_rows,ignore_index=True) if extreme_rows else pd.DataFrame(columns=["canonical_symbol","date","prev_close","close","return"])
extreme=len(ext)
ext.to_csv(out/"extreme_returns_raw.csv",index=False)
summary={"rows":total,"missing_ohlc":missing_ohlc,"nonpositive_close":nonpositive,"ohlc_order_issues":ohlc_order,
"negative_volume":neg_volume,"negative_turnover":neg_turnover,"duplicate_date_symbol":duplicates,
"extreme_returns_gt_threshold":extreme,"extreme_threshold":a.extreme_pct,
"note":"Extreme-return detection uses NSE Prev Close. It is a diagnostic, not evidence of a corporate action."}
(out/"price_quality_summary.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
