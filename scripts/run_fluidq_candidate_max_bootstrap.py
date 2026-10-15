#!/usr/bin/env python3
"""White-style max-statistic block bootstrap across the frozen candidate menu."""
import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

def run(root, block=21, replications=5000, seed=20261009):
    root=Path(root)
    summary=json.loads((root/"walk_forward_stability_summary.json").read_text())
    folds=summary["consensus_evaluations"]["0.003"]["folds"]
    names=list(summary["fixed_candidate_benchmarks"])
    series={}
    for name in names:
        df=pd.read_csv(root/"cost_0.0030"/name/"portfolio_daily.csv",parse_dates=["date"])
        series[name]=df.set_index("date")["ret"].sort_index()
    baseline=series["compressed_baseline"]
    chunks=[]
    for fold in folds:
        dates=baseline.loc[fold["test_start"]:fold["test_end"]].index
        if len(dates)==0: continue
        frame=pd.DataFrame({name:series[name].reindex(dates) for name in names},index=dates)
        frame["baseline"]=baseline.reindex(dates)
        if frame.isna().any().any(): raise ValueError("Missing candidate daily returns")
        chunks.append(frame)
    data=pd.concat(chunks).sort_index()
    if data.index.has_duplicates: raise ValueError("Duplicate dates in OOS panel")
    excess=data[names].sub(data["baseline"],axis=0).to_numpy()
    n,k=excess.shape
    if n<block: raise ValueError("Insufficient observations")
    observed=excess.mean(axis=0)*252
    # Center each candidate's daily excess series under the null; bootstrap the
    # maximum mean statistic to account for searching across the entire candidate menu.
    centered=excess-excess.mean(axis=0,keepdims=True)
    rng=np.random.default_rng(seed)
    boot_max=np.empty(replications)
    for b in range(replications):
        starts=rng.integers(0,n,size=(n+block-1)//block)
        idx=(starts[:,None]+np.arange(block)[None,:])%n
        sample=centered[idx.ravel()[:n],:]
        boot_max[b]=np.max(sample.mean(axis=0)*252)
    best=int(np.argmax(observed))
    pvalue=float((1+np.sum(boot_max>=observed[best]))/(replications+1))
    result={
      "method":"White-style max-statistic circular moving-block bootstrap, centered null",
      "sample_start":str(data.index.min().date()),"sample_end":str(data.index.max().date()),
      "trading_days":int(n),"candidate_count":int(k),"candidate_names":names,
      "block_days":block,"replications":replications,"seed":seed,
      "annualized_arithmetic_excess_by_candidate":{name:float(observed[i]) for i,name in enumerate(names)},
      "best_observed_candidate":names[best],"best_observed_annualized_excess":float(observed[best]),
      "max_statistic_adjusted_pvalue":pvalue,
      "caveats":[
        "This is a White-style diagnostic, not a complete implementation of every Reality Check refinement.",
        "It adjusts for the frozen six-candidate menu, not all researcher degrees of freedom from prior model development.",
        "Daily blocks do not eliminate dependence across yearly model-selection decisions.",
        "Returns remain subject to price-integrity, dividend, corporate-action, and backtest execution limitations."
      ]
    }
    (root/"candidate_max_statistic_bootstrap.json").write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--outdir",required=True);ap.add_argument("--block-days",type=int,default=21)
    ap.add_argument("--replications",type=int,default=5000);ap.add_argument("--seed",type=int,default=20261009)
    a=ap.parse_args();run(a.outdir,a.block_days,a.replications,a.seed)
