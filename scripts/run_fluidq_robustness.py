import argparse, json, subprocess, sys, tempfile
from pathlib import Path
import pandas as pd
import numpy as np

TRI_URL="https://raw.githubusercontent.com/bebhuvan/ipo-performance-verification/main/data/inputs/indices/nifty500_tri.csv"

def stats(ret):
    ret=pd.Series(ret).dropna(); nav=(1+ret).cumprod(); years=len(ret)/252
    cagr=float(nav.iloc[-1]**(1/years)-1) if years else np.nan
    vol=float(ret.std(ddof=1)*np.sqrt(252)); sharpe=float(ret.mean()/ret.std(ddof=1)*np.sqrt(252))
    dd=nav/nav.cummax()-1
    return cagr,vol,sharpe,float(dd.min()),float(nav.iloc[-1])

def all_variants():
    variants=[]
    for n in (10,15,20):
        for tc in (0.0015,0.003,0.005): variants.append((f"monthly_top{n}_tc{tc:.2%}",n,tc,"monthly"))
    for tc in (0.0015,0.003,0.005): variants.append((f"quarterly_top15_tc{tc:.2%}",15,tc,"quarterly"))
    return variants

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--prices",required=True); ap.add_argument("--membership",required=True); ap.add_argument("--events",required=True); ap.add_argument("--outdir",required=True)
    ap.add_argument("--variant",help="Run one named variant; omit to run all variants")
    a=ap.parse_args(); out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)
    variants=all_variants()
    if a.variant:
        variants=[v for v in variants if v[0]==a.variant]
        if not variants: raise ValueError(f"Unknown variant: {a.variant}")
    tri=pd.read_csv(TRI_URL,parse_dates=["date"]); tri["tri"]=pd.to_numeric(tri["close"],errors="coerce"); tri=tri.dropna(subset=["date","tri"]).sort_values("date").drop_duplicates("date"); tri["bench_ret"]=tri["tri"].pct_change()
    rows=[]
    with tempfile.TemporaryDirectory() as td:
        for name,n,tc,freq in variants:
            vout=Path(td)/name; vout.mkdir()
            cmd=[sys.executable,"scripts/run_fluidq_backtest.py","--prices",a.prices,"--membership",a.membership,"--events",a.events,"--outdir",str(vout),"--top-n",str(n),"--transaction-cost",str(tc),"--rebalance-frequency",freq]
            subprocess.run(cmd,check=True)
            p=pd.read_csv(vout/"portfolio_daily.csv",parse_dates=["date","signal_date"]); s=pd.read_csv(vout/"rebalance_signals.csv",parse_dates=["date"])
            m=p.merge(tri[["date","bench_ret"]],on="date",how="inner")
            if len(m)<1000: raise RuntimeError(f"{name}: insufficient benchmark overlap: {len(m)}")
            cagr,vol,sharpe,dd,nav=stats(m["ret"]); sig=s[["date","exposure"]].rename(columns={"date":"signal_date"}); m=m.merge(sig,on="signal_date",how="left")
            if m.exposure.isna().any(): raise RuntimeError(f"{name}: missing exposure alignment")
            matched_cagr,_,_,_,_=stats(m["bench_ret"]*m["exposure"]); bench_cagr,_,_,_,_=stats(m["bench_ret"])
            rows.append({"variant":name,"top_n":n,"transaction_cost":tc,"rebalance_frequency":freq,"cagr":cagr,"max_drawdown":dd,"volatility":vol,"sharpe_rf0":sharpe,"final_nav":nav,"avg_turnover":float(s.turnover.mean()),"avg_exposure":float(s.exposure.mean()),"rebalance_count":int(len(s)),"nifty500_tri_cagr":bench_cagr,"regime_matched_cagr":matched_cagr,"excess_vs_nifty500":cagr-bench_cagr,"excess_vs_regime_matched":cagr-matched_cagr})
    res=pd.DataFrame(rows); res.to_csv(out/"robustness_summary.csv",index=False)
    payload={"benchmark_source":"Independent snapshot of Nifty 500 TRI sourced from Nifty Indices","benchmark_snapshot_url":TRI_URL,"benchmark_coverage":"2019-12-02 through 2026-09-25","variants_tested":len(res),"note":"Sensitivity analysis changes only portfolio size, transaction cost, and rebalance frequency. Signal definitions and eligibility rules are otherwise unchanged.","results":res.to_dict(orient="records")}
    (out/"robustness_summary.json").write_text(json.dumps(payload,indent=2)); print(json.dumps(payload,indent=2))

if __name__=="__main__": main()
