import argparse, json, re
from pathlib import Path
import pandas as pd

try:
    from scripts.symbol_lineage import load_symbol_rename_rows, terminal_symbol_aliases
except ModuleNotFoundError:
    from symbol_lineage import load_symbol_rename_rows, terminal_symbol_aliases

def parse_factor(purpose):
    p = str(purpose or "").upper()
    factors = []
    action_types = []

    for x, y in re.findall(r"BONUS\s+(\d+)\s*:\s*(\d+)", p):
        x, y = int(x), int(y)
        if y > 0:
            factors.append((x + y) / y)
            action_types.append("bonus")

    split_matches = re.findall(
        r"FROM\s+RS\.?\s*([0-9.]+).*?TO\s+R(?:S|E)?\.?\s*([0-9.]+)", p
    )
    if split_matches and any(k in p for k in ("SPLIT", "SPLT", "CONSOLIDATION", "SUB-DIVISION")):
        old, new = map(float, split_matches[-1])
        if new > 0:
            factors.append(old / new)
            action_types.append("split_or_consolidation")

    for old, new in re.findall(
        r"(?:FACE\s+VALUE\s+)?SPLIT\s+RS\.?\s*([0-9.]+).*?TO\s+R(?:S|E)?\.?\s*([0-9.]+)",
        p,
    ):
        old, new = float(old), float(new)
        if new > 0:
            factors.append(old / new)
            action_types.append("split_or_consolidation")

    if not factors:
        return None, None
    factor = 1.0
    for f in factors:
        factor *= f
    return factor, "+".join(dict.fromkeys(action_types))

def classify_event(purpose, action_type):
    p = str(purpose or "").upper()
    a = str(action_type or "").lower()
    if any(k in p for k in ("DEMERGER", "DE-MERGER", "SCHEME OF ARRANGEMENT", "AMALGAMATION", "HIVE-OFF", "SPIN OFF", "SPIN-OFF")):
        return "RESTRUCTURING"
    if "MERGER" in p and "DEMERGER" not in p:
        return "MERGER"
    if "bonus" in a and "split_or_consolidation" in a:
        return "BONUS_SPLIT"
    if "bonus" in a:
        return "BONUS"
    if "split_or_consolidation" in a:
        return "SPLIT_OR_CONSOLIDATION"
    if any(k in p for k in ("RIGHT", "RIGHTS ISSUE")):
        return "RIGHTS"
    if "DIVIDEND" in p:
        return "DIVIDEND"
    return "OTHER_CORPORATE_ACTION"

def aliases(path, supplement):
    base = path if path and Path(path).exists() else None
    if not base and not Path(supplement).exists():
        return {}
    return terminal_symbol_aliases(load_symbol_rename_rows(base, supplement))

def first_existing_series(df, names):
    """Choose the first non-empty field on each row, not the first existing column."""
    result = pd.Series("", index=df.index, dtype="object")
    for name in names:
        if name not in df.columns:
            continue
        candidate = df[name].fillna("").astype(str).str.strip()
        candidate = candidate.mask(candidate.str.lower().isin(["", "nan", "none", "<na>"]), "")
        result = result.where(result.ne(""), candidate)
    return result

p = argparse.ArgumentParser()
p.add_argument("--extremes", required=True)
p.add_argument("--actions", required=True)
p.add_argument("--symbol-map", required=False, default="")
p.add_argument("--symbol-map-supplement", default="data/reference/nse_historical_symbol_changes.csv")
p.add_argument("--out", required=True)
p.add_argument("--supplemental-actions", default="data/input/verified_manual_corporate_actions.csv")
p.add_argument("--verified-events", default="data/input/verified_corporate_events.csv")
a = p.parse_args()

e = pd.read_csv(a.extremes)
e["date"] = pd.to_datetime(e["date"], errors="coerce")
e["symbol"] = e["canonical_symbol"].astype(str).str.upper().str.strip()
e["observed_factor"] = pd.to_numeric(e["prev_close"], errors="coerce") / pd.to_numeric(e["close"], errors="coerce")

