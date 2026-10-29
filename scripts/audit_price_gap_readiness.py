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

try:
    from scripts.membership_scope import build_membership_session_windows, in_membership_research_window
    from scripts.symbol_lineage import load_symbol_rename_rows, terminal_symbol_aliases
    from scripts.approved_price_gap_exclusions import (
        load_scope_exclusions, match_scope_exclusions_to_archive_absences,
    )
except ModuleNotFoundError:
    from membership_scope import build_membership_session_windows, in_membership_research_window
    from symbol_lineage import load_symbol_rename_rows, terminal_symbol_aliases
    from approved_price_gap_exclusions import (
        load_scope_exclusions, match_scope_exclusions_to_archive_absences,
    )

PRICE_CONTINUITY_SERIES = {"EQ", "BE", "BZ"}


def accounting_summary(target_pairs, rows_added, verified_no_trade_pairs, alias_matches,
                      archive_absence_pairs, fetch_error_pairs, alternate_series_pairs=0):
    """Count each targeted pair in exactly one reported disposition bucket."""
    buckets = {
        "observed_added": int(rows_added),
        "observed_alternate_series": int(alternate_series_pairs),
        "verified_no_trade": int(verified_no_trade_pairs),
        "already_present_alias": int(alias_matches),
        "unresolved_archive_absence": int(archive_absence_pairs),
        "unresolved_fetch_error": int(fetch_error_pairs),
    }
    return {"buckets": buckets, "accounted": sum(buckets.values()), "target_pairs": int(target_pairs),
            "mismatch": sum(buckets.values()) != int(target_pairs)}


def unresolved_archive_absence_details(path, scope_matched_pairs):
    """Return exact unresolved archive-absence pairs not covered by valid scope waivers.

    This is diagnostic only: it never changes readiness decisions or converts an
    absence into a price/no-trade observation.
    """
    path = Path(path)
    if not path.is_file():
        return []
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not {"date", "symbol", "status"}.issubset(frame.columns):
        return []
    details = set()
    for _, row in frame.iterrows():
        if row["status"].strip().lower() != "unresolved_archive_absence":
            continue
        date = pd.to_datetime(row["date"], errors="coerce")
        symbol = str(row["symbol"]).strip().upper()
        if pd.isna(date) or not symbol or symbol.lower() in {"nan", "none", "<na>"}:
            continue
        pair = (pd.Timestamp(date).normalize(), symbol)
        if pair not in scope_matched_pairs:
            details.add(pair)
    return [
        {"date": date.date().isoformat(), "symbol": symbol}
        for date, symbol in sorted(details)
    ]



