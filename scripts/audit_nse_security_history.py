#!/usr/bin/env python3
"""Capture exact-date NSE security-wise history responses for unresolved price gaps.

This is an evidence-gathering diagnostic only. An empty response is NOT proof of
no-trade, suspension, delisting, or a valid close; it never edits price/no-trade
ledgers. Raw response bodies and request metadata are retained for review.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ENDPOINT = "https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData"
LANDING = "https://www.nseindia.com/report-detail/eq_security"
TARGETS = [
    {"symbol": "MAHSCOOTER", "date": "28-10-2024", "series": "EQ"},
    {"symbol": "MAHSCOOTER", "date": "29-10-2025", "series": "EQ"},
    {"symbol": "MAHSCOOTER", "date": "30-10-2025", "series": "EQ"},
]
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/130.0.0.0 Safari/537.36",
    "Accept": "text/csv,application/csv,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": LANDING,
    "X-Requested-With": "XMLHttpRequest",
}


def main() -> int:
    out = Path(os.environ.get("NSE_AUDIT_OUT", "results/nse_security_history_audit"))
    raw_dir = out / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    session.headers.update(HEADERS)
    landing_status = None
    landing_error = None
    try:
        landing = session.get(LANDING, timeout=30)
        landing_status = landing.status_code
        landing.raise_for_status()
    except Exception as exc:
        landing_error = f"{type(exc).__name__}: {str(exc)[:300]}"

    records = []
    for i, target in enumerate(TARGETS):
        target_day = datetime.strptime(target["date"], "%d-%m-%Y").date()
        # The previous exact-date queries returned empty CSVs even for dates
        # surrounded by known trading sessions. Probe a wider range to validate
        # the endpoint response and capture neighboring sessions for review.
        params = {
            "symbol": target["symbol"],
            "from": (target_day - timedelta(days=7)).strftime("%d-%m-%Y"),
            "to": (target_day + timedelta(days=7)).strftime("%d-%m-%Y"),
            "series": target["series"],
            "type": "priceVolumeDeliverable",
            "csv": "true",
        }
        item = {
            **target,
            "query_kind": "seven-calendar-day-window-each-side",
            "query_window": {"from": params["from"], "to": params["to"]},
            "endpoint": ENDPOINT,
            "params": params,
            "captured_at_utc": datetime.now(timezone.utc).isoformat(),
            "landing_status": landing_status,
            "landing_error": landing_error,
        }
        try:
            response = session.get(ENDPOINT, params=params, timeout=45)
            body = response.content
            raw_path = raw_dir / f"{target['symbol']}_{target['date'].replace('-', '')}_{target['series']}.body"
            raw_path.write_bytes(body)
            item.update({
                "http_status": response.status_code,
                "final_url": response.url,
                "content_type": response.headers.get("Content-Type", ""),
                "body_path": str(raw_path),
                "body_bytes": len(body),
                "body_sha256": hashlib.sha256(body).hexdigest(),
                "response_preview": response.text[:1200],
                "request_error": None,
            })
            # Only parse a response that looks like CSV; keep original bytes in
            # all cases and never equate an empty/no-record response with no-trade.
            if response.ok and response.text.strip() and "html" not in response.headers.get("Content-Type", "").lower():
                try:
                    rows = list(csv.DictReader(io.StringIO(response.text)))
                    item["parsed_row_count"] = len(rows)
                    item["parsed_rows"] = rows
                except Exception as exc:
                    item["parse_error"] = f"{type(exc).__name__}: {str(exc)[:200]}"
            else:
                item["parsed_row_count"] = None
        except Exception as exc:
            item.update({
                "http_status": None,
                "request_error": f"{type(exc).__name__}: {str(exc)[:300]}",
                "parsed_row_count": None,
            })
        records.append(item)
        if i < len(TARGETS) - 1:
            time.sleep(2.0)

    report = {
        "purpose": "official-source retrieval diagnostic only; not a no-trade or price approval",
        "source": ENDPOINT,
        "landing_page": LANDING,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation_rule": "This run queries a ±7-calendar-day window around each target. Returned neighboring rows help validate endpoint behavior but are not approvals for target dates. Only a returned, validated official price row for the exact target date may be reviewed as price evidence. Empty, blocked, malformed, or missing rows remain unresolved.",
        "targets": records,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({
        "report": str(out / "report.json"),
        "targets": [
            {k: item.get(k) for k in ("symbol", "date", "query_kind", "query_window", "http_status", "content_type", "body_bytes", "parsed_row_count", "request_error", "parse_error")}
            for item in records
        ],
        "interpretation": report["interpretation_rule"],
    }, indent=2))
    # Retrieval failures are visible in the artifact, but do not create approvals.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