ca = pd.read_csv(a.actions)
if Path(a.supplemental_actions).exists():
    sup = pd.read_csv(a.supplemental_actions)
    for c in ["bc_end_date","bc_start_date","ca_broadcast_date","comp","isin","ind","nd_end_date","nd_start_date","record_date","face_value"]:
        if c not in sup.columns:
            sup[c] = ""
    sup = sup.rename(columns={"record_date":"rec_date","face_value":"face_val"})
    ca = pd.concat([ca, sup], ignore_index=True, sort=False)

ca.columns = [str(c).strip().lower().replace(" ", "_").replace("-", "_") for c in ca.columns]
# Keep optional fields available for minimal test fixtures and alternate historical exports.
for optional_column in ("rec_date", "face_val"):
    if optional_column not in ca.columns:
        ca[optional_column] = ""
ca["symbol"] = ca["symbol"].astype(str).str.upper().str.strip()
ca["ex_date"] = pd.to_datetime(ca["ex_date"], errors="coerce")
ca["purpose"] = first_existing_series(ca, ["purpose", "subject"])
if ca.empty:
    ca["inferred_factor"] = pd.Series(dtype="float64")
    ca["action_type"] = pd.Series(dtype="object")
else:
    ca[["inferred_factor", "action_type"]] = ca["purpose"].apply(lambda x: pd.Series(parse_factor(x)))
ca["event_class"] = ca.apply(lambda r: classify_event(r["purpose"], r["action_type"]), axis=1)

amap = aliases(a.symbol_map, a.symbol_map_supplement)
e["lookup_symbol"] = e["symbol"].map(lambda x: amap.get(x, x))
ca["lookup_symbol"] = ca["symbol"].map(lambda x: amap.get(x, x))

# The same documented action can appear in both the NSE feed and the manual
# evidence ledger. Deduplicate equivalent parsed factors after ticker aliases
# are normalized, or identical 5x/10x actions could be multiplied twice.
ca["_factor"] = pd.to_numeric(ca["inferred_factor"], errors="coerce")
parsed_action = ca["_factor"].notna()
ca_parsed = ca.loc[parsed_action].drop_duplicates(
    subset=["lookup_symbol", "ex_date", "_factor", "action_type"], keep="first"
)
ca_unparsed = ca.loc[~parsed_action]
ca = pd.concat([ca_parsed, ca_unparsed], axis=0).sort_index()
ca["has_action"] = ca["purpose"].str.len().fillna(0).gt(0)
ca["_factor"] = pd.to_numeric(ca["inferred_factor"], errors="coerce")
ca["_factor_for_product"] = ca["_factor"].fillna(1.0)
ca_group = (
    ca.groupby(["lookup_symbol", "ex_date"], dropna=False)
      .agg(
          symbol_action=("lookup_symbol", "first"),
          purpose=("purpose", lambda s: " / ".join(dict.fromkeys(str(x) for x in s if str(x).strip() and str(x).lower() != "nan"))),
          inferred_factor=("_factor_for_product", "prod"),
          has_action=("has_action", "any"),
          factor_count=("_factor", lambda s: int(s.notna().sum())),
          action_type=("action_type", lambda s: "+".join(dict.fromkeys(str(x) for x in s if str(x).strip() and str(x).lower() != "nan"))),
          event_class=("event_class", lambda s: "+".join(dict.fromkeys(str(x) for x in s if str(x).strip() and str(x).lower() != "nan"))),
          record_date=("rec_date", "first"),
          face_value=("face_val", "first"),
      )
      .reset_index()
)
ca_group.loc[ca_group["factor_count"] == 0, "inferred_factor"] = float("nan")