def load_exchange_status_evidence(path):
    """Load official exchange-status evidence; never interpret it as a price/no-trade row."""
    path = Path(path)
    if not path.is_file():
        return []
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    required = {"symbol", "date_from", "date_to", "status", "verification_source", "evidence_reference"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Exchange-status evidence missing columns: {sorted(required - set(frame.columns))}")
    allowed = {"nse_dealings_withdrawn", "nse_suspended", "nse_delisted"}
    rows = []
    for _, row in frame.iterrows():
        symbol = str(row["symbol"]).strip().upper()
        status = str(row["status"]).strip().lower()
        source = str(row["verification_source"]).strip()
        reference = str(row["evidence_reference"]).strip()
        start = pd.to_datetime(row["date_from"], errors="coerce")
        end_raw = str(row["date_to"]).strip()
        end = pd.to_datetime(end_raw, errors="coerce") if end_raw else pd.NaT
        if (not symbol or status not in allowed or pd.isna(start)
                or (end_raw and pd.isna(end)) or (not pd.isna(end) and end < start)
                or not source or not reference):
            raise ValueError("Invalid exchange-status evidence row; refusing to apply it.")
        rows.append({
            "symbol": symbol,
            "date_from": pd.Timestamp(start).normalize(),
            "date_to": None if pd.isna(end) else pd.Timestamp(end).normalize(),
            "status": status,
            "verification_source": source,
            "evidence_reference": reference,
        })
    return rows


def exchange_status_confirmed(date, symbol, status_rows):
    """True only when a dated, sourced official status record covers this symbol/session."""
    date = pd.Timestamp(date).normalize()
    symbol = str(symbol).strip().upper()
    return any(
        row["symbol"] == symbol
        and row["date_from"] <= date
        and (row["date_to"] is None or date <= row["date_to"])
        for row in status_rows
    )


def status_confirmed_archive_absence_pairs(path, status_rows, scope_matched_pairs):
    """Return archive-absence pairs explained by official exchange status, not by prices."""
    path = Path(path)
    if not path.is_file():
        return set()
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if not {"date", "symbol", "status"}.issubset(frame.columns):
        return set()
    confirmed = set()
    for _, row in frame.iterrows():
        if row["status"].strip().lower() != "unresolved_archive_absence":
            continue
        date = pd.to_datetime(row["date"], errors="coerce")
        symbol = str(row["symbol"]).strip().upper()
        if pd.isna(date) or not symbol:
            continue
        pair = (pd.Timestamp(date).normalize(), symbol)
        if pair not in scope_matched_pairs and exchange_status_confirmed(pair[0], symbol, status_rows):
            confirmed.add(pair)
    return confirmed


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
    ap.add_argument("--symbol-map-supplement", default="data/reference/nse_historical_symbol_changes.csv")
    ap.add_argument("--exchange-status-evidence", default="data/reference/verified_exchange_status.csv")
    ap.add_argument("--membership", default="data/input/nifty500_membership.csv")
    ap.add_argument("--membership-warmup-sessions", type=int, default=252)
    ap.add_argument(
        "--scope-exclusions",
        default="data/reference/approved_price_gap_exclusions.csv",
        help="Explicit excluded/unresolved scope decisions; never price/no-trade evidence",
    )
    ap.add_argument(
        "--archive-absence-report",
        default="results/price_quality/bhavcopy_repair_absences.csv",
        help="Replay artifact used to validate each scoped exclusion against an exact unresolved absence",
    )
    args = ap.parse_args()

    p = pd.read_csv(args.prices, usecols=lambda c: c in {
        "date", "symbol", "requested_symbol", "series", "close"
    }, low_memory=False)
    p["date"] = pd.to_datetime(p["date"], errors="coerce", format="mixed")
    p["symbol"] = p["symbol"].astype(str).str.strip().str.upper()
    source_symbol = "requested_symbol" if "requested_symbol" in p.columns else "symbol"
    p[source_symbol] = p[source_symbol].astype(str).str.strip().str.upper()
    if "series" in p.columns:
        p["series"] = p["series"].astype(str).str.upper().str.strip()
        p = p[p["series"].isin(PRICE_CONTINUITY_SERIES)].copy()
    p = p.dropna(subset=["date"])
    calendar = pd.DatetimeIndex(sorted(p["date"].unique()))
    date_to_i = {pd.Timestamp(d): i for i, d in enumerate(calendar)}

    membership_path = Path(args.membership)
    if not membership_path.exists():
        raise SystemExit(f"PIT membership file missing: {membership_path}")
    membership_frame = pd.read_csv(membership_path, low_memory=False)
    membership_windows = build_membership_session_windows(
        membership_frame, calendar, warmup_sessions=args.membership_warmup_sessions
    )
    if not membership_windows:
        raise SystemExit("No usable membership windows were found; refusing unscoped readiness audit.")

    nt_path = Path(args.verified_no_trade)
    if not nt_path.exists():
        raise SystemExit(f"Verified no-trade ledger missing: {nt_path}")
    nt = pd.read_csv(nt_path, low_memory=False)
    if not {"date", "symbol", "status"}.issubset(nt.columns):
        raise SystemExit("Verified no-trade ledger must contain date, symbol, status")
    nt["date"] = pd.to_datetime(nt["date"], errors="coerce", format="mixed")
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

    # A scope waiver can suppress only the exact unresolved absence already
    # present in the replay artifact. It never creates price/no-trade evidence.
    scope_exclusion_rows = []
    scope_matched_pairs = set()
    scope_unmatched_rows = []
    scope_exclusion_issues = []
    try:
        scope_exclusion_rows = load_scope_exclusions(args.scope_exclusions)
        matched, unmatched, issues = match_scope_exclusions_to_archive_absences(
            scope_exclusion_rows, args.archive_absence_report
        )
        scope_unmatched_rows = unmatched
        scope_exclusion_issues.extend(issues)
        # Fail closed for the whole ledger if any row is stale or unverifiable.
        if not scope_exclusion_issues and not scope_unmatched_rows:
            scope_matched_pairs = matched
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        scope_exclusion_issues.append(str(exc))

    try:
        exchange_status_rows = load_exchange_status_evidence(args.exchange_status_evidence)
    except (OSError, ValueError, pd.errors.ParserError) as exc:
        raise SystemExit(f"Invalid exchange-status evidence: {exc}")
    status_confirmed_absences = status_confirmed_archive_absence_pairs(
        args.archive_absence_report, exchange_status_rows, scope_matched_pairs
    )

    rename_rows = load_symbol_rename_rows(args.symbol_map, args.symbol_map_supplement)
    aliases = terminal_symbol_aliases(rename_rows)
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
    candidate_gap_pairs_unfiltered = 0
    excluded_gap_pairs_outside_membership_window = 0
    for symbol, group in p.groupby(source_symbol, sort=False):
        idx = sorted({date_to_i[pd.Timestamp(d)] for d in group["date"].dropna().unique() if pd.Timestamp(d) in date_to_i})
        for left, right in zip(idx[:-1], idx[1:]):
            gap = right - left - 1
            if gap < args.min_gap_sessions:
                continue
            candidate_gap_pairs_unfiltered += gap
            relevant_indices = [
                i for i in range(left + 1, right)
                if in_membership_research_window(symbol, i, membership_windows)
                and not exchange_status_confirmed(calendar[i], symbol, exchange_status_rows)
            ]
            excluded_gap_pairs_outside_membership_window += gap - len(relevant_indices)
            if not relevant_indices:
                continue
            long_gap_spans.append({
                "symbol": str(symbol),
                "last_observed": calendar[left].date().isoformat(),
                "next_observed": calendar[right].date().isoformat(),
                "missing_sessions": int(gap),
                "relevant_missing_sessions": int(len(relevant_indices)),
            })
            for i in relevant_indices:
                dd = pd.Timestamp(calendar[i])
                resolved_alias = (dd, terminal_alias(symbol)) in observed_canonical_pairs
                pair = (dd.normalize(), str(symbol).strip().upper())
                if (
                    pair not in no_trade
                    and pair not in scope_matched_pairs
                    and not resolved_alias
                ):
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
    unresolved_fetch_pairs = int(repair.get("unresolved_target_pairs_due_to_fetch_errors", -1))
    archive_absence_pairs = int(repair.get("archive_absence_review_pairs", 0) or 0)
    eq_rows_added = int(repair.get("eq_rows_added", repair.get("rows_added", 0)) or 0)
    alternate_series_pairs = (
        int(repair.get("alternate_series_rows_added", 0) or 0)
        + int(repair.get("already_present_alternate_series_pairs", 0) or 0)
    )
    accounting = accounting_summary(
        target_pairs,
        eq_rows_added,
        repair.get("verified_no_trade_pairs", 0),
        repair.get("already_present_alias_matches", 0) or 0,
        archive_absence_pairs,
        max(0, unresolved_fetch_pairs),
        alternate_series_pairs,
    )
    accounted = accounting["accounted"]
    min_bhavcopy_rows = int(repair.get("minimum_valid_bhavcopy_eq_rows", 0) or 0)
    archive_api = str(repair.get("archive_api", ""))

    post_summary = {}
    if args.post_adjustment_summary and Path(args.post_adjustment_summary).exists():
        post_summary = json.loads(Path(args.post_adjustment_summary).read_text())
    price_summary = {}
    if args.price_quality_summary and Path(args.price_quality_summary).exists():
        price_summary = json.loads(Path(args.price_quality_summary).read_text())

    gap_blockers = []
    if not price_summary:
        gap_blockers.append("Raw price-quality summary is missing; basic OHLC, duplicate and nonpositive-close checks have not passed.")
    else:
        basic_quality_fields = [
            "invalid_date_rows", "missing_ohlc", "nonpositive_close", "ohlc_order_issues",
            "negative_volume", "negative_turnover", "duplicate_date_symbol",
        ]
        invalid_quality = {
            key: int(price_summary.get(key, 0) or 0)
            for key in basic_quality_fields
            if int(price_summary.get(key, 0) or 0) != 0
        }
        if invalid_quality:
            gap_blockers.append(f"Basic raw price-quality checks failed: {invalid_quality}.")
    gap_blockers.extend(ledger_evidence_issues)
    gap_blockers.extend(scope_exclusion_issues)
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
    blocking_archive_absence_pairs = max(
        0, archive_absence_pairs - len(scope_matched_pairs) - len(status_confirmed_absences)
    )
    if len(scope_matched_pairs) > archive_absence_pairs:
        gap_blockers.append(
            "Scoped exclusions matched more rows than the repair report's unresolved-absence count; refusing scope waiver."
        )
        blocking_archive_absence_pairs = archive_absence_pairs
    remaining_archive_absence_details = unresolved_archive_absence_details(
        args.archive_absence_report, scope_matched_pairs | status_confirmed_absences
    )
    if blocking_archive_absence_pairs > 0:
        gap_blockers.append(
            f"{blocking_archive_absence_pairs} symbol/date pair(s) lack an EQ/BE/BZ price observation "
            "and independent evidence of listing/suspension status after approved scope and exchange-status evidence; "
            "review them before any carry-forward."
        )
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
        "membership_scope": {
            "membership_file": str(membership_path),
            "warmup_sessions_before_membership": int(args.membership_warmup_sessions),
            "membership_aliases_matched": int(len(membership_windows)),
            "all_history_candidate_gap_pairs": int(candidate_gap_pairs_unfiltered),
            "pairs_excluded_outside_membership_window": int(excluded_gap_pairs_outside_membership_window),
        },
        "price_series_policy": "EQ preferred; observed BE/BZ closes count as price continuity with source series preserved. BE/BZ tradability is not assumed.",
        "symbol_lineage": {
            "rows": int(len(rename_rows)),
            "supplemental_file": str(args.symbol_map_supplement),
        },
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
            "scope_excluded_archive_absence_pairs": len(scope_matched_pairs),
            "official_status_confirmed_archive_absence_pairs": [
                {"date": pair[0].date().isoformat(), "symbol": pair[1]}
                for pair in sorted(status_confirmed_absences)
            ],
            "blocking_archive_absence_pairs": blocking_archive_absence_pairs,
            "remaining_archive_absence_details": remaining_archive_absence_details,
            "already_present_alias_matches": repair.get("already_present_alias_matches"),
            "accounted_target_pairs": accounted,
            "accounting_buckets": accounting["buckets"],
            "accounting_mismatch": accounting["mismatch"],
        },
        "approved_no_trade_ledger_evidence_issues": ledger_evidence_issues,
        "exchange_status_evidence": {
            "ledger_path": str(args.exchange_status_evidence),
            "declared_count": len(exchange_status_rows),
            "status_confirmed_archive_absence_pairs": [
                {"date": pair[0].date().isoformat(), "symbol": pair[1]}
                for pair in sorted(status_confirmed_absences)
            ],
            "policy": "Official exchange-status evidence explains why a price is not expected; it is not a price observation and never authorizes carry-forward.",
        },
        "scope_exclusions": {
            "ledger_path": str(args.scope_exclusions),
            "archive_absence_report_path": str(args.archive_absence_report),
            "declared_count": len(scope_exclusion_rows),
            "matched_archive_absence_pairs": [
                {"date": pair[0].date().isoformat(), "symbol": pair[1]}
                for pair in sorted(scope_matched_pairs)
            ],
            "unmatched": [
                {"date": row.get("date"), "symbol": row.get("symbol"),
                 "status": row.get("status")}
                for row in scope_unmatched_rows
            ],
            "issues": scope_exclusion_issues,
            "policy": "excluded_unresolved is a scope disposition, not a price, not verified_no_trade, and never eligible for carry-forward",
        },
        "remaining_long_internal_gap_spans": int(len(long_gap_spans)),
        "remaining_unverified_gap_pairs": int(len(missing_unverified)),
        "sample_unverified_gap_pairs": missing_unverified[:100],
        "remaining_archive_absence_details": remaining_archive_absence_details,
        "raw_price_quality_summary": price_summary,
        "post_adjustment_summary": post_summary,
        "blockers": gap_blockers,
        "limitations": [
            "PROVISIONAL price-return research is not production approval.",
            "Dividend adjustment has not been established as complete; do not describe these results as total-return performance.",
            "Any remaining large continuity events require event-level corporate-action reconciliation before interpreting strategy returns.",
            "Explicit scope exclusions remain unresolved and must be disclosed; they are not verified no-trade and are not prices.",
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
        "remaining_archive_absence_details": remaining_archive_absence_details,
        "sample_unverified_gap_pairs": missing_unverified[:100],
        "blockers": gap_blockers,
    }, indent=2))
    if gap_blockers:
        raise SystemExit("FLUID-Q price-gap readiness gate blocked; inspect readiness report.")


if __name__ == "__main__":
    main()
