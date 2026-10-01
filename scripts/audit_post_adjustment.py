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

adj_cols = ["date", "symbol", "prev_close", "close", "adjustment_factor"]
parts = []
for ch in pd.read_csv(a.adjusted, usecols=lambda c: c in adj_cols, chunksize=300000, low_memory=False):
    parts.append(ch)
adj = pd.concat(parts, ignore_index=True)

ext["date"] = pd.to_datetime(ext["date"], errors="coerce")
adj["date"] = pd.to_datetime(adj["date"], errors="coerce")
ext["symbol"] = ext["symbol"].astype(str).str.upper().str.strip()
adj["symbol"] = adj["symbol"].astype(str).str.upper().str.strip()

for df in (ext, adj):
    for c in ["prev_close", "close", "adjustment_factor"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")

merged = ext[["date", "symbol", "prev_close", "close", "return"]].merge(
    adj[["date", "symbol", "prev_close", "close", "adjustment_factor"]],
    on=["date", "symbol"], how="left", suffixes=("_raw", "_adj")
)
merged["adjusted_return"] = merged["close_adj"] / merged["prev_close_adj"] - 1.0
merged = merged.merge(rec[["date", "symbol", "status"]], on=["date", "symbol"], how="left")
merged["abs_adjusted_return"] = merged["adjusted_return"].abs()
merged["abs_raw_return"] = merged["return"].abs()

summary = {
    "extreme_events": int(len(merged)),
    "matched_adjusted_rows": int(merged["close_adj"].notna().sum()),
    "missing_adjusted_rows": int(merged["close_adj"].isna().sum()),
    "raw_abs_return_gt_50pct": int((merged["abs_raw_return"] > 0.50).sum()),
    "adjusted_abs_return_gt_50pct": int((merged["abs_adjusted_return"] > 0.50).sum()),
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

merged.sort_values(["abs_adjusted_return", "date"], ascending=[False, True]).to_csv(
    out / "post_adjustment_extreme_events.csv", index=False
)
by_status.to_csv(out / "post_adjustment_by_status.csv", index=False)
(out / "post_adjustment_summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps(summary, indent=2))
print(by_status.to_string(index=False))