m = e.merge(ca_group, how="left", left_on=["lookup_symbol", "date"], right_on=["lookup_symbol", "ex_date"], suffixes=("_extreme", "_action"))
m["observed_ratio_deviation"] = m["observed_factor"] / m["inferred_factor"] - 1
# Retain the previous field as a compatibility diagnostic. A difference between
# previous-close/close and a split/bonus factor includes the genuine market move
# on the ex-date; it is not, by itself, evidence that the action factor is wrong.
m["factor_error"] = m["observed_ratio_deviation"].abs()
prev_close = pd.to_numeric(m["prev_close"], errors="coerce")
close = pd.to_numeric(m["close"], errors="coerce")
m["factor_adjusted_return"] = close * m["inferred_factor"] / prev_close - 1
m["status"] = "NO_EXACT_ACTION"
# Empty action joins may infer event_class as float64; later verified-event
# labels are strings, so normalize the dtype before row-wise dispositions.
m["event_class"] = m["event_class"].astype("object")

has = m["has_action"].fillna(False)
m.loc[has, "status"] = "ACTION_ON_DATE"

has_parsed_split_bonus_factor = (
    has
    & m["inferred_factor"].notna()
    & m["action_type"].fillna("").astype(str).str.len().gt(0)
)
m.loc[has_parsed_split_bonus_factor, "status"] = "ACTION_FACTOR_IDENTIFIED"
m.loc[has & m["inferred_factor"].isna(), "status"] = "ACTION_ON_DATE_NON_PRICE_FACTOR"

# Apply explicit event dispositions only when no same-date action was matched.
# This separates IPO listing-session price discovery and documented genuine
# market moves from true corporate-action gaps; it never synthesizes a factor.
m["verified_event_type"] = ""
m["verified_event_treatment"] = ""
m["verified_event_source"] = ""
m["verified_event_confidence"] = ""
m["verified_event_notes"] = ""
verified_path = Path(a.verified_events)
if verified_path.exists():
    ve = pd.read_csv(verified_path, low_memory=False)
    required = {"symbol", "event_date", "event_type", "treatment"}
    if required.issubset(ve.columns):
        ve["symbol"] = ve["symbol"].astype(str).str.upper().str.strip()
        ve["event_date"] = pd.to_datetime(ve["event_date"], errors="coerce", format="mixed")
        ve["lookup_symbol"] = ve["symbol"].map(lambda x: amap.get(x, x))
        ve = ve.dropna(subset=["event_date"])
        ve_map = {}
        for _, event in ve.iterrows():
            ve_map[(str(event["lookup_symbol"]), pd.Timestamp(event["event_date"]))] = event
        for row_idx in m.index:
            event = ve_map.get((str(m.at[row_idx, "lookup_symbol"]), pd.Timestamp(m.at[row_idx, "date"])))
            if event is None:
                continue
            event_type = str(event.get("event_type", "")).strip().upper()
            treatment = str(event.get("treatment", "")).strip().lower()
            m.at[row_idx, "verified_event_type"] = event_type
            m.at[row_idx, "verified_event_treatment"] = treatment
            m.at[row_idx, "verified_event_source"] = str(event.get("source", ""))
            m.at[row_idx, "verified_event_confidence"] = str(event.get("confidence", ""))
            m.at[row_idx, "verified_event_notes"] = str(event.get("notes", ""))

            # Evidence is attached to every matching row. Only replace
            # NO_EXACT_ACTION when there is no same-date parsed action match.
            if str(m.at[row_idx, "status"]) != "NO_EXACT_ACTION":
                continue
            if event_type == "IPO_LISTING_DAY":
                m.at[row_idx, "status"] = "LISTING_DAY_PRICE_DISCOVERY"
                m.at[row_idx, "event_class"] = "IPO_LISTING"
            elif event_type == "GENUINE_MARKET_MOVE":
                if "pending_source_price_check" in treatment:
                    m.at[row_idx, "status"] = "GENUINE_MARKET_MOVE_PRICE_RECHECK"
                else:
                    m.at[row_idx, "status"] = "GENUINE_MARKET_MOVE_CONFIRMED"
                m.at[row_idx, "event_class"] = "GENUINE_MARKET_MOVE"
            elif event_type in {"SPLIT", "BONUS", "SPLIT_OR_BONUS"}:
                # A documented event without a parseable, same-day factor must
                # remain an action-evidence issue rather than being called no action.
                m.at[row_idx, "status"] = "VERIFIED_SPLIT_ACTION_FACTOR_REVIEW"
                m.at[row_idx, "event_class"] = event_type

