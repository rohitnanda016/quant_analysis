#!/usr/bin/env python3
"""Selection-replay block bootstrap for FLUID-Q consensus vs its fixed baseline.

This is a null-centered diagnostic: in each bootstrap replicate the 2/3/4-year
Sharpe-rank consensus selection is rerun, then the selected candidate is evaluated
on the following OOS fold. It is not a full Reality Check / SPA implementation.
"""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd


def circular_block_indices(rng, n, block):
    starts = rng.integers(0, n, size=(n + block - 1) // block)
    return ((starts[:, None] + np.arange(block)[None, :]) % n).ravel()[:n]


def sharpe_columns(values):
    sd = values.std(axis=0, ddof=1)
    mean = values.mean(axis=0)
    return np.divide(mean, sd, out=np.full_like(mean, -np.inf), where=sd > 0) * np.sqrt(252.0)


def run(root, block=21, replications=5000, seed=20261010):
    root = Path(root)
    summary = json.loads((root / "walk_forward_stability_summary.json").read_text())
    consensus = summary["consensus_evaluations"]["0.003"]
    names = list(summary["fixed_candidate_benchmarks"])
    if "compressed_baseline" not in names:
        raise ValueError("compressed_baseline is missing from the candidate menu")

    series = {}
    for name in names:
        frame = pd.read_csv(root / "cost_0.0030" / name / "portfolio_daily.csv", parse_dates=["date"])
        series[name] = frame.set_index("date")["ret"].sort_index()

    baseline = series["compressed_baseline"]
    dates = baseline.index
    panel = pd.DataFrame({name: series[name].reindex(dates) for name in names}, index=dates)
    if panel.isna().any().any():
        raise ValueError("Candidate daily return streams do not align on baseline dates")
    if panel.index.has_duplicates or (panel.to_numpy() <= -1).any():
        raise ValueError("Duplicate dates or invalid returns found")

    # Each fold is mapped to positional trading-day windows. The training window
    # lengths are computed from the actual calendar windows, then applied to each
    # resampled path so model selection is rerun rather than held fixed.
    folds = []
    observed_parts = []
    for fold in consensus["folds"]:
        test_start = pd.Timestamp(fold["test_start"])
        test_end = pd.Timestamp(fold["test_end"])
        test_mask = (dates >= test_start) & (dates <= test_end)
        test_positions = np.flatnonzero(test_mask)
        if len(test_positions) == 0:
            continue
        start_pos = int(test_positions[0])
        end_pos = int(test_positions[-1]) + 1
        windows = {}
        for years in (2, 3, 4):
            train_start = pd.Timestamp(year=test_start.year - years, month=1, day=1)
            train_mask = (dates >= train_start) & (dates < test_start)
            count = int(train_mask.sum())
            if count == 0 or start_pos < count:
                raise ValueError(f"Insufficient history for {years}y training window at {test_start.date()}")
            windows[years] = count
        folds.append({"start": start_pos, "end": end_pos, "windows": windows, "actual_winner": fold["winner"]})
        chosen = series[fold["winner"]].reindex(dates[test_positions]).to_numpy()
        base = baseline.reindex(dates[test_positions]).to_numpy()
        observed_parts.append(chosen - base)

    if not folds:
        raise ValueError("No consensus OOS folds found")
    observed_excess = np.concatenate(observed_parts)
    observed_stat = float(observed_excess.mean() * 252.0)

    # Center each candidate's excess return against the fixed baseline under H0.
    # Keep same-day cross-candidate covariance and baseline dynamics intact.
    raw = panel[names].to_numpy()
    base_col = panel["compressed_baseline"].to_numpy()
    excess = raw - base_col[:, None]
    null_candidates = base_col[:, None] + (excess - excess.mean(axis=0, keepdims=True))
    null_panel = null_candidates.copy()
    base_index = names.index("compressed_baseline")
    null_panel[:, base_index] = base_col
    n = len(dates)
    if n < block:
        raise ValueError("Insufficient observations for requested block length")

    rng = np.random.default_rng(seed)
    bootstrap_stats = np.empty(replications)
    for b in range(replications):
        sampled = null_panel[circular_block_indices(rng, n, block), :]
        selected_excess = []
        for fold in folds:
            scores = []
            for years in (2, 3, 4):
                count = fold["windows"][years]
                train = sampled[fold["start"] - count:fold["start"], :]
                scores.append(sharpe_columns(train))
            score_matrix = np.vstack(scores)
            ranks = np.empty_like(score_matrix)
            for row in range(score_matrix.shape[0]):
                order = np.argsort(np.argsort(-score_matrix[row], kind="mergesort"), kind="mergesort")
                ranks[row] = order + 1
            mean_rank = ranks.mean(axis=0)
            winner_idx = int(np.argmin(mean_rank))
            test = sampled[fold["start"]:fold["end"], :]
            selected_excess.append(test[:, winner_idx] - test[:, base_index])
        bootstrap_stats[b] = np.concatenate(selected_excess).mean() * 252.0

    pvalue = float((1 + np.sum(bootstrap_stats >= observed_stat)) / (replications + 1))
    result = {
        "method": "null-centered circular moving-block bootstrap with 2/3/4-year Sharpe-rank consensus reselected inside every replicate",
        "sample_start": str(dates.min().date()),
        "sample_end": str(dates.max().date()),
        "oos_start": str(min(pd.Timestamp(f["test_start"]) for f in consensus["folds"]).date()),
        "oos_end": str(max(pd.Timestamp(f["test_end"]) for f in consensus["folds"]).date()),
        "trading_days_full_panel": int(n),
        "oos_trading_days": int(len(observed_excess)),
        "candidate_count": int(len(names)),
        "candidate_names": names,
        "selection_windows_years": [2, 3, 4],
        "selection_folds": int(len(folds)),
        "observed_adaptive_annualized_arithmetic_excess": observed_stat,
        "null_bootstrap_95pct_interval": np.quantile(bootstrap_stats, [0.025, 0.975]).tolist(),
        "selection_replay_adjusted_pvalue": pvalue,
        "replications": int(replications),
        "block_days": int(block),
        "seed": int(seed),
        "interpretation": "Diagnostic only. The p-value estimates how often a null-centered resampled history, with selection rerun, produces at least the observed adaptive OOS arithmetic excess.",
        "caveats": [
            "This is not a complete White Reality Check or Hansen SPA implementation.",
            "Bootstrap uses historical candidate return streams, not a full resimulation of prices, portfolio formation, or all researcher choices.",
            "Only seven annual OOS selection folds are available; inference is necessarily fragile.",
            "The result does not correct for omitted dividends, residual corporate-action/price-integrity issues, or other backtest execution limitations."
        ]
    }
    out = root / "selection_replay_bootstrap.json"
    out.write_text(json.dumps(result, indent=2))
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--block-days", type=int, default=21)
    parser.add_argument("--replications", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=20261010)
    args = parser.parse_args()
    run(args.outdir, args.block_days, args.replications, args.seed)
