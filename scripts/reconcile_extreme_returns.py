import argparse, json, re
from pathlib import Path
import pandas as pd

def parse_factor(purpose):
    p = str(purpose or "").upper()

    # Observed factor is Prev Close / Ex-date Close. Build the total
    # factor from every price-affecting component in the action text.
    factors = []
    action_types = []

    bonus_matches = re.findall(r"BONUS\s+(\d+)\s*:\s*(\d+)", p)
    for x, y in bonus_matches:
        x, y = int(x), int(y)
        if y > 0:
            factors.append((x + y) / y)
            action_types.append("bonus")

    split_matches = re.findall(
        r"FROM\s+RS\.?\s*([0-9.]+).*?TO\s+R(?:S|E)?\.?\s*([0-9.]+)",
        p
    )
    if split_matches and ("SPLIT" in p or "CONSOLIDATION" in p or "SUB-DIVISION" in p):
        old, new = map(float, split_matches[-1])
        if new > 0:
            factors.append(old / new)
            action_types.append("split_or_consolidation")

    if not factors:
        return None, None

    factor = 1.0
    for f in factors:
        factor *= f
    return factor, "+".join(action_types)

def aliases(path):
    if not Path(path).exists():
        return {}
    m = pd.read_csv(path)
    out = {}
    for _, r in m.iterrows():
        old = str(r.get("old_symbol", "")).strip().upper()
        new = str(r.get("new_symbol", "")).strip().upper()
        if old and new and old != "NAN" and new != "NAN":
            out[old] = new
            out[new] = new
    return out

def first_existing_series(df, names):
    for name in names:
        if name in df.columns:
            return df[name].fillna("").astype(str)
    return pd.Series("", index=df.index, dtype="object")

p = argparse.ArgumentParser()
p.add_argument("--extremes", required=True)
p.add_argument("--actions", required=True)
p.add_argument("--symbol-map", required=False, default="")
p.add_argument("--out", required=True)
a = p.parse_args()

e = pd.read_csv(a.extremes)
e["date"] = pd.to_datetime(e["date"], errors="coerce")
e["symbol"] = e["canonical_symbol"].astype(str).str.upper().str.strip()
e["observed_factor"] = (
    pd.to_numeric(e["prev_close"], errors="coerce")
    / pd.to_numeric(e["close"], errors="coerce")
)

ca = pd.read_csv(a.actions)
ca.columns = [
    str(c).strip().lower().replace(" ", "_").replace("-", "_")
    for c in ca.columns
]
ca["symbol"] = ca["symbol"].astype(str).str.upper().str.strip()
ca["ex_date"] = pd.to_datetime(ca["ex_date"], errors="coerce")
ca["purpose"] = first_existing_series(ca, ["purpose", "subject"])
ca[["inferred_factor", "action_type"]] = ca["purpose"].apply(
    lambda x: pd.Series(parse_factor(x))
)

amap = aliases(a.symbol_map)
e["lookup_symbol"] = e["symbol"].map(lambda x: amap.get(x, x))
ca["lookup_symbol"] = ca["symbol"].map(lambda x: amap.get(x, x))

# NSE can publish simultaneous corporate actions as separate rows on the
# same symbol/ex-date (e.g. bonus + split). Aggregate all price-affecting
# factors before comparing with the observed price discontinuity.
ca["has_action"] = ca["purpose"].str.len().fillna(0).gt(0)
ca["_factor"] = pd.to_numeric(ca["inferred_factor"], errors="coerce")
ca["_factor_for_product"] = ca["_factor"].fillna(1.0)
ca_group = (
    ca.groupby(["lookup_symbol", "ex_date"], dropna=False)
      .agg(
          purpose=("purpose", lambda s: " / ".join(
              dict.fromkeys(str(x) for x in s if str(x).strip() and str(x).lower() != "nan")
          )),
          inferred_factor=("_factor_for_product", "prod"),
          has_action=("has_action", "any"),
          factor_count=("_factor", lambda s: int(s.notna().sum())),
          action_type=("action_type", lambda s: "+".join(
              dict.fromkeys(str(x) for x in s if str(x).strip() and str(x).lower() != "nan")
          )),
          record_date=("rec_date", "first"),
          face_value=("face_val", "first"),
      )
      .reset_index()
)
# If an action date has no price factor at all, do not manufacture a factor.
ca_group.loc[ca_group["factor_count"] == 0, "inferred_factor"] = float("nan")

m = e.merge(
    ca_group,
    how="left",
    left_on=["lookup_symbol", "date"],
    right_on=["lookup_symbol", "ex_date"],
    suffixes=("_extreme", "_action"),
)

m["factor_error"] = abs(m["observed_factor"] / m["inferred_factor"] - 1)
m["status"] = "NO_EXACT_ACTION"

has = m["has_action"].fillna(False)
m.loc[has, "status"] = "ACTION_ON_DATE"

exact_factor = (
    has
    & m["inferred_factor"].notna()
    & (m["factor_error"] <= 0.08)
)
m.loc[exact_factor, "status"] = "EXACT_SPLIT_BONUS_RATIO_MATCH"

m.loc[
    has & m["inferred_factor"].isna(),
    "status"
] = "ACTION_ON_DATE_NON_PRICE_FACTOR"

m.loc[
    has & m["inferred_factor"].notna() & (m["factor_error"] > 0.08),
    "status"
] = "ACTION_RATIO_MISMATCH"


cols = [
    "symbol_extreme", "date", "prev_close", "close", "return",
    "observed_factor", "symbol_action", "purpose", "ex_date",
    "record_date", "face_value", "inferred_factor", "action_type",
    "factor_error", "status"
]
cols = [c for c in cols if c in m.columns]
m[cols].sort_values(["date", "symbol_extreme"]).to_csv(a.out, index=False)

rank = {
    "EXACT_SPLIT_BONUS_RATIO_MATCH": 0,
    "ACTION_ON_DATE_NON_PRICE_FACTOR": 1,
    "ACTION_RATIO_MISMATCH": 2,
    "ACTION_ON_DATE": 3,
    "NO_EXACT_ACTION": 4,
}
m["_rank"] = m["status"].map(rank).fillna(99)
best = (
    m.sort_values(
        ["symbol_extreme", "date", "_rank", "factor_error"],
        na_position="last"
    )
    .drop_duplicates(["symbol_extreme", "date"], keep="first")
)

summary = {
    "extreme_events": int(len(best)),
    "raw_matches": int(len(m)),
    "status_counts": best["status"].value_counts(dropna=False).to_dict(),
}
Path(a.out + ".summary.json").write_text(
    json.dumps(summary, indent=2, default=str)
)
print(json.dumps(summary, indent=2, default=str))
