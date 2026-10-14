#!/usr/bin/env python3
"""Cross-check unresolved gaps using NSE's per-security historical price-volume API.

Only actual EQ prices are appended. No-trade is accepted only when the API
response is valid and contains same-security observations on both sides of the
target date while omitting that date. Failures remain unresolved.
"""
import argparse
import hashlib
import io
import json
import time
from pathlib import Path

import pandas as pd
import requests

try:
    from scripts.repair_price_gaps_bhavcopy import exchange_symbol
    from scripts.symbol_lineage import load_symbol_rename_rows, terminal_symbol_aliases
except ModuleNotFoundError:
    from repair_price_gaps_bhavcopy import exchange_symbol
    from symbol_lineage import load_symbol_rename_rows, terminal_symbol_aliases

API = "https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData"
WARMUP = "https://www.nseindia.com/report-detail/eq_security"
SOURCE = "NSE security-wise historical price-volume API (EQ)"


def norm(value):
    value = str(value).replace("\ufeff", "").replace("\xa0", " ").strip().strip('"')
    return "_".join(value.lower().split())


def parse_security_history(payload, requested_symbol=None):
    """Return normalized date, symbol, series, OHLCV fields from NSE CSV or JSON.

    NSE's endpoint can return CSV columns (sometimes without a symbol column)
    or a JSON envelope with camel-cased source fields. A response is accepted
    only when dates, series and positive-close semantics can be evaluated;
    an empty/partial response never establishes no-trade.
    """
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("empty API response")
    if "<html" in payload[:1000].lower() or "<!doctype" in payload[:1000].lower():
        raise ValueError("API returned HTML instead of CSV")

    # The endpoint has been observed to emit a JSON array/object despite a CSV
    # request. Parse that format explicitly rather than treating it as a header.
    stripped = payload.lstrip()
    if stripped.startswith("{") or stripped.startswith("["):
        try:
            obj = __import__("json").loads(payload)
            if isinstance(obj, dict):
                records = obj.get("data", obj.get("rows", []))
            else:
                records = obj
            if not isinstance(records, list):
                raise ValueError("JSON response does not contain a row list")
            raw = pd.DataFrame(records)
        except (ValueError, TypeError) as exc:
            raise ValueError(f"invalid security-history JSON: {exc}") from exc
    else:
        raw = pd.read_csv(io.StringIO(payload), skipinitialspace=True)

    def normalized_column(value):
        # Normalize both spaced labels and source JSON keys such as CH_TIMESTAMP.
        text = str(value).replace("\ufeff", "").replace("\xa0", " ").strip().strip('"')
        return "_".join(text.lower().split())

    cols = {normalized_column(c): c for c in raw.columns}
    aliases = {
        "symbol": ["symbol", "ticker_symbol", "ch_symbol"],
        "series": ["series", "security_series", "ch_series"],
        "date": ["date", "trading_date", "ch_timestamp", "mtimestamp"],
        "prev_close": ["prev_close", "previous_close", "ch_previous_cls", "ch_previous_cls_price"],
        "open": ["open_price", "open", "ch_opening_price"],
        "high": ["high_price", "high", "ch_trade_high_price"],
        "low": ["low_price", "low", "ch_trade_low_price"],
        "last": ["last_price", "last", "ch_last_traded_price"],
        "close": ["close_price", "close", "ch_closing_price"],
        "vwap": ["average_price", "avg_price", "vwap", "ch_avg_price"],
        "volume": ["total_traded_quantity", "total_traded_qty", "volume", "ch_tot_traded_qty"],
        "traded_value": ["turnover_₹", "turnover", "traded_value", "ch_tot_traded_val"],
        "num_trades": ["no._of_trades", "no_of_trades", "num_trades", "ch_total_trades"],
        "deliverable_qty": ["deliverable_qty", "ch_deliv_qty", "cop_deliv_qty"],
        "deliverable_pct": ["%_dly_qt_to_traded_qty", "dly_qt_to_traded_qty", "ch_deliv_per", "cop_deliv_perc"],
    }
    rename = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in cols:
                rename[cols[candidate]] = target
                break
    raw = raw.rename(columns=rename)
    # An explicit empty JSON data array is a valid zero-row response, but it
    # contains no evidence for a no-trade disposition. Keep it empty so the
    # caller classifies the target as unverified. CSV payloads without the
    # minimum schema remain parser errors.
    if raw.empty and not len(raw.columns):
        return pd.DataFrame(columns=["symbol", "series", "date", "close"])
    need = {"series", "date", "close"}
    if not need.issubset(raw.columns):
        raise ValueError(f"missing required columns {sorted(need - set(raw.columns))}; got {list(raw.columns)}")
    if "symbol" not in raw.columns:
        if not requested_symbol:
            raise ValueError("response omits symbol and no requested_symbol was supplied")
        raw["symbol"] = str(requested_symbol).strip().upper()

    raw["symbol"] = raw["symbol"].astype(str).str.strip().str.upper()
    raw["series"] = raw["series"].astype(str).str.strip().str.upper()
    raw["date"] = pd.to_datetime(raw["date"], errors="coerce", format="mixed", dayfirst=True)
    numeric = ["prev_close", "open", "high", "low", "last", "close", "vwap",
               "volume", "traded_value", "num_trades", "deliverable_qty", "deliverable_pct"]
    for col in numeric:
        if col in raw:
            raw[col] = pd.to_numeric(raw[col].astype(str).str.replace(",", "", regex=False), errors="coerce")
    raw = raw.dropna(subset=["symbol", "date"])
    raw = raw.loc[raw["series"].eq("EQ")].copy()
    return raw.sort_values(["date", "symbol"]).reset_index(drop=True)

