import argparse, re
from pathlib import Path
import pandas as pd

def parse_factor(text):
    p = str(text or "").upper()
    factors, kinds = [], []
    for x, y in re.findall(r"BONUS\s+(\d+)\s*:\s*(\d+)", p):
        x, y = int(x), int(y)
        if y > 0:
            factors.append((x + y) / y)
            kinds.append("bonus")
    for old, new in re.findall(r"FROM\s+RS\.?\s*([0-9.]+).*?TO\s+R(?:S|E)?\.?\s*([0-9.]+)", p):
        old, new = float(old), float(new)
        if new > 0 and any(k in p for k in ("SPLIT", "CONSOLIDATION", "SUB-DIVISION")):
            factors.append(old / new)
            kinds.append("split_or_consolidation")
    if not factors:
        return None, None
    f = 1.0
    for x in factors:
        f *= x
    return f, "+".join(dict.fromkeys(kinds))

ap = argparse.ArgumentParser()
ap.add_argument("--actions", required=True)
ap.add_argument("--symbol-map", required=True)
ap.add_argument("--supplemental", default="")
ap.add_argument("--out", required=True)
args = ap.parse_args()

ca = pd.read_csv(args.actions)
ca.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in ca.columns]
ca["symbol"] = ca["symbol"].astype(str).str.upper().str.strip()
ca["ex_date"] = pd.to_datetime(ca["ex_date"], errors="coerce")
ca["purpose"] = ca["purpose"] if "purpose" in ca.columns else ca["subject"]
ca["purpose"] = ca["purpose"].fillna("").astype(str)
ca["theoretical_factor"], ca["action_type"] = zip(*ca["purpose"].map(parse_factor))

sm = pd.read_csv(args.symbol_map)
aliases = {}
for _, r in sm.iterrows():
    old = str(r.get("old_symbol", "")).strip().upper()
    new = str(r.get("new_symbol", "")).strip().upper()
    if old and new and old != "NAN" and new != "NAN":
        aliases[old] = new
        aliases[new] = new
ca["lookup_symbol"] = ca["symbol"].map(lambda x: aliases.get(x, x))
ca["factor_component"] = pd.to_numeric(ca["theoretical_factor"], errors="coerce")

g = (ca.dropna(subset=["ex_date", "factor_component"])
       .groupby(["lookup_symbol", "ex_date"], as_index=False)
       .agg(
           theoretical_factor=("factor_component", "prod"),
           purpose=("purpose", lambda s: " / ".join(dict.fromkeys(x.strip() for x in s if x.strip()))),
           action_type=("action_type", lambda s: "+".join(dict.fromkeys(x for x in s if str(x).strip()))),
           source=("symbol", lambda s: "NSE corporate actions"),
           source_symbol=("symbol", "first"),
       ))
g["factor"] = 1.0 / g["theoretical_factor"]
g["confidence"] = "high_exchange_documented"

if args.supplemental and Path(args.supplemental).exists():
    sup = pd.read_csv(args.supplemental)
    sup["symbol"] = sup["symbol"].astype(str).str.upper().str.strip()
    sup["ex_date"] = pd.to_datetime(sup["ex_date"], errors="coerce")
    sup["theoretical_factor"] = pd.to_numeric(sup["inferred_factor"], errors="coerce")
    sup = sup.dropna(subset=["symbol", "ex_date", "theoretical_factor"])
    sup["lookup_symbol"] = sup["symbol"].map(lambda x: aliases.get(x, x))
    existing = pd.MultiIndex.from_frame(g[["lookup_symbol", "ex_date"]])
    sup_idx = pd.MultiIndex.from_frame(sup[["lookup_symbol", "ex_date"]])
    sup = sup[~sup_idx.isin(existing)]
    sup["factor"] = 1.0 / sup["theoretical_factor"]
    sup["purpose"] = sup.get("subject", "")
    sup["action_type"] = sup.get("action_type", "manual_verified")
    sup["source"] = sup.get("source", "verified manual")
    sup["source_symbol"] = sup["symbol"]
    sup["confidence"] = sup.get("confidence", "high_manual_verified")
    g = pd.concat([g, sup[g.columns]], ignore_index=True)

g = g.sort_values(["lookup_symbol", "ex_date"]).drop_duplicates(["lookup_symbol", "ex_date"], keep="first")
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
g.rename(columns={"lookup_symbol": "symbol"}).to_csv(out, index=False)

print({
    "actions": int(len(g)),
    "symbols": int(g["symbol"].nunique()),
    "start": str(g["ex_date"].min().date()),
    "end": str(g["ex_date"].max().date()),
    "action_types": g["action_type"].value_counts().to_dict(),
})
