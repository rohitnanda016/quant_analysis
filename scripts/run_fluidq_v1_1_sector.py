import argparse, json, io, time
from pathlib import Path
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

NSE_INDEX_URL = "https://archives.nseindia.com/content/indices/ind_close_all_{date}.csv"

SECTOR_INDEX_NAMES = {
    "Private Bank": "NIFTY PRIVATE BANK",
    "PSU Bank": "NIFTY PSU BANK",
    "Bank": "NIFTY BANK",
    "IT": "NIFTY IT",
    "FMCG": "NIFTY FMCG",
    "Pharma": "NIFTY PHARMA",
    "Auto": "NIFTY AUTO",
    "Metal": "NIFTY METAL",
    "Realty": "NIFTY REALTY",
    "Healthcare": "NIFTY HEALTHCARE",
    "Consumer Durables": "NIFTY CONSR DURBL",
    "Oil & Gas": "NIFTY OIL AND GAS",
    "Energy": "NIFTY ENERGY",
    "Media": "NIFTY MEDIA",
    "Financial Services": "NIFTY FIN SERVICE",
}


def find_col(df, candidates):
    low = {c.lower().strip(): c for c in df.columns}
    for x in candidates:
        if x.lower() in low:
            return low[x.lower()]
    for c in df.columns:
        cl = c.lower().replace(" ", "_")
        if any(x in cl for x in candidates):
            return c
    return None


def load_membership(path):
    m = pd.read_csv(path)
    sym = find_col(m, ["symbol", "security", "security_symbol", "ticker"])
    # The project PIT membership uses half-open valid_from/valid_to intervals.
    # Accept that canonical schema directly, while retaining compatibility with
    # the older effective_date/end_date naming used by early experiment files.
    start = find_col(m, ["valid_from", "review_date", "effective_date", "start_date", "date"])
    end = find_col(m, ["valid_to", "end_date"])
    if not sym or not start:
        raise ValueError("PIT membership must contain symbol and a start/valid_from date")
    m = m.rename(columns={sym: "symbol", start: "effective_date"})
    if end:
        m = m.rename(columns={end: "end_date"})
    else:
        m["end_date"] = pd.NaT
    m["symbol"] = m["symbol"].astype(str).str.upper().str.strip()
    m["effective_date"] = pd.to_datetime(m["effective_date"], errors="coerce")
    m["end_date"] = pd.to_datetime(m["end_date"], errors="coerce")
    return m[["symbol", "effective_date", "end_date"]].dropna(subset=["symbol", "effective_date"])


def load_sector_membership(path):
    s = pd.read_csv(path, parse_dates=["valid_from", "valid_to"])
    required = {"symbol", "sector", "sector_index", "valid_from", "valid_to"}
    if not required.issubset(s.columns):
        raise ValueError(f"Sector membership missing columns: {sorted(required - set(s.columns))}")
    s["symbol"] = s["symbol"].astype(str).str.upper().str.strip()
    s["sector"] = s["sector"].astype(str).str.strip()
    return s


def fetch_day(dt):
    url = NSE_INDEX_URL.format(date=dt.strftime("%d%m%Y"))
    wanted = {"NIFTY 500", *SECTOR_INDEX_NAMES.values()}
    for attempt in range(4):
        try:
            req = Request(url, headers={"User-Agent": "Mozilla/5.0", "Accept": "text/csv,*/*"})
            with urlopen(req, timeout=20) as response:
                raw = response.read()
            if len(raw) < 5000:
                raise ValueError("short NSE response")
            x = pd.read_csv(io.BytesIO(raw))
            namec = find_col(x, ["index_name"])
            datec = find_col(x, ["index_date"])
            closec = find_col(x, ["closing", "close"])
            if not all([namec, datec, closec]):
                raise ValueError("unexpected NSE index columns")
            x[namec] = x[namec].astype(str).str.strip().str.upper()
            x = x[x[namec].isin(wanted)].copy()
            out = pd.DataFrame({
                "date": pd.to_datetime(x[datec], dayfirst=True, errors="coerce"),
                "index_name": x[namec],
                "close": pd.to_numeric(x[closec], errors="coerce"),
            }).dropna()
            out = out[out["date"].eq(pd.Timestamp(dt))]
            return out.to_dict("records")
        except Exception:
            if attempt == 3:
                return []
            time.sleep(1.5 * (attempt + 1))
    return []