def _exchange_calendar_dates(values):
    """Normalize date-like source values to naive exchange calendar dates.

    The NSE endpoint has emitted both date-only strings and ISO timestamps
    with timezone suffixes. For daily price records the source calendar date,
    not a UTC-converted instant, is the relevant key.
    """
    def as_calendar_date(value):
        if pd.isna(value):
            return pd.NaT
        parsed = pd.to_datetime(value, errors="coerce", format="mixed", dayfirst=True)
        if pd.isna(parsed):
            return pd.NaT
        # Keep the date represented in the source value even if it carries a
        # timezone; do not convert midnight UTC to the prior Indian calendar day.
        return pd.Timestamp(parsed.date())
    return pd.to_datetime(values.map(as_calendar_date), errors="coerce").dt.normalize()


def classify_target_date(history, target_date):
    target = pd.Timestamp(target_date).tz_localize(None).normalize() if pd.Timestamp(target_date).tzinfo else pd.Timestamp(target_date).normalize()
    dates = _exchange_calendar_dates(history["date"])
    exact = history.loc[dates.eq(target)]
    if not exact.empty:
        valid_close = exact["close"].notna() & exact["close"].gt(0)
        if len(exact) != 1:
            return "unverified_duplicate_source_rows", history.iloc[0:0].copy()
        if not bool(valid_close.iloc[0]):
            return "unverified_target_row_without_valid_close", history.iloc[0:0].copy()
        return "observed_price", exact
    valid_price = history["close"].notna() & history["close"].gt(0)
    before = dates.lt(target) & valid_price
    after = dates.gt(target) & valid_price
    if before.any() and after.any():
        return "verified_no_trade", history.iloc[0:0].copy()
    return "unverified", history.iloc[0:0].copy()


def select_target_probe(probes, target_date):
    """Choose a single valid NSE response that can resolve a target date.

    NSE sometimes returns truncated history for a broad date range. A partial
    response must not prevent narrower probes from running, and observations
    from separate responses are never stitched together to infer no-trade.
    """
    last = None
    target = pd.Timestamp(target_date).tz_localize(None).normalize() if pd.Timestamp(target_date).tzinfo else pd.Timestamp(target_date).normalize()
    for probe in probes:
        outcome, exact = classify_target_date(probe["history"], target_date)
        if outcome == "observed_price":
            return probe, outcome, exact
        if outcome == "verified_no_trade":
            # Do not accept a broad response as no-trade: a truncated payload
            # could contain rows on both sides while omitting a real target row.
            # Require a narrow (<=3 calendar days either side) query and nearby
            # bracketing EQ prices from that same response.
            history = probe["history"]
            valid = history.loc[history["close"].notna() & history["close"].gt(0)].copy()
            dates = _exchange_calendar_dates(valid["date"])
            before = dates[dates.lt(target)]
            after = dates[dates.gt(target)]
            radius = int(probe.get("radius_days", 999))
            if not before.empty and not after.empty and radius <= 3:
                if (target - before.max()).days <= 3 and (after.min() - target).days <= 3:
                    return probe, outcome, exact
            last = (probe, "unverified", exact)
        else:
            last = (probe, outcome, exact)
    if last is not None:
        return last
    return None, "unverified", pd.DataFrame(columns=["symbol", "series", "date", "close"])


