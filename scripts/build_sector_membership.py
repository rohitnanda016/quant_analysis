#!/usr/bin/env python3
"""Build a point-in-time single-sector classification from NSE sector-index membership.

The upstream dataset contains overlapping sector indices (e.g. Bank and Financial
Services). V1.1 therefore uses an explicit, deterministic precedence order rather
than pretending the source is a mutually-exclusive industry classification.

Half-open intervals are preserved: [valid_from, valid_to).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

SECTOR_PRIORITY = [
    ("Nifty Private Bank", "Private Bank"),
    ("Nifty PSU Bank", "PSU Bank"),
    ("Nifty Bank", "Bank"),
    ("Nifty IT", "IT"),
    ("Nifty FMCG", "FMCG"),
    ("Nifty Pharma", "Pharma"),
    ("Nifty Auto", "Auto"),
    ("Nifty Metal", "Metal"),
    ("Nifty Realty", "Realty"),
    ("Nifty Healthcare Index", "Healthcare"),
    ("Nifty Consumer Durables", "Consumer Durables"),
    ("Nifty Oil & Gas", "Oil & Gas"),
    ("Nifty Energy", "Energy"),
    ("Nifty Media", "Media"),
    ("Nifty Financial Services", "Financial Services"),
]
SECTOR_INDEX_TO_LABEL = dict(SECTOR_PRIORITY)


def load_intervals(path: str) -> pd.DataFrame:
    x = pd.read_csv(path, low_memory=False)
    required = {"index_name", "symbol", "valid_from", "valid_to"}
    missing = required - set(x.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")
    x["index_name"] = x["index_name"].astype(str).str.strip()
    x["symbol"] = x["symbol"].astype(str).str.upper().str.strip()
    x["valid_from"] = pd.to_datetime(x["valid_from"], errors="coerce")
    x["valid_to"] = pd.to_datetime(x["valid_to"], errors="coerce")
    x = x.dropna(subset=["symbol", "valid_from"])
    return x


def intersect_intervals(a: pd.DataFrame, b: pd.DataFrame) -> pd.DataFrame:
    """Return pairwise interval intersections by symbol.

    Inputs must use symbol/valid_from/valid_to. The output is a conservative
    intersection, so a sector classification can never extend beyond the
    Nifty 500 PIT membership interval.
    """
    rows = []
    b_by_symbol = {s: g for s, g in b.groupby("symbol", sort=False)}
    for symbol, sg in a.groupby("symbol", sort=False):
        bg = b_by_symbol.get(symbol)
        if bg is None:
            continue
        for _, r in sg.iterrows():
            candidates = bg[(bg.valid_from < r.valid_to) if pd.notna(r.valid_to) else pd.Series(True, index=bg.index)]
            if pd.notna(r.valid_to):
                candidates = bg[(bg.valid_from < r.valid_to) & (bg.valid_to.isna() | (bg.valid_to > r.valid_from))]
            else:
                candidates = bg[(bg.valid_to.isna()) | (bg.valid_to > r.valid_from)]
            for _, q in candidates.iterrows():
                start = max(r.valid_from, q.valid_from)
                ends = [z for z in (r.valid_to, q.valid_to) if pd.notna(z)]
                end = min(ends) if ends else pd.NaT
                if pd.notna(end) and start >= end:
                    continue
                rows.append((symbol, r.index_name, start, end, r.source if "source" in r else "unknown"))
    return pd.DataFrame(rows, columns=["symbol", "index_name", "valid_from", "valid_to", "source"])


def resolve_precedence(overlaps: pd.DataFrame) -> pd.DataFrame:
    rank = {name: i for i, (name, _) in enumerate(SECTOR_PRIORITY)}
    rows = []
    for symbol, g in overlaps.groupby("symbol", sort=False):
        boundaries = sorted(set(g["valid_from"].tolist()) | set(g["valid_to"].dropna().tolist()))
        if len(boundaries) == 0:
            continue
        for i, start in enumerate(boundaries):
            end = boundaries[i + 1] if i + 1 < len(boundaries) else pd.NaT
            active = g[(g.valid_from <= start) & (g.valid_to.isna() | (g.valid_to > start))]
            if active.empty:
                continue
            active = active.assign(_priority=active.index_name.map(rank).fillna(9999))
            winner = active.sort_values(["_priority", "index_name"]).iloc[0]
            rows.append({
                "symbol": symbol,
                "sector": SECTOR_INDEX_TO_LABEL[winner.index_name],
                "sector_index": winner.index_name,
                "valid_from": start,
                "valid_to": end,
                "source": winner.source,
            })
    out = pd.DataFrame(rows)
    if out.empty:
        return out
    # Coalesce adjacent intervals with identical classification and source.
    out = out.sort_values(["symbol", "valid_from", "valid_to"], na_position="last").reset_index(drop=True)
    merged = []
    for _, r in out.iterrows():
        if merged:
            p = merged[-1]
            contiguous = pd.notna(p["valid_to"]) and p["valid_to"] == r["valid_from"]
            if contiguous and all(p[k] == r[k] for k in ["symbol", "sector", "sector_index", "source"]):
                p["valid_to"] = r["valid_to"]
                continue
        merged.append(r.to_dict())
    return pd.DataFrame(merged)


def coverage_at_dates(sector: pd.DataFrame, nifty500: pd.DataFrame, dates: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for d in dates:
        universe = nifty500[(nifty500.valid_from <= d) & (nifty500.valid_to.isna() | (nifty500.valid_to > d))]
        members = set(universe.symbol)
        classified = sector[(sector.valid_from <= d) & (sector.valid_to.isna() | (sector.valid_to > d))]
        classified = classified[classified.symbol.isin(members)]
        rows.append({
            "date": d,
            "nifty500_members": len(members),
            "classified_members": classified.symbol.nunique(),
            "classified_pct": classified.symbol.nunique() / len(members) if members else 0.0,
            "unclassified_members": len(members - set(classified.symbol)),
            "sectors_present": classified.sector.nunique(),
        })
    return pd.DataFrame(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--membership", required=True, help="Full upstream index_membership_history.csv")
    ap.add_argument("--nifty500", required=True, help="PIT Nifty 500 membership used by this project")
    ap.add_argument("--out", required=True)
    ap.add_argument("--coverage-start", default="2017-01-01")
    ap.add_argument("--coverage-end", default="2026-08-31")
    a = ap.parse_args()

    source = load_intervals(a.membership)
    source = source[source.index_name.isin(SECTOR_INDEX_TO_LABEL)]
    source = source[(source.valid_from < pd.Timestamp(a.coverage_end)) & (source.valid_to.isna() | (source.valid_to > pd.Timestamp(a.coverage_start)))].copy()

    n = pd.read_csv(a.nifty500)
    n.columns = [str(c).strip().lower().replace(" ", "_") for c in n.columns]
    if "symbol" not in n.columns:
        raise ValueError("Nifty 500 membership must contain symbol")
    if "effective_date" not in n.columns:
        raise ValueError("Nifty 500 membership must contain effective_date")
    n["symbol"] = n["symbol"].astype(str).str.upper().str.strip()
    n["valid_from"] = pd.to_datetime(n["effective_date"], errors="coerce")
    if "end_date" in n.columns:
        n["valid_to"] = pd.to_datetime(n["end_date"], errors="coerce")
    else:
        raise ValueError("Nifty 500 membership must contain end_date")
    n = n.dropna(subset=["symbol", "valid_from"])

    # Restrict the source to the backtest's PIT Nifty 500 universe.
    overlap = intersect_intervals(source, n)
    sector = resolve_precedence(overlap)
    if sector.empty:
        raise ValueError("No PIT sector classifications were produced")

    start = pd.Timestamp(a.coverage_start)
    end = pd.Timestamp(a.coverage_end)
    sector = sector[(sector.valid_from < end) & (sector.valid_to.isna() | (sector.valid_to > start))].copy()

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    sector.to_csv(out, index=False)

    # Annual June-30 snapshots are a stable coverage diagnostic, not a backtest input.
    dates = pd.date_range(start.normalize(), end.normalize(), freq="YS") + pd.Timedelta(days=180)
    dates = pd.DatetimeIndex([min(d, end) for d in dates])
    cov = coverage_at_dates(sector, n, dates)
    cov.to_csv(out.with_name("sector_coverage.csv"), index=False)

    manifest = {
        "source_repository": "aditya-jha/nse-historical-membership",
        "source_commit": "0e9f58c4d457faf0e7ad3db4f4c1449e697e23e0",
        "coverage_start": a.coverage_start,
        "coverage_end": a.coverage_end,
        "sector_indices": [x[0] for x in SECTOR_PRIORITY],
        "precedence": [{"index": x, "sector": y, "priority": i + 1} for i, (x, y) in enumerate(SECTOR_PRIORITY)],
        "classification_method": "PIT intersection with Nifty 500, then deterministic sector-index precedence; intervals are half-open [valid_from, valid_to).",
        "overlap_rows": int(len(overlap)),
        "output_rows": int(len(sector)),
        "classified_symbols": int(sector.symbol.nunique()),
        "coverage_summary": cov.to_dict(orient="records"),
    }
    out.with_name("sector_membership_manifest.json").write_text(json.dumps(manifest, indent=2, default=str))
    print(json.dumps(manifest, indent=2, default=str))


if __name__ == "__main__":
    main()
