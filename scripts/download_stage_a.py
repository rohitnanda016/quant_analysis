import argparse, io, json, threading, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd
import requests

URLS = [
    "https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData",
    "https://www.nseindia.com/api/historical/securityArchives",
]
MEM = "data/input/nifty500_membership.csv"
_thread_local = threading.local()


def cc(c):
    c = str(c).replace("\ufeff", "").replace("\xa0", " ").strip().strip('"')
    return " ".join(c.split()).lower()


def session():
    s = getattr(_thread_local, "session", None)
    if s is None:
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0",
            "Accept": "*/*",
            "Referer": "https://www.nseindia.com/",
        })
        try:
            s.get("https://www.nseindia.com/report-detail/eq_security", timeout=30)
        except Exception:
            pass
        _thread_local.session = s
    return s


def get_chunk(sym, a, b, retries=2):
    p = {
        "symbol": sym,
        "from": a.strftime("%d-%m-%Y"),
        "to": b.strftime("%d-%m-%Y"),
        "series": "EQ",
        "type": "priceVolumeDeliverable",
        "csv": "true",
        "dataType": "priceVolumeDeliverable",
    }
    mp = {
        "symbol": "symbol",
        "series": "series",
        "date": "date",
        "prev close": "prev_close",
        "open price": "open",
        "high price": "high",
        "low price": "low",
        "last price": "last",
        "close price": "close",
        "average price": "vwap",
        "total traded quantity": "volume",
        "turnover": "traded_value",
        "no. of trades": "num_trades",
        "deliverable qty": "deliverable_qty",
        "% dly qt to traded qty": "deliverable_pct",
        "deliverableqty": "deliverable_qty",
    }
    last_error = "no response"
    s = session()

    for url in URLS:
        for attempt in range(retries + 1):
            try:
                r = s.get(url, params=p, timeout=45)
                if r.status_code != 200:
                    last_error = f"http_{r.status_code}"
                elif len(r.content) <= 100:
                    last_error = f"empty_http_200_{len(r.content)}"
                else:
                    raw = r.content.decode("utf-8-sig", errors="replace")
                    try:
                        d = pd.read_csv(io.StringIO(raw), skipinitialspace=True)
                    except Exception as e:
                        try:
                            obj = r.json()
                            rows = obj.get("data", obj) if isinstance(obj, dict) else obj
                            d = pd.DataFrame(rows)
                        except Exception as e2:
                            last_error = f"parse_error:{type(e).__name__}/{type(e2).__name__}"
                            d = pd.DataFrame()

                    if not d.empty:
                        d.columns = [cc(x) for x in d.columns]
                        d = d.rename(columns=mp)
                        if "date" not in d.columns or "close" not in d.columns or "symbol" not in d.columns:
                            last_error = "missing_required_columns"
                        else:
                            d["date"] = pd.to_datetime(d["date"], errors="coerce", dayfirst=True)
                            d["symbol"] = d["symbol"].astype(str).str.strip().str.upper()
                            d["source_endpoint"] = url
                            return d, None
                    else:
                        last_error = "empty_dataframe"
            except Exception as e:
                last_error = f"{type(e).__name__}:{str(e)[:180]}"
            if attempt < retries:
                time.sleep(2 ** attempt)

    return pd.DataFrame(), last_error


def fetch_symbol(sym, start, end, chunk_days):
    frames = []
    errors = []
    cur = start
    while cur <= end:
        nxt = min(cur + pd.Timedelta(days=chunk_days - 1), end)
        d, err = get_chunk(sym, cur, nxt)
        if len(d):
            frames.append(d)
        else:
            errors.append({
                "symbol": sym,
                "chunk_start": cur.strftime("%Y-%m-%d"),
                "chunk_end": nxt.strftime("%Y-%m-%d"),
                "error": err,
            })
        cur = nxt + pd.Timedelta(days=1)

    if frames:
        out = pd.concat(frames, ignore_index=True)
        out["requested_symbol"] = sym
        out["source_symbol"] = sym
        return out, errors
    return pd.DataFrame(), errors


p = argparse.ArgumentParser()
p.add_argument("--start", required=True)
p.add_argument("--end", required=True)
p.add_argument("--membership", default=MEM)
p.add_argument("--symbol-map", default="data/input/verified_symbol_map.csv")
p.add_argument("--out", default="data/raw/stage_a_prices.csv")
p.add_argument("--sleep", type=float, default=0.2)
p.add_argument("--chunk-days", type=int, default=365)
p.add_argument("--workers", type=int, default=6)
a = p.parse_args()

