#!/usr/bin/env python3
"""Audit whether targeted internal price gaps were resolved from official sources.

Price rows must come from raw NSE observations. A verified no-trade ledger is
acceptable for valuation carry-forward but is never treated as an observed price.
Corporate-action and total-return limitations are reported separately.
"""
import argparse
import json
from pathlib import Path
import pandas as pd


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--repair-report", required=True)
    ap.add_argument("--verified-no-trade", required=True)
    ap.add_argument("--post-adjustment-summary", default="")
    ap.add_argument("--price-quality-summary", default="")
    ap.add_argument("--report", required=True)
    ap.add_argument("--min-gap-sessions", type=int, default=10)
    ap.add_argument("--symbol-map", default="data/input/verified_symbol_map.csv")
    args = ap.parse_args()

    p = pd.read_csv(args.prices, usecols=lambda c: c in {
        "date", "symbol", "requested_symbol", "series", "close"
    }, low_memory=False)
    p["date"] = pd.to_datetime(p["date"], errors="coerce")
    p["symbol"] = p["symbol"].astype(str).str.strip().str.upper()
    source_symbol = "requested_symbol" if "requested_symbol" in p.columns else "symbol"
    p[source_symbol] = p[source_symbol].astype(str).str.strip().str.upper()
    if "series" in p.columns:
        p = p[p["series"].astype(str).str.upper().str.strip().eq("EQ")].copy()
    p = p.dropna(subset=["date"])
    calendar = pd.DatetimeIndex(sorted(p["date"].unique()))
    date_to_i = {d: i for i, d in enumerate(calendar)}

    nt_path = Path(args.verified_no_trade)
    if not nt_path.exists():
        raise SystemExit(f"Verified no-trade ledger missing: {nt_path}")
    nt = pd.read_csv(nt_path, low_memory=False)
    if not {"date", "symbol", "status"}.issubset(nt.columns):
        raise SystemExit("Verified no-trade ledger must contain date, symbol, status")
    nt["date"] = pd.to_datetime(nt["date"], errors="coerce")
    nt["symbol"] = nt["symbol"].astype(str).str.strip().str.upper()
    nt = nt[nt["status"].eq("verified_no_trade")].dropna(subset=["date", "symbol"])
    no_trade = set(zip(nt["date"], nt["symbol"]))

    aliases = {}
    alias_path = Path(args.symbol_map)
    if alias_path.exists():
        amap = pd.read_csv(alias_path)
        for z in amap.itertuples():
            old = str(getattr(z, "old_symbol", "")).strip().upper()
            new = str(getattr(z, "new_symbol", "")).strip().upper()
            if old and new and old != "NAN" and new != "NAN":
                aliases[old] = new
                aliases[new] = new
    def terminal_alias(value):
        value = str(value).strip().upper()
        seen = set()
        while value in aliases and value not in seen:
            seen.add(value)
            nxt = aliases[value]
            if nxt == value:
                break
            value = nxt
        return value

    # Existing rows can arrive under the post-rename ticker even when the
    # acquisition/request symbol in the missing-gap audit is historical.
    observed_canonical_pairs = set(zip(
        p["date"],
        p["symbol"].map(terminal_alias)
    ))

    missing_unverified = []
    long_gap_spans = []
    for symbol, group in p.groupby(source_symbol, sort=False):
        idx = sorted({date_to_i[d] for d in group["date"].dropna().unique() if d in date_to_i})
        for left, right in zip(idx[:-1], idx[1:]):
            gap = right - left - 1
            if gap < args.min_gap_sessions:
                continue
            long_gap_spans.append({
                "symbol": str(symbol),
                "last_observed": calendar[left].date().isoformat(),
                "next_observed": calendar[right].date().isoformat(),
                "missing_sessions": int(gap),
            })
            for i in range(left + 1, right):
                dd = pd.Timestamp(calendar[i])
                resolved_alias = (dd, terminal_alias(symbol)) in observed_canonical_pairs
                if (dd, str(symbol)) not in no_trade and not resolved_alias:
                    missing_unverified.append({
                        "date": dd.date().isoformat(),
                        "symbol": str(symbol),
                        "previous_observed": calendar[left].date().isoformat(),
                        "next_observed": calendar[right].date().isoformat(),
                    })

    repair_path = Path(args.repair_report)
    if not repair_path.exists():
        raise SystemExit(f"Repair report missing: {repair_path}")
    repair = json.loads(repair_path.read_text())
    fetch_errors = int(repair.get("fetch_error_dates", -1))
    target_pairs = int(repair.get("target_symbol_date_pairs", -1))
    accounted = (
        int(repair.get("rows_added", 0))
        + int(repair.get("verified_no_trade_pairs", 0))
        + int(repair.get("already_present_alias_matches", 0))
    )
    unresolved_fetch_pairs = int(repair.get("unresolved_target_pairs_due_to_fetch_errors", -1))

    post_summary = {}
    if args.post_adjustment_summary and Path(args.post_adjustment_summary).exists():
        post_summary = json.loads(Path(args.post_adjustment_summary).read_text())
    price_summary = {}
    if args.price_quality_summary and Path(args.price_quality_summary).exists():
        price_summary = json.loads(Path(args.price_quality_summary).read_text())

    gap_blockers = []
    if fetch_errors != 0:
        gap_blockers.append(f"{fetch_errors} daily bhavcopy date(s) failed; failed downloads are not no-trade evidence.")
    if target_pairs >= 0 and accounted < target_pairs:
        gap_blockers.append(f"Repair accounting mismatch: target_pairs={target_pairs}, accounted={accounted}.")
    if unresolved_fetch_pairs > 0:
        gap_blockers.append(f"{unresolved_fetch_pairs} candidate symbol/date pair(s) remain unresolved due to fetch errors.")
    if missing_unverified:
        gap_blockers.append(f"{len(missing_unverified)} missing pair(s) in long internal gaps are neither observed nor verified no-trade.")

    missing_adjusted = post_summary.get("missing_adjusted_rows")
    continuity_events = post_summary.get("continuity_relevant_gt_50pct")
    corp_action_review = (
        missing_adjusted is not None and int(missing_adjusted) > 0
    ) or (
        continuity_events is not None and int(continuity_events) > 0
    )
    dividend_values = set(str(v).strip().lower() for v in
                          (price_summary.get("dividend_adjustment_status_counts") or {}).keys())
    dividend_status = "BLOCKED_NOT_TOTAL_RETURN"
    if dividend_values and dividend_values.issubset({"applied", "total_return", "dividend_adjusted"}):
        dividend_status = "PASS"

    report = {
        "gate": "FLUID-Q price-gap resolution and research-data readiness",
        "status": "PASS_PRICE_GAPS" if not gap_blockers else "BLOCKED",
        "price_gap_integrity": "PASS" if not gap_blockers else "BLOCKED",
        "price_return_research": "PROVISIONAL" if not gap_blockers else "BLOCKED",
        "total_return_readiness": dividend_status,
        "corporate_action_continuity": "REVIEW_REQUIRED" if corp_action_review else "NO_REPORTED_RESIDUALS",
        "date_min": str(calendar.min().date()) if len(calendar) else None,
        "date_max": str(calendar.max().date()) if len(calendar) else None,
        "raw_rows": int(len(p)),
        "symbols": int(p[source_symbol].nunique()),
        "repair": {
            "target_gap_spans": repair.get("internal_gap_spans_targeted"),
            "target_symbol_date_pairs": target_pairs,
            "bhavcopy_dates_attempted": repair.get("unique_bhavcopy_dates_attempted"),
            "bhavcopy_dates_parsed": repair.get("bhavcopy_dates_parsed"),
            "fetch_error_dates": fetch_errors,
            "rows_added": repair.get("rows_added"),
            "verified_no_trade_pairs": repair.get("verified_no_trade_pairs"),
            "already_present_alias_matches": repair.get("already_present_alias_matches"),
            "accounted_target_pairs": accounted,
        },
        "remaining_long_internal_gap_spans": int(len(long_gap_spans)),
        "remaining_unverified_gap_pairs": int(len(missing_unverified)),
        "sample_unverified_gap_pairs": missing_unverified[:100],
        "raw_price_quality_summary": price_summary,
        "post_adjustment_summary": post_summary,
        "blockers": gap_blockers,
        "limitations": [
            "PROVISIONAL price-return research is not production approval.",
            "Dividend adjustment has not been established as complete; do not describe these results as total-return performance.",
            "Any remaining large continuity events require event-level corporate-action reconciliation before interpreting strategy returns.",
            "The locked evaluation window must remain excluded from model selection and tuning."
        ],
    }
    out = Path(args.report)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({
        "status": report["status"],
        "price_return_research": report["price_return_research"],
        "total_return_readiness": report["total_return_readiness"],
        "corporate_action_continuity": report["corporate_action_continuity"],
        "target_pairs": target_pairs,
        "accounted_target_pairs": accounted,
        "fetch_error_dates": fetch_errors,
        "remaining_unverified_gap_pairs": len(missing_unverified),
        "blockers": gap_blockers,
    }, indent=2))
    if gap_blockers:
        raise SystemExit("FLUID-Q price-gap readiness gate blocked; inspect readiness report.")


if __name__ == "__main__":
    main()
