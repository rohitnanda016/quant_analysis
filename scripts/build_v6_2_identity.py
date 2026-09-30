import argparse,json
from pathlib import Path
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument("--prices",required=True); p.add_argument("--membership",required=True)
p.add_argument("--symbol-map",required=True); p.add_argument("--outdir",default="data/processed/v6_2")
a=p.parse_args()
out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)

def clean(x):
    x=x.copy(); x.columns=[str(c).strip().lower().replace(" ","_") for c in x.columns]; return x

prices=clean(pd.read_csv(a.prices,low_memory=False))
mem=clean(pd.read_csv(a.membership,low_memory=False))
sm=clean(pd.read_csv(a.symbol_map))
prices["symbol"]=prices.symbol.astype(str).str.strip().str.upper()
mem["symbol"]=mem.symbol.astype(str).str.strip().str.upper()
prices["date"]=pd.to_datetime(prices.date,errors="coerce")
mem["valid_from"]=pd.to_datetime(mem.valid_from,errors="coerce")
mem["valid_to"]=pd.to_datetime(mem.valid_to,errors="coerce")
sm.old_symbol=sm.old_symbol.str.upper(); sm.new_symbol=sm.new_symbol.str.upper()
sm.effective_from=pd.to_datetime(sm.effective_from)
sm.effective_to=pd.to_datetime(sm.effective_to,errors="coerce")

# Canonical identity is the terminal symbol in the verified rename lineage.
# NSE may return the post-rename symbol even when queried with the historical
# acquisition symbol, so canonicalization uses requested_symbol when available.
rename_map = dict(zip(sm.old_symbol, sm.new_symbol))

def terminal_symbol(symbol):
    symbol = str(symbol).strip().upper()
    seen = set()
    while symbol in rename_map and symbol not in seen:
        seen.add(symbol)
        symbol = rename_map[symbol]
    return symbol

if "requested_symbol" in prices.columns:
    prices["canonical_symbol"] = prices["requested_symbol"].map(terminal_symbol)
else:
    prices["canonical_symbol"] = prices["symbol"].map(terminal_symbol)

results=[]
for _,r in sm.iterrows():
    if "requested_symbol" in prices.columns:
        n=int((prices["requested_symbol"].astype(str).str.upper()==r.old_symbol).sum())
    else:
        n=int((prices["symbol"].astype(str).str.upper()==r.old_symbol).sum())
    results.append({"old_symbol":r.old_symbol,"new_symbol":r.new_symbol,"rows_attributed":n})

mem["canonical_symbol"]=mem.symbol.map(terminal_symbol)

prices.to_csv(out/"prices_with_canonical_symbol.csv",index=False)
mem.to_csv(out/"membership_with_canonical_symbol.csv",index=False)
(out/"v6_2_summary.json").write_text(json.dumps({
    "price_rows":len(prices),"symbols":prices.symbol.nunique(),
    "canonical_symbols":prices.canonical_symbol.nunique(),
    "verified_mappings":results,"missing_prices_synthesized":False
},indent=2))
print(json.dumps(results,indent=2))
