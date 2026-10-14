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
    """Return normalized date, symbol, series, OHLCV fields from the NSE CSV."""
    if not isinstance(payload, str) or not payload.strip():
        raise ValueError("empty API response")
    if "<html" in payload[:1000].lower() or "<!doctype" in payload[:1000].lower():
        raise ValueError("API returned HTML instead of CSV")
    raw = pd.read_csv(io.StringIO(payload), skipinitialspace=True)
    cols = {norm(c): c for c in raw.columns}
    aliases = {
        "symbol": ["symbol", "ticker_symbol", "ch_symbol"], "series": ["series", "security_series", "ch_series"],
        "date": ["date", "trading_date", "ch_timestamp"], "prev_close": ["prev_close", "previous_close", "ch_previous_cls"],
        "open": ["open_price", "open", "ch_opening_price"], "high": ["high_price", "high", "ch_trade_high_price"],
        "low": ["low_price", "low", "ch_trade_low_price"], "last": ["last_price", "last", "ch_last_traded_price"],
        "close": ["close_price", "close", "ch_closing_price"], "vwap": ["average_price", "avg_price", "vwap", "ch_avg_price"],
        "volume": ["total_traded_quantity", "total_traded_qty", "volume", "ch_tot_traded_qty"],
        "traded_value": ["turnover_₹", "turnover", "traded_value", "ch_tot_traded_val"],
        "num_trades": ["no._of_trades", "no_of_trades", "num_trades", "ch_total_trades"],
        "deliverable_qty": ["deliverable_qty", "ch_deliv_qty"],
        "deliverable_pct": ["%_dly_qt_to_traded_qty", "dly_qt_to_traded_qty", "ch_deliv_per"],
    }
    rename = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in cols:
                rename[cols[candidate]] = target
                break
    raw = raw.rename(columns=rename)
    need = {"series", "date", "close"}
    if not need.issubset(raw.columns):
        raise ValueError(f"missing required columns {sorted(need - set(raw.columns))}")
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


def classify_target_date(history, target_date):
    target = pd.Timestamp(target_date).normalize()
    dates = pd.to_datetime(history["date"], errors="coerce").dt.normalize()
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
        response, error = None, ""
        for attempt in range(max(1, a.retries)):
            try:
                trial = session.get(API, params=params, timeout=45)
                if trial.status_code == 200 and "text/csv" in trial.headers.get("content-type", "").lower():
                    response = trial
                    break
                error = f"HTTP {trial.status_code}; content-type={trial.headers.get('content-type', '')}"
            except requests.RequestException as exc_error:
                error = repr(exc_error)
            if attempt + 1 < max(1, a.retries):
                time.sleep(attempt + 1)
        check = {
            "date": target.date().isoformat(), "symbol": wanted, "exchange_symbol_queried": exchange,
            "query_from": start.date().isoformat(), "query_to": end.date().isoformat(),
            "query_url": response.url if response is not None else requests.Request(API, params=params).prepare().url,
            "outcome": "unverified", "error": error,
        }
        if response is None:
            remaining.append(exc.to_dict())
            checks.append(check)
            time.sleep(max(0, a.pause_seconds))
            continue
        check.update({
            "http_status": int(response.status_code), "response_bytes": len(response.content),
            "response_sha256": hashlib.sha256(response.content).hexdigest(),
        })
        try:
            history = parse_security_history(response.text, requested_symbol=exchange)
        except Exception as parse_error:
            check["error"] = f"parse error: {parse_error}"
            remaining.append(exc.to_dict())
            checks.append(check)
            time.sleep(max(0, a.pause_seconds))
            continue
        check["rows_returned"] = int(len(history))
        check["returned_dates"] = [d.date().isoformat() for d in history["date"].drop_duplicates().sort_values()]
        outcome, exact = classify_target_date(history, target)
        check["outcome"] = outcome
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