def _date_key(series):
    return pd.to_datetime(series, errors="coerce", format="mixed").dt.strftime("%Y-%m-%d")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--prices", required=True)
    p.add_argument("--exceptions", required=True)
    p.add_argument("--no-trade", required=True)
    p.add_argument("--repair-report", required=True)
    p.add_argument("--symbol-map", default="data/input/verified_symbol_map.csv")
    p.add_argument("--symbol-map-supplement", default="data/reference/nse_historical_symbol_changes.csv")
    p.add_argument("--audit-report", default="results/price_quality/security_history_gap_audit.json")
    p.add_argument("--window-days", type=int, default=5)
    p.add_argument("--retries", type=int, default=3)
    p.add_argument("--pause-seconds", type=float, default=0.3)
    a = p.parse_args()
    prices_path, exceptions_path = Path(a.prices), Path(a.exceptions)
    no_trade_path, repair_path, audit_path = Path(a.no_trade), Path(a.repair_report), Path(a.audit_report)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    if not exceptions_path.exists() or exceptions_path.stat().st_size == 0:
        audit_path.write_text(json.dumps({"status": "PASS_NO_REMAINING_ABSENCES", "checks": []}, indent=2))
        print("No unresolved archive absences.")
        return

    prices = pd.read_csv(prices_path, low_memory=False)
    exceptions = pd.read_csv(exceptions_path, low_memory=False).fillna("")
    no_trade = pd.read_csv(no_trade_path, low_memory=False) if no_trade_path.exists() and no_trade_path.stat().st_size else pd.DataFrame(
        columns=["date", "symbol", "exchange_symbol_checked", "series", "status", "verification_source", "evidence_reference"]
    )
    rename_rows = load_symbol_rename_rows(a.symbol_map, a.symbol_map_supplement)
    terminal_aliases = terminal_symbol_aliases(rename_rows)
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/131.0 Safari/537.36",
        "Accept": "text/csv,application/json,*/*", "Referer": "https://www.nseindia.com/",
    })
    try:
        session.get(WARMUP, timeout=30)
    except requests.RequestException:
        pass

    key_col = "canonical_symbol" if "canonical_symbol" in prices.columns else (
        "requested_symbol" if "requested_symbol" in prices.columns else "symbol"
    )
    price_dates = pd.to_datetime(prices["date"], errors="coerce", format="mixed")
    existing = {
        (pd.Timestamp(d).date().isoformat(), str(sym).strip().upper())
        for d, sym in zip(price_dates, prices[key_col])
        if not pd.isna(d) and str(sym).strip().upper() not in {"", "NAN", "NONE", "<NA>"}
    }
    additions, new_no_trade, remaining, checks = [], [], [], []
    for _, exc in exceptions.iterrows():
        target = pd.to_datetime(exc.get("date"), errors="coerce", format="mixed")
        wanted = str(exc.get("symbol", "")).strip().upper()
        if pd.isna(target) or not wanted:
            remaining.append(exc.to_dict())
            checks.append({"date": str(exc.get("date", "")), "symbol": wanted, "outcome": "invalid_exception"})
            continue
        target = pd.Timestamp(target).normalize()
        start, end = target - pd.Timedelta(days=max(1, a.window_days)), target + pd.Timedelta(days=max(1, a.window_days))
        exchange = exchange_symbol(wanted, target, rename_rows)
        params = {
            "symbol": exchange, "from": start.strftime("%d-%m-%Y"), "to": end.strftime("%d-%m-%Y"),
            "series": "EQ", "type": "priceVolumeDeliverable", "csv": "true", "dataType": "priceVolumeDeliverable",
        }
        # Probe broad-to-narrow windows. The NSE endpoint can truncate a broad
        # response, so an earlier valid-but-partial payload must not suppress
        # later probes.
        start_offsets = [max(1, a.window_days), 2, 1]
        request_variants = []
        seen_ranges = set()
        for radius in start_offsets:
            range_start = target - pd.Timedelta(days=radius)
            range_end = target + pd.Timedelta(days=radius)
            date_range = (range_start.strftime("%d-%m-%Y"), range_end.strftime("%d-%m-%Y"))
            if date_range in seen_ranges:
                continue
            seen_ranges.add(date_range)
            for accept, remove_fields in [
                ("text/csv,application/json,*/*", set()),
                ("application/json,*/*", {"csv", "dataType"}),
            ]:
                request_params = {**params, "from": date_range[0], "to": date_range[1]}
                for field in remove_fields:
                    request_params.pop(field, None)
                request_variants.append((request_params, accept, radius))
        selected_probe = None
        selected_outcome = "unverified"
        selected_exact = pd.DataFrame(columns=["symbol", "series", "date", "close"])
        attempts = []
        probe_results = []
        last_error = ""
        request_diagnostics = []
        for variant_params, accept, radius in request_variants:
            for attempt in range(max(1, a.retries)):
                try:
                    trial = session.get(
                        API, params=variant_params,
                        headers={"Accept": accept}, timeout=45
                    )
                    content_type = trial.headers.get("content-type", "").lower()
                    if trial.status_code == 200 and (
                        "text/csv" in content_type or "application/json" in content_type
                    ) and trial.text.strip() and not trial.text.lstrip().lower().startswith(("<html", "<!doctype")):
                        try:
                            candidate_history = parse_security_history(trial.text, requested_symbol=exchange)
                        except Exception as parse_error:
                            last_error = f"parse error: {parse_error}"
                            attempts.append({
                                "url": trial.url, "variant": "csv" if "csv" in accept else "json",
                                "attempt": attempt + 1, "error": last_error,
                            })
                            # Try a different query variant/window; a malformed
                            # response is not evidence for either price or no-trade.
                            break
                        dates_returned = [
                            d.date().isoformat()
                            for d in candidate_history["date"].drop_duplicates().sort_values()
                        ]
                        diagnostic = {
                            "url": trial.url,
                            "http_status": int(trial.status_code),
                            "content_type": content_type,
                            "response_bytes": len(trial.content),
                            "response_sha256": hashlib.sha256(trial.content).hexdigest(),
                            "rows_returned": int(len(candidate_history)),
                            "returned_dates": dates_returned,
                            "variant": "csv" if "csv" in accept else "json",
                            "probe_radius_days": radius,
                        }
                        request_diagnostics.append(diagnostic)
                        probe_results.append({
                            "response": trial,
                            "history": candidate_history,
                            "diagnostic": diagnostic,
                            "radius_days": radius,
                        })
                        selected_probe, selected_outcome, _ = select_target_probe(probe_results, target)
                        if selected_outcome in {"observed_price", "verified_no_trade"}:
                            break
                        # This payload parsed but is insufficient (for example,
                        # only pre-target rows); continue to the narrower window.
                        break
                    last_error = (
                        f"HTTP {trial.status_code}; content-type={content_type}; bytes={len(trial.content)}"
                    )
                    attempts.append({
                        "url": trial.url, "variant": "csv" if "csv" in accept else "json",
                        "attempt": attempt + 1, "error": last_error,
                    })
                except requests.RequestException as request_error:
                    last_error = repr(request_error)
                    attempts.append({
                        "url": requests.Request(API, params=variant_params).prepare().url,
                        "variant": "csv" if "csv" in accept else "json",
                        "attempt": attempt + 1, "error": last_error,
                    })
                if attempt + 1 < max(1, a.retries):
                    time.sleep(attempt + 1)
            selected_probe, selected_outcome, selected_exact = select_target_probe(probe_results, target)
            if selected_probe is not None and selected_outcome in {"observed_price", "verified_no_trade"}:
                break

        check = {
            "date": target.date().isoformat(), "symbol": wanted, "exchange_symbol_queried": exchange,
            "query_from": start.date().isoformat(), "query_to": end.date().isoformat(),
            "query_url": selected_probe["response"].url if selected_probe is not None else requests.Request(API, params=params).prepare().url,
            "outcome": selected_outcome if selected_probe is not None else "unverified",
            "error": "" if selected_probe is not None else (last_error or "NSE security-history endpoint returned no usable CSV/JSON payload"),
            "probe_count": len(probe_results),
            "probes": request_diagnostics,
            "attempt_errors": attempts,
        }
        if selected_probe is None:
            remaining.append(exc.to_dict())
            checks.append(check)
            time.sleep(max(0, a.pause_seconds))
            continue

        response = selected_probe["response"]
        history = selected_probe["history"]
        outcome = selected_outcome
        exact = selected_exact
        check.update({
            "http_status": int(response.status_code),
            "response_bytes": len(response.content),
            "response_sha256": hashlib.sha256(response.content).hexdigest(),
            "rows_returned": int(len(history)),
            "returned_dates": [d.date().isoformat() for d in history["date"].drop_duplicates().sort_values()],
        })
        pair = (target.date().isoformat(), wanted)
        if outcome == "observed_price" and pair not in existing:
            if len(exact) != 1:
                check["outcome"] = "unverified_duplicate_source_rows"
                remaining.append(exc.to_dict())
            else:
                row = exact.iloc[0]
                vals = {col: pd.NA for col in prices.columns}
                field_map = {
                    "date": target.date().isoformat(), "symbol": exchange, "series": "EQ",
                    "prev_close": row.get("prev_close", pd.NA), "open": row.get("open", pd.NA),
                    "high": row.get("high", pd.NA), "low": row.get("low", pd.NA),
                    "last": row.get("last", pd.NA), "close": row.get("close", pd.NA),
                    "vwap": row.get("vwap", pd.NA), "volume": row.get("volume", pd.NA),
                    "turnover ₹": row.get("traded_value", pd.NA), "num_trades": row.get("num_trades", pd.NA),
                    "deliverable_qty": row.get("deliverable_qty", pd.NA), "deliverable_pct": row.get("deliverable_pct", pd.NA),
                    "source_endpoint": "NSE security-wise historical price-volume API",
                    "requested_symbol": wanted, "source_symbol": exchange,
                    "canonical_symbol": terminal_aliases.get(wanted, wanted),
                }
                for col, val in field_map.items():
                    if col in vals:
                        vals[col] = val
                additions.append(vals)
                existing.add(pair)
                check["outcome"] = "observed_price_added"
        elif outcome == "observed_price" and pair in existing:
            check["outcome"] = "already_present"
        elif outcome == "verified_no_trade":
            dates = pd.to_datetime(history["date"], errors="coerce").dt.normalize()
            before, after = history.loc[dates.lt(target), "date"], history.loc[dates.gt(target), "date"]
            check["nearest_observation_before"] = before.max().date().isoformat() if not before.empty else None
            check["nearest_observation_after"] = after.min().date().isoformat() if not after.empty else None
            exists = (
                _date_key(no_trade["date"]).eq(target.date().isoformat())
                & no_trade["symbol"].astype(str).str.strip().str.upper().eq(wanted)
            ).any() if not no_trade.empty else False
            if not exists:
                new_no_trade.append({
                    "date": target.date().isoformat(), "symbol": wanted, "exchange_symbol_checked": exchange,
                    "series": "EQ", "status": "verified_no_trade",
                    "verification_source": SOURCE + "; successful response has adjacent observations but no target-date row",
                    "evidence_reference": check["query_url"],
                })
            else:
                check["outcome"] = "already_verified_no_trade"
        else:
            remaining.append(exc.to_dict())
        checks.append(check)
        time.sleep(max(0, a.pause_seconds))

    if additions:
        prices = pd.concat([prices, pd.DataFrame(additions, columns=prices.columns)], ignore_index=True, sort=False)
        prices.to_csv(prices_path, index=False)
    if new_no_trade:
        no_trade = pd.concat([no_trade, pd.DataFrame(new_no_trade)], ignore_index=True, sort=False)
        no_trade["_date_key"] = _date_key(no_trade["date"])
        no_trade["_symbol_key"] = no_trade["symbol"].astype(str).str.strip().str.upper()
        no_trade = no_trade.drop_duplicates(["_date_key", "_symbol_key"]).drop(columns=["_date_key", "_symbol_key"])
        no_trade.to_csv(no_trade_path, index=False)
    remaining_df = pd.DataFrame(remaining, columns=exceptions.columns)
    remaining_df.to_csv(exceptions_path, index=False)

    if repair_path.exists() and repair_path.stat().st_size:
        report = json.loads(repair_path.read_text())
        report["rows_added"] = int(report.get("rows_added", 0)) + len(additions)
        report["eq_rows_added"] = int(report.get("eq_rows_added", 0)) + len(additions)
        report["rows_after"] = int(len(prices))
        report["verified_no_trade_pairs"] = int(report.get("verified_no_trade_pairs", 0)) + len(new_no_trade)
        report["approved_ledger_rows_total"] = int(len(no_trade))
        report["archive_absence_review_pairs"] = int(len(remaining_df))
        report["already_present_alias_matches"] = int(report.get("already_present_alias_matches", 0)) + sum(
            check.get("outcome") == "already_present" for check in checks
        )
        report["status"] = "BLOCKED" if len(remaining_df) or int(report.get("fetch_error_dates", 0)) else "PASS"
        repair_path.write_text(json.dumps(report, indent=2, default=str))

    audit = {
        "status": "PASS" if not len(remaining_df) else "REVIEW_REQUIRED",
        "history_api": API, "security_history_rows_added": len(additions),
        "verified_no_trade_rows_added": len(new_no_trade), "unresolved_pairs_remaining": len(remaining_df),
        "checks": checks,
    }
    audit_path.write_text(json.dumps(audit, indent=2, default=str))
    print(json.dumps({k: audit[k] for k in [
        "status", "security_history_rows_added", "verified_no_trade_rows_added",
        "unresolved_pairs_remaining", "history_api"
    ]}, indent=2))


if __name__ == "__main__":
    main()
