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
    for value, kind in parts:
        factor *= value
        if kind not in kinds:
            kinds.append(kind)
    return factor, "+".join(kinds)

def load_aliases(path):
    df = pd.read_csv(path)
    aliases = {}
    for _, row in df.iterrows():
        old = str(row.get("old_symbol", "")).strip().upper()
        new = str(row.get("new_symbol", "")).strip().upper()
        if old and new and old != "NAN" and new != "NAN":
            aliases[old] = new
            aliases[new] = new
    return aliases

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--actions", required=True)
    ap.add_argument("--symbol-map", required=True)
    ap.add_argument("--supplemental", default="")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    ca = pd.read_csv(args.actions, low_memory=False)
    ca.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in ca.columns]
    if "symbol" not in ca.columns or "ex_date" not in ca.columns:
        raise RuntimeError(f"NSE action file missing required columns: {list(ca.columns)}")
    purpose_col = "purpose" if "purpose" in ca.columns else "subject"
    if purpose_col not in ca.columns:
        raise RuntimeError("NSE action file has neither purpose nor subject")

    ca["symbol"] = ca["symbol"].astype(str).str.upper().str.strip()
    ca["ex_date"] = pd.to_datetime(ca["ex_date"], errors="coerce")
    ca["purpose"] = ca[purpose_col].fillna("").astype(str)

    parsed = ca["purpose"].map(parse_factor)
    ca["theoretical_factor"] = parsed.map(lambda x: x[0])
    ca["action_type"] = parsed.map(lambda x: x[1])
    ca["factor_component"] = pd.to_numeric(ca["theoretical_factor"], errors="coerce")

    aliases = load_aliases(args.symbol_map)
    ca["lookup_symbol"] = ca["symbol"].map(lambda x: aliases.get(x, x))

    rows = []
    usable = ca.dropna(subset=["ex_date", "factor_component"]).copy()
    for (symbol, ex_date), grp in usable.groupby(["lookup_symbol", "ex_date"], sort=False):
        theoretical = float(grp["factor_component"].prod())
        if theoretical <= 0 or not pd.notna(theoretical):
            continue
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
            "theoretical_factor": theoretical,
            "factor": 1.0 / theoretical,
            "purpose": " / ".join(purposes),
            "action_type": "+".join(kinds),
            "source": "NSE corporate actions",
            "source_symbol": str(grp.iloc[0]["symbol"]),
            "confidence": "high_exchange_documented",
        })

    columns = [
        "lookup_symbol", "ex_date", "theoretical_factor", "factor",
        "purpose", "action_type", "source", "source_symbol", "confidence"
    ]
    g = pd.DataFrame(rows, columns=columns)

    if args.supplemental:
        path = Path(args.supplemental)
        if path.exists():
            sup = pd.read_csv(path, low_memory=False)
            required = {"symbol", "ex_date", "inferred_factor"}
            missing = required - set(sup.columns)
            if missing:
                raise RuntimeError(f"Supplemental action file missing columns: {sorted(missing)}")
            sup["symbol"] = sup["symbol"].astype(str).str.upper().str.strip()
            sup["ex_date"] = pd.to_datetime(sup["ex_date"], errors="coerce")
            sup["theoretical_factor"] = pd.to_numeric(sup["inferred_factor"], errors="coerce")
            sup = sup.dropna(subset=["symbol", "ex_date", "theoretical_factor"])
            sup["lookup_symbol"] = sup["symbol"].map(lambda x: aliases.get(x, x))

            existing = set(zip(g["lookup_symbol"], g["ex_date"])) if not g.empty else set()
            manual = []
            for _, row in sup.iterrows():
                key = (row["lookup_symbol"], row["ex_date"])
                if key in existing:
                    continue
                manual.append({
                    "lookup_symbol": row["lookup_symbol"],
                    "ex_date": row["ex_date"],
                    "theoretical_factor": float(row["theoretical_factor"]),
                    "factor": 1.0 / float(row["theoretical_factor"]),
                    "purpose": str(row.get("subject", row.get("action", ""))),
                    "action_type": str(row.get("action_type", "manual_verified")),
                    "source": str(row.get("source", "verified manual")),
                    "source_symbol": row["symbol"],
                    "confidence": str(row.get("confidence", "high_manual_verified")),
                })
            if manual:
                g = pd.concat([g, pd.DataFrame(manual, columns=columns)], ignore_index=True)

    if g.empty:
        raise RuntimeError("No split/bonus price-adjustment actions were produced")

    g = g.sort_values(["lookup_symbol", "ex_date"], kind="stable")
    g = g.drop_duplicates(["lookup_symbol", "ex_date"], keep="first")
    g["factor"] = pd.to_numeric(g["factor"], errors="coerce")
    if g["factor"].isna().any() or (g["factor"] <= 0).any():
        raise RuntimeError("Invalid adjustment factor generated")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    g.rename(columns={"lookup_symbol": "symbol"}).to_csv(out, index=False)

    print({
        "actions": int(len(g)),
        "symbols": int(g["symbol"].nunique()),
        "start": str(g["ex_date"].min().date()),
        "end": str(g["ex_date"].max().date()),
        "manual_added": int(sum(1 for x in g["confidence"] if str(x) == "high_manual_verified")),
    })

if __name__ == "__main__":
    main()
