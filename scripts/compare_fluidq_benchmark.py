import argparse, json
from pathlib import Path
import pandas as pd, numpy as np

TRI_SNAPSHOT_URL="https://raw.githubusercontent.com/bebhuvan/ipo-performance-verification/main/data/inputs/indices/nifty500_tri.csv"

def fetch_tri():
    tri=pd.read_csv(TRI_SNAPSHOT_URL,parse_dates=["date"])
    required={"date","close"}
    if not required.issubset(tri.columns):
        raise ValueError(f"Nifty 500 TRI snapshot missing columns: {required-set(tri.columns)}")
    tri["value"]=pd.to_numeric(tri["close"],errors="coerce")
    tri=tri.dropna(subset=["date","value"]).sort_values("date").drop_duplicates("date")
    if tri.empty:
        raise ValueError("Nifty 500 TRI snapshot returned no usable rows")
    return tri[["date","value"]]

def stats(ret):
    ret=ret.dropna()
    nav=(1+ret).cumprod()
    years=len(ret)/252
    cagr=float(nav.iloc[-1]**(1/years)-1) if years else np.nan
    vol=float(ret.std(ddof=1)*np.sqrt(252))
    sharpe=float(ret.mean()/ret.std(ddof=1)*np.sqrt(252))
    dd=nav/nav.cummax()-1
    return {"cagr":cagr,"volatility":vol,"sharpe_rf0":sharpe,
            "max_drawdown":float(dd.min()),"final_nav":float(nav.iloc[-1])}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--portfolio",required=True)
    ap.add_argument("--signals",required=True)
    ap.add_argument("--outdir",required=True)
    a=ap.parse_args(); out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)

    p=pd.read_csv(a.portfolio,parse_dates=["date","signal_date"]).sort_values("date")
    s=pd.read_csv(a.signals,parse_dates=["date"]).sort_values("date")
    tri=fetch_tri()
    tri["ret"]=tri.value.pct_change()

    m=p[["date","ret","signal_date"]].merge(
        tri[["date","ret"]],on="date",how="inner",
        suffixes=("_fluidq","_nifty500tri")
    )
    if len(m)<1000:
        raise ValueError(f"Too few benchmark overlap rows: {len(m)}")

    base=stats(m.ret_fluidq); bench=stats(m.ret_nifty500tri)

    sig=s[["date","exposure"]].copy().rename(columns={"date":"signal_date"})
    m=m.merge(sig,on="signal_date",how="left")
    missing=int(m.exposure.isna().sum())
    if missing:
        raise ValueError(f"Missing regime exposure for {missing} portfolio rows")

    m["matched_bench_ret"]=m.ret_nifty500tri*m.exposure
    matched=stats(m.matched_bench_ret)

    active=(1+m.ret_fluidq)/(1+m.ret_nifty500tri)-1
    active_stats=stats(active)

    outd={
        "benchmark_source":"Independent snapshot of Nifty 500 TRI sourced from Nifty Indices",
        "benchmark_snapshot_url":TRI_SNAPSHOT_URL,
        "benchmark_snapshot_coverage":"2019-12-02 through 2026-09-25",
        "comparison_window_note":"Because the auditable daily TRI snapshot begins in late 2019, benchmark attribution is calculated only over the common portfolio/benchmark window from 2020 onward; the standalone FLUID-Q backtest remains 2014-11-03 through 2026-08-31.",
        "overlap_start":str(m.date.min().date()),
        "overlap_end":str(m.date.max().date()),
        "overlap_days":int(len(m)),
        "fluidq":base,
        "nifty500_tri":bench,
        "regime_matched_nifty500":matched,
        "daily_active_return_stats":active_stats,
        "fluidq_minus_full_benchmark_cagr":base["cagr"]-bench["cagr"],
        "fluidq_minus_regime_matched_cagr":base["cagr"]-matched["cagr"]
    }
    (out/"benchmark_comparison.json").write_text(json.dumps(outd,indent=2))
    m.to_csv(out/"benchmark_daily_comparison.csv",index=False)
    print(json.dumps(outd,indent=2))

if __name__=="__main__":
    main()
