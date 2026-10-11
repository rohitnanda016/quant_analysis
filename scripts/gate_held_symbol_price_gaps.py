#!/usr/bin/env python3
"""Fail closed when the known IBVENTURES held-series gap remains unresolved.

This is a data-integrity gate, not a price-repair algorithm. It never imputes
prices. The known interval is expected to contain official observations for
the fully-paid equity series; a long gap blocks publication of the artifact.
"""
import argparse
import json
from pathlib import Path

import pandas as pd


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prices", required=True)
    p.add_argument("--symbol", default="IBVENTURES")
    p.add_argument("--start", default="2018-06-01")
    p.add_argument("--end", default="2018-11-15")
    p.add_argument("--max-gap-days", type=int, default=15)
    p.add_argument("--report", default="results/price_quality/held_gap_gate.json")
    a = p.parse_args()

    usecols = ["date", "symbol"]
    df = pd.read_csv(a.prices, usecols=lambda c: c in usecols, low_memory=False)
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["symbol"] = df["symbol"].astype(str).str.strip().str.upper()
    start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
    d = (df.loc[(df["symbol"] == a.symbol.upper()) &
                df["date"].between(start, end), "date"]
           .dropna().drop_duplicates().sort_values())

    gaps = []
    if len(d) > 1:
        dates = d.reset_index(drop=True)
        for i in range(1, len(dates)):
            days = int((dates.iloc[i] - dates.iloc[i - 1]).days)
            if days > a.max_gap_days:
                gaps.append({
                    "previous_date": dates.iloc[i - 1].date().isoformat(),
                    "next_date": dates.iloc[i].date().isoformat(),
                    "calendar_days": days,
                })

    report = {
        "symbol": a.symbol.upper(),
        "window_start": a.start,
        "window_end": a.end,
        "observations": int(len(d)),
        "max_allowed_calendar_gap_days": a.max_gap_days,
        "unresolved_gaps": gaps,
        "status": "pass" if len(d) > 1 and not gaps else "blocked",
        "note": "No prices are imputed. Resolve gaps with verifiable exchange data or document an authoritative no-trading/suspension interval before relaxing this gate.",
    }
    out = Path(a.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if report["status"] != "pass":
        raise SystemExit("Held-symbol price-integrity gate blocked: unresolved IBVENTURES gap.")


if __name__ == "__main__":
    main()
