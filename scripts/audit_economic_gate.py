#!/usr/bin/env python3
"""Audit known return-series limitations and protect the locked future holdout."""
import argparse
import json
from pathlib import Path
import pandas as pd

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--holdout-start", default="2026-09-01")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()
    holdout_start = pd.Timestamp(args.holdout_start)
    rows = 0
    min_date = max_date = None
    holdout_rows = 0
    dividend_status_counts = {}
    adjustment_method_counts = {}
    symbols = set()
    for ch in pd.read_csv(args.prices, usecols=lambda c: c in {
        "date", "symbol", "canonical_symbol", "dividend_adjustment", "adjustment_method"
    }, chunksize=250000, low_memory=False):
        rows += len(ch)
        dates = pd.to_datetime(ch["date"], errors="coerce")
        valid = dates.dropna()
        if not valid.empty:
            lo, hi = valid.min(), valid.max()
            min_date = lo if min_date is None else min(min_date, lo)
            max_date = hi if max_date is None else max(max_date, hi)
            holdout_rows += int((valid >= holdout_start).sum())
        sym_col = "canonical_symbol" if "canonical_symbol" in ch.columns else "symbol"
        if sym_col in ch.columns:
            symbols.update(ch[sym_col].dropna().astype(str).unique().tolist())
        if "dividend_adjustment" in ch.columns:
            counts = ch["dividend_adjustment"].fillna("MISSING").astype(str).value_counts()
            for k, v in counts.items():
                dividend_status_counts[k] = dividend_status_counts.get(k, 0) + int(v)
        if "adjustment_method" in ch.columns:
            counts = ch["adjustment_method"].fillna("MISSING").astype(str).value_counts()
            for k, v in counts.items():
                adjustment_method_counts[k] = adjustment_method_counts.get(k, 0) + int(v)

    dividend_applied = bool(dividend_status_counts) and all(
        k.strip().lower() in {"applied", "total_return", "dividend_adjusted"}
        for k, v in dividend_status_counts.items() if v > 0
    )
    holdout_clean = holdout_rows == 0 and (max_date is None or max_date < holdout_start)
    blockers = []
    if not dividend_applied:
        blockers.append("Dividend/total-return adjustment is not established; current series is not a complete total-return series.")
    if not holdout_clean:
        blockers.append(f"Research input contains {holdout_rows} rows on/after locked holdout start {holdout_start.date()}.")
    report = {
        "gate": "FLUID-Q data integrity and holdout protection",
        "status": "PASS" if not blockers else "BLOCKED",
        "input": args.prices,
        "rows": rows,
        "unique_symbols": len(symbols),
        "date_min": str(min_date.date()) if min_date is not None else None,
        "date_max": str(max_date.date()) if max_date is not None else None,
        "dividend_adjustment_status_counts": dividend_status_counts,
        "adjustment_method_counts": adjustment_method_counts,
        "dividend_total_return_gate": "PASS" if dividend_applied else "BLOCKED",
        "locked_holdout_start": str(holdout_start.date()),
        "holdout_rows_in_research_input": holdout_rows,
        "holdout_protection": "PASS" if holdout_clean else "FAIL",
        "blockers": blockers,
        "interpretation": "A successful audit job means the report was generated, not that the strategy passed promotion criteria."
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if not holdout_clean:
        raise SystemExit(2)

if __name__ == "__main__":
    main()
