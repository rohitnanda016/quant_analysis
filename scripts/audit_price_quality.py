import argparse, json
from collections import Counter
from pathlib import Path
import pandas as pd

try:
    from scripts.symbol_lineage import load_symbol_rename_rows, terminal_symbol_aliases
except ModuleNotFoundError:
    from symbol_lineage import load_symbol_rename_rows, terminal_symbol_aliases

PRICE_CONTINUITY_SERIES = {"EQ", "BE", "BZ"}

p=argparse.ArgumentParser()
p.add_argument("--prices",required=True)
p.add_argument("--outdir",default="results/price_quality")
p.add_argument("--extreme-pct",type=float,default=0.50)
p.add_argument("--symbol-map",default="data/input/verified_symbol_map.csv")
p.add_argument("--symbol-map-supplement",default="data/reference/nse_historical_symbol_changes.csv")
a=p.parse_args()
out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)
rename_rows = load_symbol_rename_rows(a.symbol_map, a.symbol_map_supplement)
aliases = terminal_symbol_aliases(rename_rows)

def canonicalize_symbol(value):
    if pd.isna(value):
        return value
    symbol = str(value).strip().upper()
    return aliases.get(symbol, symbol)

def num(s):
    return pd.to_numeric(s.astype(str).str.replace(",","",regex=False).str.replace("₹","",regex=False).str.strip(),errors="coerce")

cols=["canonical_symbol","requested_symbol","symbol","series","date","prev_close","open","high","low","close","vwap","volume","turnover ₹","turnover_₹"]
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
    # Use the stable strategy/request key for archive-repaired rows whose
    # historical exchange ticker differs from the modern universe ticker.
    raw_symbol = ch["symbol"].astype("string").str.strip()
    requested_symbol = (
        ch["requested_symbol"].astype("string").str.strip()
        if "requested_symbol" in ch.columns else pd.Series(pd.NA, index=ch.index, dtype="string")
    )
    if "canonical_symbol" in ch.columns:
        canonical = ch["canonical_symbol"].astype("string").str.strip()
    else:
        canonical = pd.Series(pd.NA, index=ch.index, dtype="string")
    canonical = canonical.where(canonical.notna() & canonical.ne("") & ~canonical.str.lower().isin(["nan", "none", "<na>"]), requested_symbol)
    canonical = canonical.where(canonical.notna() & canonical.ne("") & ~canonical.str.lower().isin(["nan", "none", "<na>"]), raw_symbol)
    # Use the same terminal ticker identity as the adjustment pipeline. Merely
    # preferring requested_symbol leaves historical aliases unmatched against
    # adjusted prices and falsely inflates missing-adjusted-row diagnostics.
    canonical = canonical.map(canonicalize_symbol)
    ch["canonical_symbol"] = canonical
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
    # Vectorize duplicate detection while retaining cross-chunk state. The
    # previous per-row .loc loop was quadratic-ish on large histories and made
    # the readiness workflow appear stalled on ~2M-row inputs.
    valid_keys = keys.loc[ch["date"].notna()]
    duplicate_mask = valid_keys.duplicated(keep="first") | valid_keys.isin(seen)
    duplicate_indices = valid_keys.index[duplicate_mask]
    duplicates += int(duplicate_mask.sum())
    if len(duplicate_indices) and len(duplicate_examples) < 10000:
        remaining_slots = 10000 - len(duplicate_examples)
        examples = ch.loc[duplicate_indices[:remaining_slots], [
            c for c in ["canonical_symbol", "date", "symbol", "series", "close"]
            if c in ch.columns
        ]].copy()
        examples["date"] = examples["date"].astype(str)
        duplicate_examples.extend(examples.to_dict("records"))
    seen.update(valid_keys.tolist())
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
