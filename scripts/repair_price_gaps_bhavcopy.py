#!/usr/bin/env python3
"""Backfill long internal NSE price gaps from official daily bhavcopy archives.

Only exact EQ observations from an official archive are inserted. A symbol/date
pair absent from a successfully parsed archive is recorded as unresolved until
independent listing/suspension evidence is supplied. It is never written as a
synthetic raw price or automatically approved as a no-trade day.
"""
import argparse
import io
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path

import pandas as pd
from jugaad_data.nse import NSEArchives

_THREAD_LOCAL = threading.local()


def thread_archive():
    if not hasattr(_THREAD_LOCAL, "archive"):
        _THREAD_LOCAL.archive = NSEArchives()
    return _THREAD_LOCAL.archive


# Supports both legacy bhavcopy columns (OPEN_PRICE/CLOSE_PRICE/...) and
# UDiFF columns (OpnPric/ClsPric/TckrSymb/SctySrs) returned by NSEArchives.
PRICE_COLS = {
    "symbol": ["SYMBOL", "TCKRSYMB", "TICKER_SYMBOL"],
    "series": ["SERIES", "SCTYSRS", "SECURITY_SERIES"],
    "date": ["TIMESTAMP", "DATE", "DATE1", "TRADDT", "TRADING_DATE"],
    "prev_close": ["PREVCLOSE", "PREV_CLOSE", "PRVSCLSGPRIC", "PREVIOUS_CLOSE"],
    "open": ["OPEN", "OPEN_PRICE", "OPNPRIC"],
    "high": ["HIGH", "HIGH_PRICE", "HGHPRIC"],
    "low": ["LOW", "LOW_PRICE", "LWPRIC"],
    "last": ["LAST", "LAST_PRICE", "LASTPRIC"],
    "close": ["CLOSE", "CLOSE_PRICE", "CLSPRIC"],
    "vwap": ["VWAP", "AVG_PRICE", "AVGPRIC"],
    "volume": ["TOTTRDQTY", "TTL_TRD_QNTY", "TOTAL_TRADED_QUANTITY", "TTLTRADGVOL"],
    "traded_value": ["TOTTRDVAL", "TURNOVER_LACS", "TURNOVER", "TTLTRFVAL", "TRADED_VALUE"],
    "num_trades": ["TOTALTRADES", "NO_OF_TRADES", "TTLNBOFTXSEXCTD", "NUM_TRADES"],
}


def norm(value):
    return " ".join(str(value).replace("\ufeff", "").replace("\xa0", " ").strip().strip('"').split()).upper()