def load_index_history(required_dates):
    required = pd.DatetimeIndex(sorted(pd.to_datetime(required_dates).unique()))
    rows = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_day, pd.Timestamp(d)): d for d in required}
        for fut in as_completed(futures):
            rows.extend(fut.result())
    idx = pd.DataFrame(rows)
    if idx.empty:
        raise ValueError("No NSE index observations retrieved")
    idx["date"] = pd.to_datetime(idx["date"])
    idx["index_name"] = idx["index_name"].astype(str).str.upper().str.strip()
    idx["close"] = pd.to_numeric(idx["close"], errors="coerce")
    idx = idx.dropna(subset=["date", "close"]).sort_values(["index_name", "date"]).drop_duplicates(["index_name", "date"])
    pivot = idx.pivot(index="date", columns="index_name", values="close").sort_index()
    if "NIFTY 500" not in pivot.columns:
        raise ValueError("Nifty 500 missing from NSE daily snapshots")
    coverage = float(pivot.index.isin(required).mean())
    if len(pivot) < 500 or coverage < 0.95:
        raise ValueError(f"Insufficient Nifty 500 index history: {len(pivot)} rows, coverage={coverage:.1%}")
    out = pd.DataFrame(index=pivot.index)
    out["nifty500_close"] = pivot["NIFTY 500"]
    out["nifty500_ret_6m"] = pivot["NIFTY 500"].pct_change(126)
    out["nifty500_dma200"] = pivot["NIFTY 500"].rolling(200, min_periods=200).mean()
    for sector, broadcast in SECTOR_INDEX_NAMES.items():
        if broadcast in pivot.columns:
            out[f"sector_ret_6m::{sector}"] = pivot[broadcast].pct_change(126)
    out.index.name = "date"
    return out.reset_index()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--membership", required=True)
    ap.add_argument("--sector-membership", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--top-n", type=int, default=15)
    ap.add_argument("--transaction-cost", type=float, default=0.003)
    ap.add_argument("--rebalance-frequency", choices=["monthly", "quarterly"], default="monthly")
    ap.add_argument("--sector-start-date", default="2017-01-01")
    a = ap.parse_args()
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(a.prices, low_memory=False)
    datec = find_col(df, ["date"])
    symc = find_col(df, ["symbol", "canonical_symbol"])
    closec = find_col(df, ["close"])
    turnc = find_col(df, ["turnover_₹", "turnover", "turnover_rs"])
    if not all([datec, symc, closec]):
        raise ValueError("Required price columns missing")
    # Avoid duplicate column labels when the adjusted price file contains both
    # canonical_symbol and its original symbol. Select the canonical identity first,
    # then rebuild a clean analysis frame.
    keep = [datec, symc, closec]
    if turnc:
        keep.append(turnc)
    df = df.loc[:, keep].copy()
    ren = {datec: "date", symc: "symbol", closec: "close"}
    if turnc:
        ren[turnc] = "turnover"
    df = df.rename(columns=ren)
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    for c in ["close", "turnover"]:
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"])

    g = df.groupby("symbol", sort=False)
    df["ret_6m"] = g["close"].pct_change(126)
    df["ret_12m_ex1m"] = g["close"].shift(21).div(g["close"].shift(252)) - 1
    df["dma200"] = g["close"].transform(lambda x: x.rolling(200, min_periods=200).mean())
    df["trend"] = df["close"] / df["dma200"] - 1
    df["vol126"] = g["close"].transform(lambda x: x.pct_change().rolling(126, min_periods=100).std()) * np.sqrt(252)
    df["ram"] = df["ret_6m"] / df["vol126"].replace(0, np.nan)
    df["adv60"] = g["turnover"].transform(lambda x: x.rolling(60, min_periods=40).mean()) if "turnover" in df else np.nan

    index_data = load_index_history(df["date"].unique())
    df = df.merge(index_data, on="date", how="left")

    members = load_membership(a.membership)
    sectors = load_sector_membership(a.sector_membership)
    events = pd.read_csv(a.events)
    events["event_date"] = pd.to_datetime(events["event_date"], errors="coerce")
    corporate = set(events.loc[events.treatment.eq("corporate_event"), "symbol"].astype(str).str.upper())

    period_key = df["date"].dt.to_period("M") if a.rebalance_frequency == "monthly" else df["date"].dt.to_period("Q")
    reb_dates = df.groupby(period_key)["date"].max().tolist()
    sector_start = pd.Timestamp(a.sector_start_date)
    reb_dates = [d for d in reb_dates if pd.Timestamp(d) >= sector_start]

    snapshots = []
    holdings = set()
    price_dates = np.sort(df["date"].unique())

    for rd in reb_dates:
        snap = df[df.date.eq(rd)].copy()
        mm = members[(members.effective_date <= rd) & (members.end_date.isna() | (members.end_date >= rd))]
        active = mm[["symbol"]].drop_duplicates()
        snap = snap.merge(active, on="symbol", how="inner")

        sm = sectors[(sectors.valid_from <= rd) & (sectors.valid_to.isna() | (sectors.valid_to > rd))]
        sm = sm[["symbol", "sector", "sector_index"]].drop_duplicates("symbol")
        snap = snap.merge(sm, on="symbol", how="left")

        nifty6 = float(snap["nifty500_ret_6m"].iloc[0])
        nifty_dma = float(snap["nifty500_dma200"].iloc[0])
        snap["rs6"] = snap["ret_6m"] - nifty6
        snap["sector_momentum"] = np.nan
        for sector in SECTOR_INDEX_NAMES:
            col = f"sector_ret_6m::{sector}"
            if col in snap.columns:
                snap.loc[snap["sector"].eq(sector), "sector_momentum"] = float(snap[col].iloc[0])
        snap["sector_momentum_pct"] = snap["sector_momentum"].rank(pct=True) * 100
        for c in ["ret_6m", "ret_12m_ex1m", "rs6", "trend", "ram"]:
            snap[c + "_pct"] = snap[c].rank(pct=True) * 100

        snap["sector_momentum_pct"] = snap["sector_momentum_pct"].fillna(50.0)
        snap["score"] = (
            snap["ret_6m_pct"] * .20 +
            snap["ret_12m_ex1m_pct"] * .15 +
            snap["rs6_pct"] * .20 +
            snap["trend_pct"] * .20 +
            snap["ram_pct"] * .15 +
            snap["sector_momentum_pct"] * .10
        )

        eligible = snap[
            (snap["close"] > snap["dma200"]) &
            (snap["ret_6m"] > 0) &
            (snap["rs6"] > 0)
        ].copy()
        eligible = eligible[eligible["adv60"] >= 1e8]
        eligible = eligible.sort_values(["score", "ret_6m"], ascending=False)
        eligible["rank"] = eligible["score"].rank(method="first", ascending=False)

        eligible_set = set(eligible.symbol)
        score65 = set(eligible.loc[eligible.score >= 65, "symbol"])
        rank30 = set(eligible.loc[eligible["rank"] <= 30, "symbol"])
        keep = [s for s in holdings if s in eligible_set and s in score65 and s in rank30]
        candidates = eligible[(eligible.score >= 75) & (eligible["rank"] <= 30)]

        chosen = []
        sector_counts = {}
        max_per_sector = max(1, min(3, int(np.floor(a.top_n * .25))))

        def can_add(sym):
            row = snap.loc[snap.symbol.eq(sym), "sector"]
            if row.empty or pd.isna(row.iloc[0]):
                return True
            return sector_counts.get(row.iloc[0], 0) < max_per_sector

        def add(sym):
            chosen.append(sym)
            row = snap.loc[snap.symbol.eq(sym), "sector"]
            if not row.empty and pd.notna(row.iloc[0]):
                sec = row.iloc[0]
                sector_counts[sec] = sector_counts.get(sec, 0) + 1

        for s in keep:
            if len(chosen) < a.top_n and can_add(s):
                add(s)
        for s in candidates.symbol:
            if s not in chosen and len(chosen) < a.top_n and can_add(s):
                add(s)

        breadth = float((snap["close"] > snap["dma200"]).mean())
        healthy = int(breadth >= .60) + int(nifty6 > 0) + int(nifty_dma > 0 and float(snap["nifty500_close"].iloc[0]) > nifty_dma)
        exposure = {3: 1.0, 2: .75, 1: .50, 0: .25}[healthy]

        day_events = set(events.loc[events.event_date.eq(rd), "symbol"].astype(str).str.upper())
        chosen = [s for s in chosen if not (s in corporate and s in day_events)]
        turnover = (len(set(chosen) ^ set(holdings)) / 2) / max(len(chosen), 1) if chosen else (1.0 if holdings else 0.0)

        classified = snap["sector"].notna()
        chosen_rows = snap[snap["symbol"].isin(chosen)].copy()
        chosen_classified = chosen_rows["sector"].notna()
        chosen_sector_counts = chosen_rows.loc[chosen_classified, "sector"].value_counts().to_dict()
        max_classified_sector_weight = (
            max(chosen_sector_counts.values(), default=0) / len(chosen)
            if chosen else 0.0
        )
        snapshots.append({
            "date": rd,
            "n_eligible": len(eligible),
            "n_sector_classified": int(classified.sum()),
            "sector_coverage": float(classified.mean()) if len(snap) else 0.0,
            "n_holdings": len(chosen),
            "n_holdings_sector_classified": int(chosen_classified.sum()),
            "holdings_sector_coverage": float(chosen_classified.mean()) if chosen else 0.0,
            "max_classified_sector_weight": float(max_classified_sector_weight),
            "holdings": ",".join(chosen),
            "exposure": exposure,
            "regime_healthy": healthy,
            "breadth": breadth,
            "nifty500_ret_6m": nifty6,
            "nifty500_above_dma200": bool(nifty_dma > 0 and float(snap["nifty500_close"].iloc[0]) > nifty_dma),
            "turnover": turnover,
            "sector_counts": json.dumps(sector_counts, sort_keys=True),
            "chosen_sector_counts": json.dumps(chosen_sector_counts, sort_keys=True),
        })
        holdings = set(chosen)

    sig = pd.DataFrame(snapshots)
    if sig.empty:
        raise ValueError("No V1.1 rebalance snapshots produced")

    sig["date"] = pd.to_datetime(sig.date)
    daily = []
    for i, r in sig.iterrows():
        signal_date = pd.Timestamp(r.date)
        next_signal = pd.Timestamp(sig.iloc[i + 1].date) if i + 1 < len(sig) else pd.Timestamp(price_dates[-1])
        pos = [x for x in str(r.holdings).split(",") if x]
        future = price_dates[price_dates > signal_date]
        if not pos or len(future) == 0:
            continue
        execd = pd.Timestamp(future[0])
        px = df[df.symbol.isin(pos) & (df.date >= execd) & (df.date <= next_signal)]
        piv = px.pivot(index="date", columns="symbol", values="close").sort_index().reindex(columns=pos)
        if set(pos) - set(piv.columns):
            raise ValueError(f"Missing selected symbols in execution window {signal_date.date()}")
        rets = piv.pct_change(fill_method=None).mean(axis=1, skipna=False).fillna(0) * float(r.exposure)
        cost = float(r.turnover) * a.transaction_cost
        if len(rets):
            rets.iloc[0] -= cost
        for dd, rr in rets.items():
            daily.append((dd, float(rr), signal_date))

    dr = pd.DataFrame(daily, columns=["date", "ret", "signal_date"]).sort_values(["date", "signal_date"])
    dr = dr.groupby("date", as_index=False).agg({"ret": "first", "signal_date": "first"}).sort_values("date")
    if dr.empty:
        raise ValueError("No daily portfolio series produced")

    dr["nav"] = (1 + dr["ret"]).cumprod()
    years = (dr.date.iloc[-1] - dr.date.iloc[0]).days / 365.25
    cagr = float(dr.nav.iloc[-1] ** (1 / years) - 1) if years > 0 else np.nan
    peak = dr.nav.cummax()
    dd = dr.nav / peak - 1
    ret_std = float(dr.ret.std(ddof=1))
    vol = ret_std * np.sqrt(252)
    sharpe = float(dr.ret.mean() / ret_std * np.sqrt(252)) if ret_std else np.nan
    downside = dr.loc[dr.ret < 0, "ret"].std(ddof=1)
    sortino = float(dr.ret.mean() / downside * np.sqrt(252)) if pd.notna(downside) and downside else np.nan

    metrics = {
        "start": str(dr.date.iloc[0].date()),
        "end": str(dr.date.iloc[-1].date()),
        "cagr": cagr,
        "max_drawdown": float(dd.min()),
        "final_nav": float(dr.nav.iloc[-1]),
        "volatility": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "rebalance_count": int(len(sig)),
        "avg_turnover": float(sig.turnover.mean()),
        "avg_sector_coverage": float(sig.sector_coverage.mean()),
        "top_n": a.top_n,
        "transaction_cost": a.transaction_cost,
        "rebalance_frequency": a.rebalance_frequency,
        "sector_constrained": True,
        "sector_max_holdings": max_per_sector,
        "sector_max_weight": .25,
        "sector_momentum_weight": .10,
        "sector_start_date": a.sector_start_date,
        "relative_strength_definition": "stock 6M return minus Nifty 500 6M price return",
        "sector_momentum_definition": "corresponding NSE sector-index 6M price return",
        "sector_membership_definition": "PIT intersection of upstream NSE sector-index intervals with project Nifty 500 intervals; half-open [valid_from, valid_to)",
        "sector_membership_source": "aditya-jha/nse-historical-membership",
        "sector_membership_source_commit": "0e9f58c4d457faf0e7ad3db4f4c1449e697e23e0",
        "note": "V1.1 is a separate experiment. It starts in 2017 because the upstream sector history documents materially stronger coverage from 2017 onward. Unclassified stocks receive neutral sector-momentum rank and are exempt from sector caps.",
    }

    sig.to_csv(out / "rebalance_signals.csv", index=False)
    dr.to_csv(out / "portfolio_daily.csv", index=False)
    (out / "metrics.json").write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
