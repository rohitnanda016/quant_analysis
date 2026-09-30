import argparse
from pathlib import Path
import requests
import pandas as pd


def load_symbol_changes(path="data/input/verified_symbol_map.csv"):
    x = pd.read_csv(path)
    x["old_symbol"] = x["old_symbol"].astype(str)
    x["new_symbol"] = x["new_symbol"].astype(str)
    x["date_of_change"] = pd.to_datetime(x["effective_from"], errors="coerce")
    x["old_symbol"] = x.old_symbol.str.upper().str.strip()
    x["new_symbol"] = x.new_symbol.str.upper().str.strip()
    x["date_of_change"] = pd.to_datetime(x.date_of_change, errors="coerce", dayfirst=True)
    return x.dropna(subset=["old_symbol","new_symbol","date_of_change"]).drop_duplicates()

def historical_symbol(symbol, asof, changes):
    symbol = str(symbol).strip().upper()
    asof = pd.Timestamp(asof)
    seen = set()
    while symbol not in seen:
        seen.add(symbol)
        c = changes[(changes.new_symbol == symbol) & (changes.date_of_change > asof)]
        if c.empty:
            break
        symbol = c.sort_values("date_of_change").iloc[0].old_symbol
    return symbol

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--membership", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    a = ap.parse_args()

    m = pd.read_csv(a.membership, low_memory=False)
    m.columns = [str(c).strip().lower().replace(" ","_") for c in m.columns]
    m["symbol"] = m.symbol.astype(str).str.strip().str.upper()
    m["valid_from"] = pd.to_datetime(m.valid_from, errors="coerce")
    m["valid_to"] = pd.to_datetime(m.valid_to, errors="coerce")
    start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
    changes = load_symbol_changes()

    out = []
    for _, r in m.iterrows():
        vf = r.valid_from
        vt = r.valid_to if pd.notna(r.valid_to) else end
        if pd.isna(vf) or vt < start or vf > end:
            continue
        lo, hi = max(vf, start), min(vt, end)
        cuts = [lo]
        candidates = changes[(changes.new_symbol == r.symbol) &
                             (changes.date_of_change > lo) &
                             (changes.date_of_change <= hi)]["date_of_change"].tolist()
        cuts = sorted(set(cuts + candidates))
        for i, seg_start in enumerate(cuts):
            seg_end = cuts[i+1] - pd.Timedelta(days=1) if i+1 < len(cuts) else hi
            rr = r.copy()
            rr["valid_from"] = seg_start
            rr["valid_to"] = seg_end
            rr["source_symbol"] = r.symbol
            rr["canonical_symbol"] = r.symbol
            rr["symbol"] = historical_symbol(r.symbol, seg_start, changes)
            rr["acquisition_symbol"] = rr["symbol"]
            out.append(rr)

    y = pd.DataFrame(out).drop_duplicates()
    y = y.sort_values(["valid_from","symbol","valid_to"]).reset_index(drop=True)
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    y.to_csv(a.out, index=False)
    changed = y[y.symbol != y.source_symbol]
    print("membership_rows", len(y))
    print("historical_symbols", y.symbol.nunique())
    print("acquisition_symbols", y.acquisition_symbol.nunique())
    print("remapped_rows", len(changed))
    print("remapped_symbols", changed.source_symbol.nunique())
    if len(changed):
        print(changed[["source_symbol","symbol","valid_from","valid_to"]].drop_duplicates().to_string(index=False))

if __name__ == "__main__":
    main()

# Pipeline trigger: historical membership identity validation.
