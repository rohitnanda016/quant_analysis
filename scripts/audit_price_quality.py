import argparse, json
from collections import Counter
from pathlib import Path
import pandas as pd

PRICE_CONTINUITY_SERIES = {"EQ", "BE", "BZ"}

p=argparse.ArgumentParser()
p.add_argument("--prices",required=True)
p.add_argument("--outdir",default="results/price_quality")
p.add_argument("--extreme-pct",type=float,default=0.50)
a=p.parse_args()
out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)

def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",","",regex=False).str.replace("₹","",regex=False).str.strip(),errors="coerce")

cols=["canonical_symbol","symbol","series","date","prev_close","open","high","low","close","vwap","volume","turnover ₹","turnover_₹"]
total=invalid_dates=missing_ohlc=nonpositive=ohlc_order=neg_volume=neg_turnover=duplicates=extreme=0
extreme_rows=[]; duplicate_examples=[]; seen=set(); series_counts=Counter()
for ch in pd.read_csv(a.prices,usecols=lambda c: c in cols,chunksize=250000,low_memory=False):
    # EQ is preferred, but valid BE/BZ closes are still observed market prices.
    # Their series labels remain intact for separate execution-eligibility checks.
    if "series" in ch.columns:
        ch=ch[ch["series"].astype(str).str.strip().str.upper().isin(PRICE_CONTINUITY_SERIES)].copy()
    if ch.empty:
        continue
    if "series" in ch.columns:
        series_counts.update(ch["series"].astype(str).str.strip().str.upper().value_counts().to_dict())
    total += len(ch)
    if "canonical_symbol" not in ch.columns: ch["canonical_symbol"]=ch["symbol"]
    ch["date"]=pd.to_datetime(ch["date"],errors="coerce",format="mixed")
    invalid_dates += int(ch["date"].isna().sum())
    if "turnover_₹" not in ch.columns and "turnover ₹" in ch.columns: ch["turnover_₹"]=ch["turnover ₹"]
    for c in ["prev_close","open","high","low","close","vwap","volume","turnover_₹"]:
        if c in ch: ch[c]=num(ch[c])
    missing_ohlc += int(ch[["open","high","low","close"]].isna().any(axis=1).sum())
    nonpositive += int((ch["close"]<=0).sum())
    ohlc_order += int(((ch["high"]<ch["low"])|(ch["high"]<ch["open"])|(ch["high"]<ch["close"])|(ch["low"]>ch["open"])|(ch["low"]>ch["close"])).sum())
    neg_volume += int((ch["volume"]<0).sum())
    neg_turnover += int((ch["turnover_₹"]<0).sum())
    canonical=ch["canonical_symbol"].fillna(ch["symbol"]).astype(str).str.strip().str.upper()
    keys=canonical+"|"+ch["date"].astype(str)
    for idx,key in keys.items():
        # Invalid dates are reported independently; they must not all collapse
        # into a false duplicate key such as SYMBOL|NaT.
        if pd.isna(ch.loc[idx, "date"]):
            continue
        if key in seen:
            duplicates += 1
            if len(duplicate_examples)<10000:
                duplicate_examples.append({
                    "canonical_symbol": canonical.loc[idx], "date": str(ch.loc[idx,"date"]),
                    "symbol": str(ch.loc[idx,"symbol"]),
                    "series": str(ch.loc[idx,"series"]) if "series" in ch.columns else "",
                    "close": ch.loc[idx,"close"] if "close" in ch.columns else None,
                })
        else:
            seen.add(key)
    denom=ch["prev_close"].abs()
    ret=(ch["close"]/ch["prev_close"]-1).where(denom>0)
    ex=ch.loc[ret.abs()>a.extreme_pct,["canonical_symbol","symbol","date","prev_close","close"]].copy()
    if len(ex):
        ex["return"]=ret.loc[ex.index]
        extreme_rows.append(ex)

ext=pd.concat(extreme_rows,ignore_index=True) if extreme_rows else pd.DataFrame(columns=["canonical_symbol","symbol","date","prev_close","close","return"])
extreme=len(ext)
ext.to_csv(out/"extreme_returns_raw.csv",index=False)
pd.DataFrame(duplicate_examples,columns=["canonical_symbol","date","symbol","series","close"]).to_csv(out/"duplicate_date_symbol_examples.csv",index=False)
summary={"rows":total,"series_filter":"EQ, BE and BZ price-continuity observations; original series labels retained","series_counts":dict(series_counts),"invalid_date_rows":invalid_dates,"missing_ohlc":missing_ohlc,"nonpositive_close":nonpositive,"ohlc_order_issues":ohlc_order,
"negative_volume":neg_volume,"negative_turnover":neg_turnover,"duplicate_date_symbol":duplicates,
"duplicate_examples_written":len(duplicate_examples),"extreme_returns_gt_threshold":extreme,"extreme_threshold":a.extreme_pct,
"note":"Price-quality checks cover EQ/BE/BZ observations. Mixed date formats are parsed explicitly; invalid dates are counted separately and excluded from duplicate-key counting. Duplicate keys are canonical_symbol + date across the entire file, including chunk boundaries. BE/BZ price observations are not relabeled as EQ; execution eligibility must be handled separately. Extreme-return detection uses NSE Prev Close; it is diagnostic, not evidence of a corporate action."}
(out/"price_quality_summary.json").write_text(json.dumps(summary,indent=2))
print(json.dumps(summary,indent=2))
