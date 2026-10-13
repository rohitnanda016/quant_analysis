#!/usr/bin/env python3
"""Backfill in-scope gaps using actual NSE EQ, BE or BZ price observations.

EQ observations are preferred; BE/BZ rows retain their original series for price
continuity and execution-eligibility checks. A pair without a usable price row
remains unresolved until independent listing/suspension evidence is supplied.
No synthetic raw prices or automatically approved no-trade days are created.
"""
import argparse
import hashlib
import io
import json
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from pathlib import Path

import pandas as pd
from jugaad_data.nse import NSEArchives

try:
    from scripts.membership_scope import build_membership_session_windows, in_membership_research_window
    from scripts.symbol_lineage import load_symbol_rename_rows, symbol_map_fingerprint
except ModuleNotFoundError:
    from membership_scope import build_membership_session_windows, in_membership_research_window
    from symbol_lineage import load_symbol_rename_rows, symbol_map_fingerprint

_THREAD_LOCAL = threading.local()
PRICE_CONTINUITY_SERIES = {"EQ", "BE", "BZ"}
ALTERNATE_PRICE_SERIES = {"BE", "BZ"}


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


def checkpoint_matches(checkpoint, start, end, target_pairs, total_dates,
                       warmup_sessions=None, target_inventory_hash=None):
    """Reject checkpoints produced for a different repair inventory."""
    matches = (
        checkpoint.get("date_start") == str(pd.Timestamp(start).date())
        and checkpoint.get("date_end") == str(pd.Timestamp(end).date())
        and checkpoint.get("target_symbol_date_pairs") == int(target_pairs)
        and checkpoint.get("total_dates") == int(total_dates)
    )
    if warmup_sessions is not None:
        matches = matches and checkpoint.get("membership_warmup_sessions") == int(warmup_sessions)
    if target_inventory_hash is not None:
        matches = matches and checkpoint.get("target_inventory_sha256") == str(target_inventory_hash)
    return matches


def inventory_attempts_complete(attempted_date_values, total_dates):
    """A batch scan is complete once every target date was attempted, even if some failed."""
    return len(set(attempted_date_values)) >= int(total_dates)


def target_inventory_fingerprint(targets_by_date):
    """Fingerprint exact date/symbol repair targets, not only inventory totals."""
    pairs = sorted(
        (pd.Timestamp(day).date().isoformat(), str(symbol).strip().upper())
        for day, symbols in targets_by_date.items()
        for symbol in symbols
    )
    payload = "\n".join(f"{day}|{symbol}" for day, symbol in pairs).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def deduplicate_price_rows(frame):
    """Remove only byte-for-byte duplicate rows; never hide conflicting prices.

    Key-level collisions (same date/symbol/series with different values) must
    remain visible to the downstream quality gate rather than silently choosing
    an arbitrary observation.
    """
    return frame.drop_duplicates()


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