def parse_archive(payload, day, filter_eq=True):
    if isinstance(payload, pd.DataFrame):
        frame = payload.copy()
    elif isinstance(payload, bytes):
        frame = pd.read_csv(io.BytesIO(payload))
    elif isinstance(payload, str):
        # jugaad-data versions have returned both CSV text and paths/URLs.
        try:
            frame = pd.read_csv(io.StringIO(payload))
        except Exception:
            frame = pd.read_csv(payload)
    else:
        raise TypeError(f"Unexpected bhavcopy response type: {type(payload).__name__}")

    frame.columns = [norm(c).replace(" ", "_").replace("-", "_") for c in frame.columns]
    # Legacy daily bhavcopy labels turnover in lakh rupees; UDiFF TtlTrfVal
    # is already rupees. Normalize both to the source CSV's rupee unit.
    turnover_is_lakh_rupees = "TURNOVER_LACS" in frame.columns
    rename = {}
    for target, choices in PRICE_COLS.items():
        for choice in choices:
            key = norm(choice).replace(" ", "_").replace("-", "_")
            if key in frame.columns:
                rename[key] = target
                break
    frame = frame.rename(columns=rename)
    required = {"symbol", "series", "close"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Bhavcopy missing required columns {sorted(required-set(frame.columns))}; got {list(frame.columns)}")

    frame["symbol"] = frame["symbol"].astype(str).str.strip().str.upper()
    frame["series"] = frame["series"].astype(str).str.strip().str.upper()
    if filter_eq:
        frame = frame.loc[frame["series"].eq("EQ")].copy()
    frame["date"] = pd.Timestamp(day)
    for col in ["open", "high", "low", "last", "prev_close", "close", "vwap", "volume", "traded_value", "num_trades"]:
        if col in frame:
            frame[col] = pd.to_numeric(frame[col].astype(str).str.replace(",", "", regex=False), errors="coerce")
    if turnover_is_lakh_rupees and "traded_value" in frame:
        frame["traded_value"] = frame["traded_value"] * 100000.0
    return frame.dropna(subset=["symbol", "close"])


def exchange_symbol(symbol, day, symbol_map):
    """Return the exchange ticker valid on day for a known rename lineage."""
    cur = str(symbol).strip().upper()
    visited = set()
    day = pd.Timestamp(day)
    # Walk backwards for dates before a rename; forwards after it.
    changed = True
    while changed and cur not in visited:
        visited.add(cur)
        changed = False
        for old, new, effective in symbol_map:
            if day < effective and cur == new:
                cur = old
                changed = True
                break
            if day >= effective and cur == old:
                cur = new
                changed = True
                break
    return cur


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--symbol-map", default="data/input/verified_symbol_map.csv")
    ap.add_argument("--out", required=True)
    ap.add_argument("--no-trade-out", default="data/input/verified_no_trade_dates.csv")
    ap.add_argument("--exceptions-out", default="data/input/unresolved_gap_exceptions.csv")
    ap.add_argument("--report", default="results/price_quality/bhavcopy_gap_repair.json")
    ap.add_argument("--start", default="2014-01-01")
    ap.add_argument("--end", default="2026-08-31")
    ap.add_argument("--min-gap-sessions", type=int, default=10)
    ap.add_argument("--sleep", type=float, default=0.15)
    ap.add_argument("--retries", type=int, default=3)
    ap.add_argument("--workers", type=int, default=3, help="Concurrent source sessions; keep modest to avoid excessive exchange requests.")
    ap.add_argument("--min-bhavcopy-eq-rows", type=int, default=500, help="Reject partial/invalid archives rather than using them as no-trade evidence.")
    a = ap.parse_args()

    src = Path(a.prices)
    raw_all = pd.read_csv(src, low_memory=False)
    if not {"date", "symbol"}.issubset(raw_all.columns):
        raise SystemExit("Price file must contain date and symbol columns")
    raw_all["date"] = pd.to_datetime(raw_all["date"], errors="coerce")
    raw_all["symbol"] = raw_all["symbol"].astype(str).str.strip().str.upper()
    if "series" in raw_all:
        raw_all["series"] = raw_all["series"].astype(str).str.strip().str.upper()
    start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
    raw_all = raw_all.loc[raw_all["date"].between(start, end)].copy()
    # Keep every original series in the output. Gap discovery and repair are
    # restricted to fully-paid EQ shares because that is the strategy universe.
    base = raw_all.loc[raw_all["series"].eq("EQ")].copy() if "series" in raw_all else raw_all.copy()
    detect_col = "requested_symbol" if "requested_symbol" in base.columns else "symbol"
    base[detect_col] = base[detect_col].astype(str).str.strip().str.upper()
    if base.empty:
        raise SystemExit("No EQ price observations fall in the requested date window")

    calendar = pd.DatetimeIndex(sorted(base["date"].dropna().unique()))
    targets_by_date = defaultdict(set)
    gap_spans = []
    date_to_idx = {d: i for i, d in enumerate(calendar)}
    for symbol, group in base.groupby(detect_col, sort=False):
        idx = sorted({date_to_idx[d] for d in group["date"].dropna().unique() if d in date_to_idx})
        if len(idx) < 2:
            continue
        for left, right in zip(idx[:-1], idx[1:]):
            missing_count = right - left - 1
            if missing_count < a.min_gap_sessions:
                continue
            gap_start = calendar[left + 1]
            gap_end = calendar[right - 1]
            gap_spans.append({
                "symbol": str(symbol),
                "last_observed": calendar[left].date().isoformat(),
                "next_observed": calendar[right].date().isoformat(),
                "missing_sessions": int(missing_count),
                "gap_start": gap_start.date().isoformat(),
                "gap_end": gap_end.date().isoformat(),
            })
            for i in range(left + 1, right):
                targets_by_date[calendar[i]].add(str(symbol))

    # Rename map applies on the effective date, so a historical query ticker
    # can still be repaired from the exchange ticker actually used that day.
    sm = pd.read_csv(a.symbol_map)
    sm["old_symbol"] = sm["old_symbol"].astype(str).str.strip().str.upper()
    sm["new_symbol"] = sm["new_symbol"].astype(str).str.strip().str.upper()
    sm["effective_from"] = pd.to_datetime(sm["effective_from"], errors="coerce")
    rename_rows = [(r.old_symbol, r.new_symbol, r.effective_from)
                   for r in sm.itertuples() if pd.notna(r.effective_from)]

    # Existing identity set is based on the original acquisition/request
    # symbol. Do not replace existing raw prices automatically.
    existing = set(zip(base["date"], base[detect_col]))
    existing_raw_keys = set(zip(base["date"], base["symbol"]))
    additions = []
    no_trade = []  # Only independently verified entries from an existing approved ledger.
    absence_exceptions = []
    already_present_alias_matches = 0
    fetch_errors = []
    fetched_days = 0
    # Diagnostics distinguish a true symbol-level absence from a partial or
    # incorrectly parsed daily archive. These observations never approve a gap.
    benchmark_symbols = ("RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK", "AARTIIND")
    benchmark_presence_counts = {symbol: {"dates_checked": 0, "present": 0, "absent": 0} for symbol in benchmark_symbols}
    archive_diagnostic_examples = []
    non_eq_target_presence_counts = defaultdict(lambda: defaultdict(int))
    non_eq_target_presence_examples = []
    all_days = sorted(d for d in targets_by_date if start <= d <= end)

    def fetch_day(day):
        last_error = None
        parsed = None
        for attempt in range(a.retries + 1):
            try:
                payload = thread_archive().bhavcopy_raw(pd.Timestamp(day).to_pydatetime())
                parsed_all = parse_archive(payload, day, filter_eq=False)
                parsed = parsed_all.loc[parsed_all["series"].eq("EQ")].copy()
                if len(parsed) < a.min_bhavcopy_eq_rows:
                    raise ValueError(
                        f"Bhavcopy sanity check failed: only {len(parsed)} EQ rows; "
                        f"minimum is {a.min_bhavcopy_eq_rows}"
                    )
                last_error = None
                break
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {str(exc)[:220]}"
                time.sleep(min(2 ** attempt, 15))
        time.sleep(a.sleep)
        if last_error is not None:
            return pd.Timestamp(day), None, None, last_error
        return pd.Timestamp(day), parsed, parsed_all, None

    completed = 0
    with ThreadPoolExecutor(max_workers=max(1, min(a.workers, 6))) as pool:
        futures = {pool.submit(fetch_day, day): day for day in all_days}
        for future in as_completed(futures):
            day = pd.Timestamp(futures[future])
            target_symbols = targets_by_date[day]
            try:
                _, parsed, parsed_all, err = future.result()
            except Exception as exc:
                parsed = None
                parsed_all = None
                err = f"{type(exc).__name__}: {str(exc)[:220]}"

            if err is not None or parsed is None:
                fetch_errors.append({
                    "date": day.date().isoformat(),
                    "error": str(err or "empty_archive"),
                    "target_symbols": len(target_symbols),
                })
            else:
                fetched_days += 1
                parsed_by_symbol = {str(s).strip().upper(): g for s, g in parsed.groupby("symbol", sort=False)}
                parsed_symbols = set(parsed_by_symbol)
                all_series_by_symbol = {str(s).strip().upper(): g for s, g in parsed_all.groupby("symbol", sort=False)}
                for benchmark in benchmark_symbols:
                    benchmark_presence_counts[benchmark]["dates_checked"] += 1
                    bucket = "present" if benchmark in parsed_symbols else "absent"
                    benchmark_presence_counts[benchmark][bucket] += 1
                missing_benchmarks = [s for s in benchmark_symbols if s not in parsed_symbols]
                # Keep only high-signal examples to avoid bloating the report.
                if len(archive_diagnostic_examples) < 100 and (missing_benchmarks or "AARTIIND" in target_symbols):
                    archive_diagnostic_examples.append({
                        "date": day.date().isoformat(),
                        "parsed_eq_rows": int(len(parsed)),
                        "parsed_unique_symbols": int(len(parsed_symbols)),
                        "target_symbols_count": int(len(target_symbols)),
                        "target_symbols_missing_sample": [s for s in sorted(target_symbols) if s not in parsed_symbols][:12],
                        "benchmark_symbols_missing": missing_benchmarks,
                        "aartiind_is_target": "AARTIIND" in target_symbols,
                        "aartiind_present": "AARTIIND" in parsed_symbols,
                    })
                for requested in sorted(target_symbols):
                    if (day, requested) in existing:
                        continue
                    exchange = exchange_symbol(requested, day, rename_rows)
                    if (day, exchange) in existing_raw_keys:
                        already_present_alias_matches += 1
                        continue
                    matched = parsed_by_symbol.get(exchange)
                    if matched is None or matched.empty:
                        # Record whether the ticker exists in the archive under a non-EQ series.
                        # This helps distinguish a series transition from a missing ticker.
                        all_series_rows = all_series_by_symbol.get(exchange)
                        other_series = [] if all_series_rows is None else sorted({
                            str(x).strip().upper() for x in all_series_rows["series"].dropna()
                            if str(x).strip().upper() != "EQ"
                        })
                        if other_series:
                            for series_name in other_series:
                                non_eq_target_presence_counts[requested][series_name] += 1
                            if len(non_eq_target_presence_examples) < 100:
                                non_eq_target_presence_examples.append({
                                    "date": day.date().isoformat(), "symbol": requested,
                                    "exchange_symbol_checked": exchange, "non_eq_series": other_series,
                                })
                        # Absence from a complete bhavcopy does not, by itself,
                        # prove a genuine no-trade day: the symbol may have been
                        # renamed, suspended, delisted, or moved series. Keep it
                        # unresolved until an authoritative status/lineage source
                        # explains the absence. Never use it for return carry-forward.
                        absence_exceptions.append({
                            "date": day.date().isoformat(),
                            "symbol": requested,
                            "exchange_symbol_checked": exchange,
                            "series": "EQ",
                            "status": "unresolved_archive_absence",
                            "verification_source": "NSE daily EQ bhavcopy has no matching ticker; listing/suspension status not independently verified",
                        })
                        continue

                    row = matched.iloc[-1].to_dict()
                    new = {col: pd.NA for col in base.columns}
                    for col in [
                        "symbol", "series", "date", "prev_close", "open", "high",
                        "low", "last", "close", "vwap", "volume", "traded_value",
                        "turnover", "turnover_₹", "turnover ₹", "num_trades",
                    ]:
                        if col in new and col in row:
                            new[col] = row[col]
                    if "turnover ₹" in new and "traded_value" in row:
                        new["turnover ₹"] = row["traded_value"]
                    if "turnover_₹" in new and "traded_value" in row:
                        new["turnover_₹"] = row["traded_value"]
                    if "requested_symbol" in new:
                        new["requested_symbol"] = requested
                    if "source_symbol" in new:
                        new["source_symbol"] = exchange
                    if "source_endpoint" in new:
                        new["source_endpoint"] = "NSE daily bhavcopy archive"
                    additions.append(new)
                    existing.add((day, requested))
                    existing_raw_keys.add((day, exchange))

            completed += 1
            if completed % 50 == 0 or completed == len(all_days):
                print(
                    f"bhavcopy dates {completed}/{len(all_days)}; fetched={fetched_days}; "
                    f"added={len(additions)}; unresolved_absences={len(absence_exceptions)}; "
                    f"errors={len(fetch_errors)}",
                    flush=True,
                )

    # Keep raw rows as downloaded; no-trade marks are stored separately and
    # may only be used by the backtest to carry forward a mark, never as prices.
    add_df = pd.DataFrame(additions, columns=base.columns) if additions else pd.DataFrame(columns=base.columns)
    result = pd.concat([raw_all, add_df], ignore_index=True, sort=False)
    result = result.dropna(subset=["date", "symbol"])
    result = result.drop_duplicates(["date", "symbol", "series"] if "series" in result else ["date", "symbol"])
    result = result.sort_values(["date", "symbol"]).reset_index(drop=True)

    nt_path = Path(a.no_trade_out)
    nt_path.parent.mkdir(parents=True, exist_ok=True)
    # Preserve only prior entries that have been explicitly reviewed outside
    # this automatic gap scan. This code never creates verified_no_trade rows.
    if nt_path.exists() and nt_path.stat().st_size:
        approved = pd.read_csv(nt_path, low_memory=False)
        required_approved = {"date", "symbol", "status", "verification_source", "evidence_reference"}
        if not required_approved.issubset(approved.columns):
            raise SystemExit(
                "Existing verified no-trade ledger must contain date, symbol, status, "
                "verification_source and evidence_reference; automatic archive absence is not enough."
            )
        approved["status"] = approved["status"].astype(str).str.strip()
        approved["verification_source"] = approved["verification_source"].astype(str).str.strip()
        approved["evidence_reference"] = approved["evidence_reference"].astype(str).str.strip()
        approved = approved.loc[
            approved["status"].eq("verified_no_trade")
            & approved["verification_source"].ne("")
            & approved["verification_source"].str.lower().ne("nan")
            & approved["evidence_reference"].ne("")
            & approved["evidence_reference"].str.lower().ne("nan")
            & approved["verification_source"].str.lower().ne("nse daily bhavcopy eq universe")
        ].copy()
        no_trade_df = approved
    else:
        no_trade_df = pd.DataFrame(columns=[
            "date", "symbol", "exchange_symbol_checked", "series", "status",
            "verification_source", "evidence_reference"
        ])
    no_trade_df = no_trade_df.drop_duplicates(["date", "symbol"])
    exception_df = pd.DataFrame(absence_exceptions, columns=[
        "date", "symbol", "exchange_symbol_checked", "series", "status", "verification_source"
    ]).drop_duplicates(["date", "symbol"])
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(out, index=False)
    no_trade_df.to_csv(nt_path, index=False)
    exceptions_path = Path(a.exceptions_out)
    exceptions_path.parent.mkdir(parents=True, exist_ok=True)
    exception_df.to_csv(exceptions_path, index=False)

    target_pairs_set = {
        (pd.Timestamp(day), str(symbol).upper().strip())
        for day, syms in targets_by_date.items()
        for symbol in syms
    }
    approved_pairs = set()
    if not no_trade_df.empty:
        approved_dates = pd.to_datetime(no_trade_df["date"], errors="coerce")
        approved_symbols = no_trade_df["symbol"].astype(str).str.upper().str.strip()
        approved_pairs = set(zip(approved_dates, approved_symbols))
    verified_target_no_trade_pairs = int(len(target_pairs_set & approved_pairs))

    report = {
        "source_input": str(src),
        "archive_api": "NSEArchives.bhavcopy_raw (legacy archive before 2024-07-08; UDiFF archive thereafter)",
        "date_start": str(start.date()),
        "date_end": str(end.date()),
        "calendar_sessions": int(len(calendar)),
        "minimum_internal_gap_sessions_targeted": int(a.min_gap_sessions),
        "minimum_valid_bhavcopy_eq_rows": int(a.min_bhavcopy_eq_rows),
        "workers": int(max(1, min(a.workers, 6))),
        "internal_gap_spans_targeted": int(len(gap_spans)),
        "target_symbol_date_pairs": int(sum(len(x) for x in targets_by_date.values())),
        "unique_bhavcopy_dates_attempted": int(len(all_days)),
        "bhavcopy_dates_parsed": int(fetched_days),
        "fetch_error_dates": int(len(fetch_errors)),
        "rows_before": int(len(raw_all)),
        "rows_added": int(len(additions)),
        "rows_after": int(len(result)),
        "verified_no_trade_pairs": verified_target_no_trade_pairs,
        "approved_ledger_rows_total": int(len(no_trade_df)),
        "archive_absence_review_pairs": int(len(exception_df)),
        "already_present_alias_matches": int(already_present_alias_matches),
        "unresolved_target_pairs_due_to_fetch_errors": int(sum(x["target_symbols"] for x in fetch_errors)),
        "accounted_target_pairs": int(len(additions) + verified_target_no_trade_pairs + already_present_alias_matches + len(exception_df) + sum(x["target_symbols"] for x in fetch_errors)),
        "status": "BLOCKED" if fetch_errors or len(exception_df) else "PASS",
        "top_added_symbols": pd.Series([str(x.get("requested_symbol", x.get("symbol", ""))) for x in additions]).value_counts().head(30).to_dict(),
        "archive_symbol_presence_diagnostics": {
            "benchmark_presence_counts": benchmark_presence_counts,
            "examples": archive_diagnostic_examples,
            "unresolved_targets_found_in_non_eq_series": {
                symbol: dict(series_counts)
                for symbol, series_counts in sorted(non_eq_target_presence_counts.items())
            },
            "non_eq_series_examples": non_eq_target_presence_examples,
            "interpretation": "Presence counts diagnose archive parsing/matching only; non-EQ rows are not treated as valid EQ prices and no absence is approved as no-trade.",
        },
        "gaps": gap_spans,
        "fetch_errors": fetch_errors,
        "verified_no_trade_ledger": str(nt_path),
        "unresolved_absence_exceptions": str(exceptions_path),
        "approved_no_trade_evidence_fields": ["verification_source", "evidence_reference"],
        "note": "Only actual NSE EQ bhavcopy observations are added. Absence from a successfully parsed archive remains unresolved pending independent evidence; it is not verified no-trade and is never converted into a synthetic raw price row. Failed archive days also remain unresolved.",
    }
    rp = Path(a.report); rp.parent.mkdir(parents=True, exist_ok=True)
    rp.write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: report[k] for k in [
        "calendar_sessions", "internal_gap_spans_targeted", "target_symbol_date_pairs",
        "unique_bhavcopy_dates_attempted", "bhavcopy_dates_parsed", "fetch_error_dates",
        "rows_before", "rows_added", "rows_after", "verified_no_trade_pairs", "archive_absence_review_pairs",
        "unresolved_target_pairs_due_to_fetch_errors"
    ]}, indent=2))
    # The separate readiness gate consumes this report after other diagnostics
    # have run. Failed downloads never count as verified no-trade observations.


if __name__ == "__main__":
    main()
