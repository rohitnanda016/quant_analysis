import argparse, json
from pathlib import Path
import pandas as pd

p = argparse.ArgumentParser()
p.add_argument("--extremes", required=True)
p.add_argument("--reconciliation", required=True)
p.add_argument("--adjusted", required=True)
p.add_argument("--outdir", required=True)
a = p.parse_args()

out = Path(a.outdir)
out.mkdir(parents=True, exist_ok=True)
ext = pd.read_csv(a.extremes, low_memory=False)
rec = pd.read_csv(a.reconciliation, low_memory=False)

# audit_price_quality.py emits canonical_symbol for extreme events because
# corporate-action adjustments are applied on canonical symbols. The
# reconciliation output calls that field "symbol", so normalize the event
# identifier before comparing adjusted continuity.
if "canonical_symbol" in ext.columns:
    ext["symbol"] = ext["canonical_symbol"]
elif "symbol" not in ext.columns:
    raise SystemExit(f"Extreme-return file has no canonical_symbol/symbol column: {list(ext.columns)}")

adj_cols = ["date", "canonical_symbol", "symbol", "prev_close", "close", "adjustment_factor"]
parts = []
for ch in pd.read_csv(a.adjusted, usecols=lambda c: c in adj_cols, chunksize=300000, low_memory=False):
    if "canonical_symbol" not in ch.columns:
        ch["canonical_symbol"] = ch["symbol"]
    parts.append(ch)
adj = pd.concat(parts, ignore_index=True)

ext["date"] = pd.to_datetime(ext["date"], errors="coerce")
rec["date"] = pd.to_datetime(rec["date"], errors="coerce")
adj["date"] = pd.to_datetime(adj["date"], errors="coerce")
ext["symbol"] = ext["symbol"].astype(str).str.upper().str.strip()
adj["canonical_symbol"] = adj["canonical_symbol"].astype(str).str.upper().str.strip()

for df in (ext, adj):
    for c in ["prev_close", "close", "adjustment_factor"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")

merged = ext[["date", "symbol", "prev_close", "close", "return"]].merge(
    adj[["date", "canonical_symbol", "prev_close", "close", "adjustment_factor"]].rename(
        columns={"canonical_symbol": "symbol"}
    ),
    on=["date", "symbol"], how="left", suffixes=("_raw", "_adj")
)
merged["adjusted_return"] = merged["close_adj"] / merged["prev_close_adj"] - 1.0
# Preserve event classification from the reconciliation layer.
rec_cols = ["date", "symbol", "status"]
if "event_class" in rec.columns:
    rec_cols.append("event_class")
merged = merged.merge(rec[rec_cols], on=["date", "symbol"], how="left")

# A >50% move on the first observed trading day is a series-start/listing
# effect, not a continuity break.
first_dates = adj.groupby("canonical_symbol")["date"].min().rename("series_start_date").reset_index()
first_dates = first_dates.rename(columns={"canonical_symbol": "symbol"})
merged = merged.merge(first_dates, on="symbol", how="left")
merged["series_start"] = merged["date"].eq(merged["series_start_date"])
merged["continuity_relevant"] = ~merged["series_start"]
merged["abs_adjusted_return"] = merged["adjusted_return"].abs()
merged["abs_raw_return"] = merged["return"].abs()

summary = {
    "extreme_events": int(len(merged)),
    "matched_adjusted_rows": int(merged["close_adj"].notna().sum()),
    "missing_adjusted_rows": int(merged["close_adj"].isna().sum()),
    "raw_abs_return_gt_50pct": int((merged["abs_raw_return"] > 0.50).sum()),
    "adjusted_abs_return_gt_50pct": int((merged["abs_adjusted_return"] > 0.50).sum()),
    "continuity_relevant_gt_50pct": int(((merged["abs_adjusted_return"] > 0.50) & merged["continuity_relevant"]).sum()),
    "series_start_events": int(merged["series_start"].sum()),
    "adjusted_abs_return_le_20pct": int((merged["abs_adjusted_return"] <= 0.20).sum()),
    "adjusted_abs_return_le_10pct": int((merged["abs_adjusted_return"] <= 0.10).sum()),
    "adjusted_abs_return_le_5pct": int((merged["abs_adjusted_return"] <= 0.05).sum()),
    "median_abs_adjusted_return": float(merged["abs_adjusted_return"].median()),
    "median_abs_raw_return": float(merged["abs_raw_return"].median()),
}

by_status = merged.groupby("status", dropna=False).agg(
    events=("symbol", "size"),
    median_abs_adjusted_return=("abs_adjusted_return", "median"),
    max_abs_adjusted_return=("abs_adjusted_return", "max"),
    adjusted_gt_50pct=("abs_adjusted_return", lambda s: int((s > .50).sum())),
    adjusted_le_10pct=("abs_adjusted_return", lambda s: int((s <= .10).sum())),
).reset_index()

merged[merged["close_adj"].isna()].sort_values(["date", "symbol"]).to_csv(
    out / "missing_adjusted_rows.csv", index=False
)
merged[(merged["abs_adjusted_return"] > 0.50) & merged["continuity_relevant"]].sort_values(
    ["abs_adjusted_return", "date"], ascending=[False, True]
).to_csv(out / "continuity_relevant_extremes_gt_50pct.csv", index=False)

merged.sort_values(["abs_adjusted_return", "date"], ascending=[False, True]).to_csv(
    out / "post_adjustment_extreme_events.csv", index=False
)
by_status.to_csv(out / "post_adjustment_by_status.csv", index=False)
(out / "post_adjustment_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
print(by_status.to_string(index=False))
