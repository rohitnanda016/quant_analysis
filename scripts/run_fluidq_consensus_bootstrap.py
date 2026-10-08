#!/usr/bin/env python3
"""Paired moving-block bootstrap of consensus vs fixed baseline, diagnostic only."""
import argparse
import json
from pathlib import Path
import numpy as np
import pandas as pd

def compare(root, block=21, replications=5000, seed=20261008):
    root = Path(root)
    summary = json.loads((root / "walk_forward_stability_summary.json").read_text())
    consensus = summary["consensus_evaluations"]["0.003"]
    series = {}
    for name in summary["fixed_candidate_benchmarks"]:
        df = pd.read_csv(root / "cost_0.0030" / name / "portfolio_daily.csv", parse_dates=["date"])
        series[name] = df.set_index("date")["ret"].sort_index()
    baseline = series["compressed_baseline"]
    parts = []
    for fold in consensus["folds"]:
        dates = baseline.loc[fold["test_start"]:fold["test_end"]].index
        adaptive = series[fold["winner"]].reindex(dates)
        if adaptive.isna().any():
            raise ValueError("Missing candidate returns in OOS fold")
        parts.append(pd.DataFrame({"adaptive": adaptive, "baseline": baseline.reindex(dates),
                                   "winner": fold["winner"]}, index=dates))
    paired = pd.concat(parts).sort_index()
    if paired.isna().any().any() or paired.index.has_duplicates:
        raise ValueError("Invalid paired daily return series")
    paired.index.name = "date"
    paired.to_csv(root / "consensus_vs_fixed_daily.csv")
    arr = paired[["adaptive", "baseline"]].to_numpy()
    n = len(arr)
    if n < block or np.any(arr <= -1):
        raise ValueError("Insufficient or invalid daily return observations")
    rng = np.random.default_rng(seed)
    # Circular moving blocks preserve short-run serial dependence and same-day covariance.
    excess = np.empty(replications)
    cagr_diff = np.empty(replications)
    for i in range(replications):
        starts = rng.integers(0, n, size=(n + block - 1) // block)
        indices = (starts[:, None] + np.arange(block)[None, :]) % n
        sample = arr[indices.ravel()[:n]]
        excess[i] = np.mean(sample[:, 0] - sample[:, 1]) * 252
        annual = np.exp(np.log1p(sample).mean(axis=0) * 252) - 1
        cagr_diff[i] = annual[0] - annual[1]
    observed_annual_excess = float((arr[:, 0] - arr[:, 1]).mean() * 252)
    observed_cagr = np.exp(np.log1p(arr).mean(axis=0) * 252) - 1
    result = {
        "method": "paired circular moving-block bootstrap; descriptive uncertainty only",
        "sample_start": str(paired.index.min().date()),
        "sample_end": str(paired.index.max().date()),
        "trading_days": n, "block_days": block, "replications": replications, "seed": seed,
        "observed_annualized_arithmetic_excess": observed_annual_excess,
        "observed_annualized_geometric_return_adaptive": float(observed_cagr[0]),
        "observed_annualized_geometric_return_baseline": float(observed_cagr[1]),
        "observed_annualized_geometric_return_difference": float(observed_cagr[0] - observed_cagr[1]),
        "bootstrap_annualized_excess_95pct_interval": np.quantile(excess, [.025, .975]).tolist(),
        "bootstrap_geometric_return_difference_95pct_interval": np.quantile(cagr_diff, [.025, .975]).tolist(),
        "bootstrap_fraction_excess_le_zero": float(np.mean(excess <= 0)),
        "caveats": [
            "Candidate menu and consensus method were developed after examining historical data.",
            "Bootstrap interval is not a multiple-testing-adjusted confidence interval or a valid prospective p-value.",
            "Only seven annual selection folds; daily resampling does not create independent selection decisions.",
            "Backtest assumptions, price integrity, and missing dividends remain limitations."
        ]
    }
    (root / "consensus_bootstrap_diagnostic.json").write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--block-days", type=int, default=21)
    ap.add_argument("--replications", type=int, default=5000)
    ap.add_argument("--seed", type=int, default=20261008)
    args = ap.parse_args()
    compare(args.outdir, args.block_days, args.replications, args.seed)
