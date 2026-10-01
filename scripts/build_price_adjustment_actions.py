import argparse, re
from pathlib import Path
import pandas as pd

def parse_factor(text):
    p = str(text or "").upper()
    parts = []
    for x, y in re.findall(r"BONUS\s+(\d+)\s*:\s*(\d+)", p):
        y = int(y)
        if y:
            parts.append(((int(x) + y) / y, "bonus"))
    for old, new in re.findall(r"FROM\s+RS\.?\s*([0-9.]+).*?TO\s+R(?:S|E)?\.?\s*([0-9.]+)", p):
        old, new = float(old), float(new)
        if new and any(k in p for k in ("SPLIT", "CONSOLIDATION", "SUB-DIVISION")):
            parts.append((old / new, "split_or_consolidation"))
    if not parts:
        return None, None
    factor = 1.0
    kinds = []
    for f, k in parts:
        factor *= f
        if k not in kinds:
            kinds.append(k)
    return factor, "+".join(kinds)

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
purpose_col = "purpose" if "purpose" in ca.columns else "subject"
ca["purpose"] = ca[purpose_col].fillna("").astype(str)

parsed = ca["purpose"].map(parse_factor)
ca["theoretical_factor"] = parsed.map(lambda x: x[0])
ca["action_type"] = parsed.map(lambda x: x[1])

sm = pd.read_csv(args.symbol_map)
aliases = {}
for _, row in sm.iterrows():
    old = str(row.get("old_symbol", "")).strip().upper()
    new = str(row.get("new_symbol", "")).strip().upper()
    if old and new and old != "NAN" and new != "NAN":
        aliases[old] = new
        aliases[new] = new
ca["lookup_symbol"] = ca["symbol"].map(lambda x: aliases.get(x, x))
ca["factor_component"] = pd.to_numeric(ca["theoretical_factor"], errors="coerce")

rows = []
for (symbol, ex_date), grp in ca.dropna(subset=["ex_date", "factor_component"]).groupby(["lookup_symbol", "ex_date"]):
    factor = float(grp["factor_component"].prod())
    purposes = []
    kinds = []
    for value in grp["purpose"]:
        value = str(value).strip()
        if value and value not in purposes:
            purposes.append(value)
    for value in grp["action_type"].dropna():
        value = str(value).strip()
        if value and value not in kinds:
            kinds.append(value)
    rows.append({
        "lookup_symbol": symbol,
        "ex_date": ex_date,
        "theoretical_factor": factor,
        "factor": 1.0 / factor,
        "purpose": " / ".join(purposes),
        "action_type": "+".join(kinds),
        "source": "NSE corporate actions",
        "source_symbol": str(grp.iloc[0]["symbol"]),
        "confidence": "high_exchange_documented",
    })

g = pd.DataFrame(rows)

if args.supplemental and Path(args.supplemental).exists():
    sup = pd.read_csv(args.supplemental)
    sup["symbol"] = sup["symbol"].astype(str).str.upper().str.strip()
    sup["ex_date"] = pd.to_datetime(sup["ex_date"], errors="coerce")
    sup["theoretical_factor"] = pd.to_numeric(sup["inferred_factor"], errors="coerce")
    sup = sup.dropna(subset=["symbol", "ex_date", "theoretical_factor"])
    sup["lookup_symbol"] = sup["symbol"].map(lambda x: aliases.get(x, x))
    existing = set(zip(g["lookup_symbol"], g["ex_date"])) if len(g) else set()
    sup = sup[[ (s, d) not in existing for s, d in zip(sup["lookup_symbol"], sup["ex_date"]) ]]
    manual_rows = []
    for _, row in sup.iterrows():
        manual_rows.append({
            "lookup_symbol": row["lookup_symbol"],
            "ex_date": row["ex_date"],
            "theoretical_factor": float(row["theoretical_factor"]),
            "factor": 1.0 / float(row["theoretical_factor"]),
            "purpose": str(row.get("subject", "")),
            "action_type": str(row.get("action_type", "manual_verified")),
            "source": str(row.get("source", "verified manual")),
            "source_symbol": row["symbol"],
            "confidence": str(row.get("confidence", "high_manual_verified")),
        })
    if manual_rows:
        g = pd.concat([g, pd.DataFrame(manual_rows)], ignore_index=True)

g = g.sort_values(["lookup_symbol", "ex_date"]).drop_duplicates(["lookup_symbol", "ex_date"], keep="first")
out = Path(args.out)
out.parent.mkdir(parents=True, exist_ok=True)
g.rename(columns={"lookup_symbol": "symbol"}).to_csv(out, index=False)
print({"actions": len(g), "symbols": g["symbol"].nunique(), "start": str(g["ex_date"].min().date()), "end": str(g["ex_date"].max().date())})