# Add nearby corporate-action context for manual review. Do not promote a
# nearby event to an exact match: ex-date proximity alone is not proof that
# the event explains the observed price discontinuity.
m["nearby_action_date"] = ""
m["nearby_action_distance_days"] = pd.NA
m["nearby_action_purpose"] = ""
m["nearby_action_class"] = ""
m["nearby_action_factor"] = pd.NA

review_mask = m["status"].isin(["NO_EXACT_ACTION", "ACTION_ON_DATE_NON_PRICE_FACTOR"])
nearby_index = {}
for lookup_symbol, group in ca_group.dropna(subset=["ex_date"]).groupby("lookup_symbol", sort=False):
    nearby_index[str(lookup_symbol)] = group.sort_values("ex_date")

for row_idx in m.index[review_mask]:
    symbol = str(m.at[row_idx, "lookup_symbol"])
    event_date = m.at[row_idx, "date"]
    candidates = nearby_index.get(symbol)
    if candidates is None or pd.isna(event_date):
        continue
    delta = (candidates["ex_date"] - event_date).dt.days
    nearby = candidates.loc[delta.abs().le(5)].copy()
    if nearby.empty:
        continue
    nearby["_distance"] = (nearby["ex_date"] - event_date).dt.days
    nearby["_abs_distance"] = nearby["_distance"].abs()
    # Prefer the closest action; for ties prefer the one with a parsed factor.
    nearby["_has_factor"] = nearby["inferred_factor"].notna().astype(int)
    nearest = nearby.sort_values(
        ["_abs_distance", "_has_factor", "ex_date"],
        ascending=[True, False, True],
        kind="stable",
    ).iloc[0]
    m.at[row_idx, "nearby_action_date"] = nearest["ex_date"].date().isoformat()
    m.at[row_idx, "nearby_action_distance_days"] = int(nearest["_distance"])
    m.at[row_idx, "nearby_action_purpose"] = str(nearest["purpose"])
    m.at[row_idx, "nearby_action_class"] = str(nearest["event_class"])
    m.at[row_idx, "nearby_action_factor"] = nearest["inferred_factor"]

cols = ["symbol","date","prev_close","close","return","observed_factor","inferred_factor","observed_ratio_deviation","factor_error","factor_adjusted_return","symbol_action","purpose","event_class","ex_date","record_date","face_value","action_type","status","verified_event_type","verified_event_treatment","verified_event_source","verified_event_confidence","verified_event_notes","nearby_action_date","nearby_action_distance_days","nearby_action_purpose","nearby_action_class","nearby_action_factor"]
cols = [c for c in cols if c in m.columns]
m[cols].sort_values(["date","symbol"]).to_csv(a.out, index=False)

rank = {"ACTION_FACTOR_IDENTIFIED":0,"LISTING_DAY_PRICE_DISCOVERY":0,"GENUINE_MARKET_MOVE_CONFIRMED":0,"GENUINE_MARKET_MOVE_PRICE_RECHECK":0,"VERIFIED_SPLIT_ACTION_FACTOR_REVIEW":1,"ACTION_ON_DATE_NON_PRICE_FACTOR":1,"ACTION_ON_DATE":2,"NO_EXACT_ACTION":3}
m["_rank"] = m["status"].map(rank).fillna(99)
best = m.sort_values(["symbol","date","_rank","factor_error"], na_position="last").drop_duplicates(["symbol","date"], keep="first")

summary = {
    "extreme_events": int(len(best)),
    "raw_matches": int(len(m)),
    "status_counts": best["status"].value_counts(dropna=False).to_dict(),
    "event_class_counts": best["event_class"].fillna("NO_MATCH").value_counts(dropna=False).to_dict(),
}
Path(a.out + ".summary.json").write_text(json.dumps(summary, indent=2, default=str))
print(json.dumps(summary, indent=2, default=str))