def absences_requiring_replay(absence_exceptions, rename_rows):
    """Return old absence pairs where current lineage changes the exchange ticker."""
    replay = set()
    for item in absence_exceptions:
        day_value = pd.to_datetime(item.get("date"), errors="coerce", format="mixed")
        symbol_value = str(item.get("symbol", "")).strip().upper()
        if pd.isna(day_value) or not symbol_value:
            continue
        mapped = exchange_symbol(symbol_value, day_value, rename_rows)
        checked = str(item.get("exchange_symbol_checked", "")).strip().upper()
        if mapped != checked:
            replay.add((pd.Timestamp(day_value).date().isoformat(), symbol_value))
    return replay


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--symbol-map", default="data/input/verified_symbol_map.csv")
    ap.add_argument("--symbol-map-supplement", default="data/reference/nse_historical_symbol_changes.csv")
    ap.add_argument("--membership", default="data/input/nifty500_membership.csv")
    ap.add_argument("--membership-warmup-sessions", type=int, default=252,
                    help="Price-history sessions before membership needed for momentum/200DMA features.")
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
    ap.add_argument("--resume", action="store_true", help="Resume from a validated local repair checkpoint.")
    ap.add_argument("--max-dates", type=int, default=0, help="Maximum archive dates to process this run; 0 processes all pending dates.")
    a = ap.parse_args()

    src = Path(a.prices)
    raw_all = pd.read_csv(src, low_memory=False)
    if not {"date", "symbol"}.issubset(raw_all.columns):
        raise SystemExit("Price file must contain date and symbol columns")
    raw_all["date"] = pd.to_datetime(raw_all["date"], errors="coerce", format="mixed")
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
    membership_path = Path(a.membership)
    if not membership_path.exists():
        raise SystemExit(f"PIT membership file missing: {membership_path}")
    membership_frame = pd.read_csv(membership_path, low_memory=False)
    membership_windows = build_membership_session_windows(
        membership_frame, calendar, warmup_sessions=a.membership_warmup_sessions
    )
    if not membership_windows:
        raise SystemExit("No usable membership windows were found; refusing unscoped price-gap repair.")

    targets_by_date = defaultdict(set)
    gap_spans = []
    candidate_missing_pairs_unfiltered = 0
    excluded_outside_membership_window = 0
    date_to_idx = {pd.Timestamp(d): i for i, d in enumerate(calendar)}
    for symbol, group in base.groupby(detect_col, sort=False):
        idx = sorted({date_to_idx[pd.Timestamp(d)] for d in group["date"].dropna().unique() if pd.Timestamp(d) in date_to_idx})
        if len(idx) < 2:
            continue
        for left, right in zip(idx[:-1], idx[1:]):
            missing_count = right - left - 1
            if missing_count < a.min_gap_sessions:
                continue
            candidate_missing_pairs_unfiltered += missing_count
            relevant_indices = [
                i for i in range(left + 1, right)
                if in_membership_research_window(symbol, i, membership_windows)
            ]
            excluded_outside_membership_window += missing_count - len(relevant_indices)
            if not relevant_indices:
                continue
            gap_spans.append({
                "symbol": str(symbol),
                "last_observed": calendar[left].date().isoformat(),
                "next_observed": calendar[right].date().isoformat(),
                "missing_sessions": int(missing_count),
                "targeted_missing_sessions": int(len(relevant_indices)),
                "gap_start": calendar[relevant_indices[0]].date().isoformat(),
                "gap_end": calendar[relevant_indices[-1]].date().isoformat(),
            })
            for i in relevant_indices:
                targets_by_date[calendar[i]].add(str(symbol))
    target_inventory_hash = target_inventory_fingerprint(targets_by_date)

    # Rename map applies on the effective date, so a historical query ticker
    # can still be repaired from the exchange ticker actually used that day.
    rename_rows = load_symbol_rename_rows(a.symbol_map, a.symbol_map_supplement)
    symbol_map_hash = symbol_map_fingerprint(rename_rows)
    print(json.dumps({
        "historical_symbol_map_rows": len(rename_rows),
        "historical_symbol_map_sha256": symbol_map_hash,
        "supplemental_symbol_map": a.symbol_map_supplement,
    }), flush=True)

    # EQ observations define eligibility and gap discovery. Existing BE/BZ
    # observations are also valid market-price marks for return continuity,
    # but their original series must be preserved for execution-eligibility checks.
    existing = set(zip(base["date"], base[detect_col]))
    existing_eq_raw_keys = set(zip(base["date"], base["symbol"]))
    if "series" in raw_all.columns:
        continuity_rows = raw_all.loc[
            raw_all["series"].astype(str).str.strip().str.upper().isin(PRICE_CONTINUITY_SERIES)
        ]
    else:
        continuity_rows = raw_all
    existing_raw_keys = set(zip(continuity_rows["date"], continuity_rows["symbol"]))
    additions = []
    no_trade = []  # Only independently verified entries from an existing approved ledger.
    absence_exceptions = []
    already_present_alias_matches = 0
    already_present_alternate_series_pairs = 0
    alternate_series_rows_added = 0
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
    completed_date_values = set()
    attempted_date_values = set()
    run_started = time.monotonic()
    checkpoint_path = Path(a.report).with_name("bhavcopy_repair_checkpoint.json")
    additions_path = checkpoint_path.with_name("bhavcopy_repair_additions.csv")
    absences_path = checkpoint_path.with_name("bhavcopy_repair_absences.csv")
    checkpoint_path.parent.mkdir(parents=True, exist_ok=True)

    if a.resume and checkpoint_path.exists():
        prior = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        expected_pairs = int(sum(len(symbols) for symbols in targets_by_date.values()))
        if not checkpoint_matches(
            prior, start, end, expected_pairs, len(all_days),
            warmup_sessions=a.membership_warmup_sessions,
            target_inventory_hash=target_inventory_hash,
        ):
            # Membership scoping changes the inventory materially. Never mix
            # additions/absence rows from the old all-history inventory with
            # the new target set; discard stale checkpoint state and start clean.
            print(
                "Checkpoint inventory mismatch; discarding stale checkpoint and rebuilding "
                "from the finalized source dataset.",
                flush=True,
            )
            for stale_path in (checkpoint_path, additions_path, absences_path):
                stale_path.unlink(missing_ok=True)
        else:
            completed_date_values = set(prior.get("completed_date_values", []))
            fetch_errors = list(prior.get("fetch_errors", []))
            if "attempted_date_values" in prior:
                attempted_date_values = set(prior.get("attempted_date_values", []))
            else:
                # Migrate a matching checkpoint from the immediately preceding
                # repair version: every successful date plus its persisted fetch
                # error dates were attempted in that batch.
                attempted_date_values = set(completed_date_values) | {
                    str(item.get("date")) for item in fetch_errors if item.get("date")
                }
            completed = len(attempted_date_values)
            if additions_path.exists() and additions_path.stat().st_size:
                additions = pd.read_csv(additions_path, low_memory=False).to_dict("records")
            if absences_path.exists() and absences_path.stat().st_size:
                absence_exceptions = pd.read_csv(absences_path, low_memory=False).to_dict("records")
            fetched_days = int(prior.get("fetched_dates", 0))
            benchmark_presence_counts = prior.get("benchmark_presence", benchmark_presence_counts)
            for symbol, counts in prior.get("non_eq_target_presence", {}).items():
                for series_name, count in counts.items():
                    non_eq_target_presence_counts[symbol][series_name] = int(count)
            archive_diagnostic_examples = list(prior.get("diagnostic_examples", []))
            non_eq_target_presence_examples = list(prior.get("non_eq_examples", []))
            already_present_alias_matches = int(prior.get("already_present_alias_matches", 0))
            already_present_alternate_series_pairs = int(prior.get("already_present_alternate_series_pairs", 0))
            alternate_series_rows_added = int(prior.get("alternate_series_rows_added", 0))

            # A newer, source-verified rename mapping can resolve prior absences.
            # Revisit only dates containing an absence whose exchange ticker has
            # changed; keep all successful observations and other exceptions.
            previous_map_hash = prior.get("symbol_map_sha256")
            replay_pairs = (
                absences_requiring_replay(absence_exceptions, rename_rows)
                if previous_map_hash != symbol_map_hash else set()
            )
            if replay_pairs:
                replay_days = {day for day, _ in replay_pairs}
                old_count = len(absence_exceptions)
                absence_exceptions = [
                    item for item in absence_exceptions
                    if (str(item.get("date")), str(item.get("symbol", "")).strip().upper()) not in replay_pairs
                ]
                attempted_date_values.difference_update(replay_days)
                completed_date_values.difference_update(replay_days)
                completed = len(attempted_date_values)
                print(json.dumps({
                    "symbol_map_changed": True,
                    "targeted_absence_pairs_requeued": len(replay_pairs),
                    "dates_requeued": len(replay_days),
                    "old_absence_rows": old_count,
                    "remaining_prior_absence_rows": len(absence_exceptions),
                }), flush=True)

            existing.update((pd.Timestamp(row["date"]), str(row.get("requested_symbol", row["symbol"])).upper()) for row in additions)
            existing_raw_keys.update((pd.Timestamp(row["date"]), str(row["symbol"]).upper()) for row in additions)
            existing.update((pd.Timestamp(row["date"]), str(row.get("requested_symbol", row["symbol"])).upper()) for row in absence_exceptions)
            print(f"Resuming repair: {completed}/{len(all_days)} attempted dates; {len(additions)} persisted rows.", flush=True)

    def write_checkpoint():
        # Small, durable progress record so a runner interruption is diagnosable.
        checkpoint = {
            "status": "complete" if inventory_attempts_complete(attempted_date_values, len(all_days)) else "in_progress",
            "completed_dates": int(len(completed_date_values)),
            "attempted_dates": int(len(attempted_date_values)),
            "total_dates": int(len(all_days)),
            "date_start": str(start.date()),
            "date_end": str(end.date()),
            "membership_warmup_sessions": int(a.membership_warmup_sessions),
            "target_inventory_sha256": target_inventory_hash,
            "symbol_map_sha256": symbol_map_hash,
            "completed_date_values": sorted(completed_date_values),
            "attempted_date_values": sorted(attempted_date_values),
            "targeted_gap_spans": int(len(gap_spans)),
            "target_symbol_date_pairs": int(sum(len(symbols) for symbols in targets_by_date.values())),
            "fetched_dates": int(fetched_days),
            "added_rows": int(len(additions)),
            "alternate_series_rows_added": int(alternate_series_rows_added),
            "already_present_alias_matches": int(already_present_alias_matches),
            "already_present_alternate_series_pairs": int(already_present_alternate_series_pairs),
            "unresolved_absence_pairs": int(len(absence_exceptions)),
            "fetch_error_dates": int(len(fetch_errors)),
            "elapsed_seconds": round(time.monotonic() - run_started, 1),
            "last_updated_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "benchmark_presence": benchmark_presence_counts,
            "non_eq_target_presence": {
                symbol: dict(series_counts)
                for symbol, series_counts in sorted(non_eq_target_presence_counts.items())
            },
            "recent_errors": fetch_errors[-20:],
            "fetch_errors": fetch_errors,
            "diagnostic_examples": archive_diagnostic_examples[-20:],
            "non_eq_examples": non_eq_target_presence_examples[-20:],
            "note": "Progress checkpoint only; not a readiness report and not evidence of no-trade.",
        }
        pd.DataFrame(additions, columns=base.columns).to_csv(additions_path, index=False)
        pd.DataFrame(absence_exceptions, columns=["date", "symbol", "exchange_symbol_checked", "series", "status", "verification_source"]).to_csv(absences_path, index=False)
        temp_path = checkpoint_path.with_suffix(".tmp")
        temp_path.write_text(json.dumps(checkpoint, indent=2, default=str), encoding="utf-8")
        temp_path.replace(checkpoint_path)

    with ThreadPoolExecutor(max_workers=max(1, min(a.workers, 6))) as pool:
        pending_days = [day for day in all_days if pd.Timestamp(day).date().isoformat() not in attempted_date_values]
        if a.max_dates > 0:
            pending_days = pending_days[:a.max_dates]
        futures = {pool.submit(fetch_day, day): day for day in pending_days}
        for future in as_completed(futures):
            day = pd.Timestamp(futures[future])
            target_symbols = targets_by_date[day]
            try:
                _, parsed, parsed_all, err = future.result()
            except Exception as exc:
                parsed = None
                parsed_all = None
                err = f"{type(exc).__name__}: {str(exc)[:220]}"

            attempted_date_values.add(day.date().isoformat())
            if err is not None or parsed is None:
                fetch_errors = [item for item in fetch_errors if item.get("date") != day.date().isoformat()]
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
                        if (day, exchange) in existing_eq_raw_keys:
                            already_present_alias_matches += 1
                        else:
                            already_present_alternate_series_pairs += 1
                        continue
                    matched = parsed_by_symbol.get(exchange)
                    matched_from_alternate_series = False
                    if matched is None or matched.empty:
                        # Keep BE/BZ observations as genuine prices without
                        # relabeling them as EQ. These series can support a
                        # continuous price mark; execution eligibility is
                        # evaluated separately from price continuity.
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
                        alternate = pd.DataFrame()
                        if all_series_rows is not None and not all_series_rows.empty:
                            alternate = all_series_rows.loc[
                                all_series_rows["series"].astype(str).str.strip().str.upper().isin(ALTERNATE_PRICE_SERIES)
                                & pd.to_numeric(all_series_rows["close"], errors="coerce").gt(0)
                            ].copy()
                        if not alternate.empty:
                            candidate_series = alternate["series"].astype(str).str.strip().str.upper().unique()
                            candidate_closes = pd.to_numeric(alternate["close"], errors="coerce").dropna().unique()
                            if len(candidate_series) == 1 and len(candidate_closes) == 1:
                                matched = alternate
                                matched_from_alternate_series = True
                            else:
                                absence_exceptions.append({
                                    "date": day.date().isoformat(),
                                    "symbol": requested,
                                    "exchange_symbol_checked": exchange,
                                    "series": "|".join(candidate_series.astype(str)),
                                    "status": "unresolved_ambiguous_alternate_series",
                                    "verification_source": "NSE bhavcopy contains multiple alternate-series price candidates; independent review required",
                                })
                                continue
                        else:
                            # The symbol is absent from all price-continuity
                            # series. Presence in a debt/other series is not
                            # evidence of an equity price or a no-trade day.
                            absence_exceptions.append({
                                "date": day.date().isoformat(),
                                "symbol": requested,
                                "exchange_symbol_checked": exchange,
                                "series": "|".join(other_series) if other_series else "EQ",
                                "status": "unresolved_archive_absence",
                                "verification_source": "NSE bhavcopy has no matching EQ/BE/BZ price row; listing/suspension status needs independent verification",
                            })
                            continue

                    row = matched.iloc[-1].to_dict()
                    if matched_from_alternate_series:
                        alternate_series_rows_added += 1
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
                    if str(new.get("series", "EQ")).strip().upper() == "EQ":
                        existing_eq_raw_keys.add((day, exchange))

            if err is None and parsed is not None:
                completed_date_values.add(day.date().isoformat())
                fetch_errors = [item for item in fetch_errors if item.get("date") != day.date().isoformat()]
            completed += 1
            if completed % 25 == 0 or completed == len(all_days):
                elapsed = time.monotonic() - run_started
                rate = completed / elapsed if elapsed > 0 else 0.0
                eta = (len(all_days) - completed) / rate if rate > 0 else None
                print(
                    f"bhavcopy dates {completed}/{len(all_days)}; fetched={fetched_days}; "
                    f"added={len(additions)}; unresolved_absences={len(absence_exceptions)}; "
                    f"errors={len(fetch_errors)}; elapsed_s={elapsed:.0f}; "
                    f"rate_dates_s={rate:.3f}; eta_s={eta:.0f}" if eta is not None else
                    f"bhavcopy dates {completed}/{len(all_days)}; fetched={fetched_days}; "
                    f"added={len(additions)}; unresolved_absences={len(absence_exceptions)}; "
                    f"errors={len(fetch_errors)}; elapsed_s={elapsed:.0f}; rate_dates_s={rate:.3f}",
                    flush=True,
                )
            if completed % 100 == 0:
                write_checkpoint()

    # Always persist the final state of this batch, including short batches and
    # inventories that did not land exactly on a 100-date boundary.
    write_checkpoint()

    # Keep raw rows as downloaded; no-trade marks are stored separately and
    # may only be used by the backtest to carry forward a mark, never as prices.
    add_df = pd.DataFrame(additions, columns=base.columns) if additions else pd.DataFrame(columns=base.columns)
    result = pd.concat([raw_all, add_df], ignore_index=True, sort=False)
    result = result.dropna(subset=["date", "symbol"])
    result = deduplicate_price_rows(result)
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
        "symbol_lineage": {
            "rows": int(len(rename_rows)),
            "sha256": symbol_map_hash,
            "supplemental_file": str(a.symbol_map_supplement),
        },
        "membership_scope": {
            "membership_file": str(membership_path),
            "warmup_sessions_before_membership": int(a.membership_warmup_sessions),
            "membership_aliases_matched": int(len(membership_windows)),
            "all_history_candidate_gap_pairs": int(candidate_missing_pairs_unfiltered),
            "pairs_excluded_outside_membership_window": int(excluded_outside_membership_window),
            "target_inventory_sha256": target_inventory_hash,
        },
        "minimum_valid_bhavcopy_eq_rows": int(a.min_bhavcopy_eq_rows),
        "workers": int(max(1, min(a.workers, 6))),
        "internal_gap_spans_targeted": int(len(gap_spans)),
        "target_symbol_date_pairs": int(sum(len(x) for x in targets_by_date.values())),
        "unique_bhavcopy_dates_attempted": int(len(all_days)),
        "bhavcopy_dates_parsed": int(fetched_days),
        "fetch_error_dates": int(len(fetch_errors)),
        "rows_before": int(len(raw_all)),
        "rows_added": int(len(additions)),
        "eq_rows_added": int(sum(1 for row in additions if str(row.get("series", "EQ")).strip().upper() == "EQ")),
        "alternate_series_rows_added": int(alternate_series_rows_added),
        "alternate_series_rows_added_by_series": pd.Series([
            str(row.get("series", "EQ")).strip().upper()
            for row in additions if str(row.get("series", "EQ")).strip().upper() in ALTERNATE_PRICE_SERIES
        ]).value_counts().to_dict(),
        "rows_after": int(len(result)),
        "verified_no_trade_pairs": verified_target_no_trade_pairs,
        "approved_ledger_rows_total": int(len(no_trade_df)),
        "archive_absence_review_pairs": int(len(exception_df)),
        "already_present_alias_matches": int(already_present_alias_matches),
        "already_present_alternate_series_pairs": int(already_present_alternate_series_pairs),
        "unresolved_target_pairs_due_to_fetch_errors": int(sum(x["target_symbols"] for x in fetch_errors)),
        "accounted_target_pairs": int(
            len(additions) + verified_target_no_trade_pairs + already_present_alias_matches
            + already_present_alternate_series_pairs + len(exception_df)
            + sum(x["target_symbols"] for x in fetch_errors)
        ),
        "status": ("IN_PROGRESS" if not inventory_attempts_complete(attempted_date_values, len(all_days)) else ("BLOCKED" if fetch_errors or len(exception_df) else "PASS")),
        "top_added_symbols": pd.Series([str(x.get("requested_symbol", x.get("symbol", ""))) for x in additions]).value_counts().head(30).to_dict(),
        "archive_symbol_presence_diagnostics": {
            "benchmark_presence_counts": benchmark_presence_counts,
            "examples": archive_diagnostic_examples,
            "unresolved_targets_found_in_non_eq_series": {
                symbol: dict(series_counts)
                for symbol, series_counts in sorted(non_eq_target_presence_counts.items())
            },
            "non_eq_series_examples": non_eq_target_presence_examples,
            "interpretation": "EQ rows are preferred. Actual BE/BZ closes are retained as alternate-series price observations for continuity without relabeling them as EQ; series eligibility remains a separate execution concern. Other series do not resolve price gaps.",
        },
        "gaps": gap_spans,
        "fetch_errors": fetch_errors,
        "verified_no_trade_ledger": str(nt_path),
        "unresolved_absence_exceptions": str(exceptions_path),
        "approved_no_trade_evidence_fields": ["verification_source", "evidence_reference"],
        "note": "Only actual NSE bhavcopy prices are added. Missing observations are targeted only inside point-in-time Nifty 500 membership intervals plus a 252-session signal warm-up. EQ is preferred; actual BE/BZ closes may be added with their series preserved for price continuity. Unresolved absences are not converted to synthetic prices or no-trade approvals.",
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
