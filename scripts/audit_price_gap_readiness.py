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
    ledger_evidence_issues = []
    if not nt.empty:
        evidence_fields = {"verification_source", "evidence_reference"}
        if not evidence_fields.issubset(nt.columns):
            ledger_evidence_issues.append("Approved no-trade ledger lacks verification_source/evidence_reference.")
            nt = nt.iloc[0:0].copy()
        else:
            nt["verification_source"] = nt["verification_source"].astype(str).str.strip()
            nt["evidence_reference"] = nt["evidence_reference"].astype(str).str.strip()
            invalid_evidence = (
                nt["verification_source"].eq("")
                | nt["verification_source"].str.lower().isin(["nan", "nse daily bhavcopy eq universe"])
                | nt["evidence_reference"].eq("")
                | nt["evidence_reference"].str.lower().eq("nan")
            )
            if invalid_evidence.any():
                ledger_evidence_issues.append(
                    f"{int(invalid_evidence.sum())} approved no-trade row(s) lack independent evidence."
                )
            nt = nt.loc[~invalid_evidence].copy()
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
    archive_absence_pairs = int(repair.get("archive_absence_review_pairs", 0) or 0)
    min_bhavcopy_rows = int(repair.get("minimum_valid_bhavcopy_eq_rows", 0) or 0)
    archive_api = str(repair.get("archive_api", ""))

    post_summary = {}
    if args.post_adjustment_summary and Path(args.post_adjustment_summary).exists():
        post_summary = json.loads(Path(args.post_adjustment_summary).read_text())
    price_summary = {}
    if args.price_quality_summary and Path(args.price_quality_summary).exists():
        price_summary = json.loads(Path(args.price_quality_summary).read_text())

    if not price_summary:
        gap_blockers.append("Raw price-quality summary is missing; basic OHLC, duplicate and nonpositive-close checks have not passed.")
    else:
        basic_quality_fields = [
            "missing_ohlc", "nonpositive_close", "ohlc_order_issues",
            "negative_volume", "negative_turnover", "duplicate_date_symbol",
        ]
        invalid_quality = {
            key: int(price_summary.get(key, 0) or 0)
            for key in basic_quality_fields
            if int(price_summary.get(key, 0) or 0) != 0
        }
        if invalid_quality:
            gap_blockers.append(f"Basic raw price-quality checks failed: {invalid_quality}.")
    gap_blockers = []
    gap_blockers.extend(ledger_evidence_issues)
    if fetch_errors != 0:
        gap_blockers.append(f"{fetch_errors} daily bhavcopy date(s) failed; failed downloads are not no-trade evidence.")
    if min_bhavcopy_rows < 500:
        gap_blockers.append("Daily archive sanity threshold is missing or below 500 EQ rows; artifact cannot be used as verified no-trade evidence.")
    if "NSEArchives.bhavcopy_raw" not in archive_api:
        gap_blockers.append("Repair report does not prove use of the UDiFF-capable NSEArchives.bhavcopy_raw adapter; re-run with current repair code.")
    if target_pairs >= 0 and accounted < target_pairs:
        gap_blockers.append(f"Repair accounting mismatch: target_pairs={target_pairs}, accounted={accounted}.")
    if unresolved_fetch_pairs > 0:
        gap_blockers.append(f"{unresolved_fetch_pairs} candidate symbol/date pair(s) remain unresolved due to fetch errors.")
    if archive_absence_pairs > 0:
        gap_blockers.append(f"{archive_absence_pairs} symbol/date pairs are absent from parsed EQ bhavcopies but lack independent evidence of an active listing or suspension; review them before any carry-forward.")
    if missing_unverified:
        gap_blockers.append(f"{len(missing_unverified)} missing pair(s) in long internal gaps are neither observed nor verified no-trade.")

    missing_adjusted = post_summary.get("missing_adjusted_rows")
    continuity_events = post_summary.get("continuity_relevant_gt_50pct")
    corp_action_summary_available = bool(post_summary)
    corp_action_review = (not corp_action_summary_available) or (
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
        "corporate_action_continuity": ("NOT_RUN" if not corp_action_summary_available else "REVIEW_REQUIRED") if corp_action_review else "NO_REPORTED_RESIDUALS",
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
            "minimum_valid_bhavcopy_eq_rows": min_bhavcopy_rows,
            "archive_api": archive_api,
            "rows_added": repair.get("rows_added"),
            "verified_no_trade_pairs": repair.get("verified_no_trade_pairs"),
            "archive_absence_review_pairs": archive_absence_pairs,
            "already_present_alias_matches": repair.get("already_present_alias_matches"),
            "accounted_target_pairs": accounted,
        },
        "approved_no_trade_ledger_evidence_issues": ledger_evidence_issues,
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