start = pd.Timestamp(a.start)
end = pd.Timestamp(a.end)

sm = pd.read_csv(a.symbol_map)
sm["old_symbol"] = sm.old_symbol.astype(str).str.strip().str.upper()
sm["new_symbol"] = sm.new_symbol.astype(str).str.strip().str.upper()
fallback = {r.old_symbol: r.new_symbol for _, r in sm.iterrows()}

m = pd.read_csv(a.membership)
m.columns = [str(c).strip().lower().replace(" ", "_") for c in m.columns]
m.symbol = m.symbol.astype(str).str.strip().str.upper()
m.valid_from = pd.to_datetime(m.valid_from, errors="coerce")
m.valid_to = pd.to_datetime(m.valid_to, errors="coerce").fillna(end)

acq_col = "acquisition_symbol" if "acquisition_symbol" in m.columns else "symbol"
syms = sorted(
    m.loc[(m.valid_from <= end) & (m.valid_to >= start), acq_col]
    .dropna().astype(str).str.upper().unique()
)

Path(a.out).parent.mkdir(parents=True, exist_ok=True)

print(
    f"ACQUISITION: {len(syms)} symbols, {start.date()} to {end.date()}, "
    f"chunk_days={a.chunk_days}, workers={a.workers}",
    flush=True,
)

parts = []
failures = []
completed = 0

with ThreadPoolExecutor(max_workers=a.workers) as ex:
    future_map = {
        ex.submit(fetch_symbol, sym, start, end, a.chunk_days): sym
        for sym in syms
    }

    for fut in as_completed(future_map):
        sym = future_map[fut]
        try:
            d, errs = fut.result()
            if len(d):
                parts.append(d)
            else:
                failures.extend(errs or [{
                    "symbol": sym,
                    "chunk_start": str(start.date()),
                    "chunk_end": str(end.date()),
                    "error": "no_data",
                }])

            # If an old symbol is known, retry the complete symbol history using its
            # mapped NSE symbol only when the primary acquisition returned nothing.
            if len(d) == 0 and sym in fallback and fallback[sym] != sym:
                d2, errs2 = fetch_symbol(fallback[sym], start, end, a.chunk_days)
                if len(d2):
                    d2["requested_symbol"] = sym
                    d2["source_symbol"] = fallback[sym]
                    parts.append(d2)
                    failures = [x for x in failures if x.get("symbol") != sym]
                else:
                    failures.extend(errs2)

        except Exception as e:
            failures.append({
                "symbol": sym,
                "chunk_start": str(start.date()),
                "chunk_end": str(end.date()),
                "error": f"worker:{type(e).__name__}:{str(e)[:180]}",
            })

        completed += 1
        if completed % 25 == 0 or completed == len(syms):
            rows = sum(len(x) for x in parts)
            failed_symbols = len({x["symbol"] for x in failures})
            print(
                f"processed {completed}/{len(syms)} rows={rows} "
                f"failed_symbols={failed_symbols} failed_chunks={len(failures)}",
                flush=True,
            )
        time.sleep(a.sleep)

x = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
if len(x):
    x = (
        x.dropna(subset=["date", "symbol"])
         .drop_duplicates(["date", "symbol"])
         .sort_values(["date", "symbol"])
    )

Path(a.out).parent.mkdir(parents=True, exist_ok=True)
x.to_csv(a.out, index=False)

audit = {
    "start": a.start,
    "end": a.end,
    "symbols_requested": len(syms),
    "chunk_days": a.chunk_days,
    "workers": a.workers,
    "symbols_returned": int(x.symbol.nunique()) if len(x) else 0,
    "rows": len(x),
    "failed_chunks": len(failures),
    "failed_symbols": sorted({z["symbol"] for z in failures}),
    "failure_examples": failures[:100],
}
Path(a.out).with_suffix(".audit.json").write_text(json.dumps(audit, indent=2))

print(json.dumps({
    "rows": len(x),
    "symbols": int(x.symbol.nunique()) if len(x) else 0,
    "failed_symbols": len(audit["failed_symbols"]),
    "failed_chunks": len(failures),
}, indent=2))
