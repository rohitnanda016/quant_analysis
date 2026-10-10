#!/usr/bin/env python3
import argparse, json, subprocess, sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.run_fluidq_walk_forward import CANDIDATES, stats, prepare_nifty_cache

def run_candidate(args, name, weights, root):
    out = root / name
    if (out / "portfolio_daily.csv").exists():
        return
    cmd = [
        sys.executable, "scripts/run_fluidq_backtest.py",
        "--prices", args.prices, "--membership", args.membership, "--events", args.events,
        "--factor-weights", weights, "--outdir", str(out),
        "--top-n", str(args.top_n), "--transaction-cost", str(args.transaction_cost),
        "--rebalance-frequency", args.rebalance_frequency,
        "--nifty500-index", args.nifty500_index,
    ]
    subprocess.run(cmd, check=True)

def load_series(root):
    out = {}
    for name in CANDIDATES:
        p = pd.read_csv(root / name / "portfolio_daily.csv", parse_dates=["date"])
        out[name] = p.set_index("date")["ret"].sort_index()
    return out

def select(train_df, rule):
    if rule == "sharpe":
        cols = ["sharpe", "cagr"]
        return train_df.sort_values(cols, ascending=False, kind="mergesort").iloc[0]["candidate"]
    if rule == "cagr":
        cols = ["cagr", "sharpe"]
        return train_df.sort_values(cols, ascending=False, kind="mergesort").iloc[0]["candidate"]
    train_df = train_df.copy()
    train_df["calmar"] = train_df["cagr"] / train_df["max_drawdown"].abs().replace(0, np.nan)
    return train_df.sort_values(["calmar", "sharpe", "cagr"], ascending=False, kind="mergesort").iloc[0]["candidate"]

def evaluate(series, train_years, test_years, rule):
    all_dates = sorted(set().union(*(s.index for s in series.values())))
    first = pd.Timestamp(min(all_dates)).normalize()
    last = pd.Timestamp(max(all_dates)).normalize()
    folds, stitched = [], []
    test_start = pd.Timestamp(year=first.year + train_years, month=1, day=1)
    while test_start <= last:
        train_start = pd.Timestamp(year=test_start.year - train_years, month=1, day=1)
        test_end = min(pd.Timestamp(year=test_start.year + test_years - 1, month=12, day=31), last)
        train_df = pd.DataFrame([
            {"candidate": name, **stats(s[(s.index >= train_start) & (s.index < test_start)])}
            for name, s in series.items()
        ])
        winner = str(select(train_df, rule))
        oos = series[winner][(series[winner].index >= test_start) & (series[winner].index <= test_end)]
        stitched.append(oos)
        folds.append({
            "train_start": str(train_start.date()), "test_start": str(test_start.date()),
            "test_end": str(test_end.date()), "winner": winner,
            "oos": stats(oos),
        })
        test_start = pd.Timestamp(year=test_start.year + test_years, month=1, day=1)
    stitched = pd.concat(stitched).sort_index() if stitched else pd.Series(dtype=float)
    return {"train_years": train_years, "test_years": test_years, "selection_rule": rule,
            "folds": folds, "stitched_oos": stats(stitched)}

def evaluate_consensus(series, train_windows, test_years, rule="sharpe"):
    all_dates = sorted(set().union(*(s.index for s in series.values())))
    first = pd.Timestamp(min(all_dates)).normalize()
    last = pd.Timestamp(max(all_dates)).normalize()
    folds, stitched = [], []
    test_start = pd.Timestamp(year=first.year + max(train_windows), month=1, day=1)
    while test_start <= last:
        scores = pd.DataFrame(index=list(series.keys()))
        for years in train_windows:
            train_start = pd.Timestamp(year=test_start.year - years, month=1, day=1)
            table = pd.DataFrame([
                {"candidate": name, **stats(s[(s.index >= train_start) & (s.index < test_start)])}
                for name, s in series.items()
            ]).set_index("candidate")
            if rule == "sharpe":
                metric = table["sharpe"]
            elif rule == "cagr":
                metric = table["cagr"]
            else:
                metric = table["cagr"] / table["max_drawdown"].abs().replace(0, np.nan)
            scores[f"{years}y_rank"] = metric.rank(ascending=False, method="average")
        scores["mean_rank"] = scores.mean(axis=1)
        winner = str(scores.sort_values(["mean_rank"]).index[0])
        test_end = min(pd.Timestamp(year=test_start.year + test_years - 1, month=12, day=31), last)
        oos = series[winner][(series[winner].index >= test_start) & (series[winner].index <= test_end)]
        stitched.append(oos)
        folds.append({
            "train_windows": train_windows, "test_start": str(test_start.date()),
            "test_end": str(test_end.date()), "winner": winner,
            "mean_rank": float(scores.loc[winner, "mean_rank"]),
            "candidate_mean_ranks": scores["mean_rank"].sort_values().to_dict(),
            "oos": stats(oos),
        })
        test_start = pd.Timestamp(year=test_start.year + test_years, month=1, day=1)
    stitched = pd.concat(stitched).sort_index() if stitched else pd.Series(dtype=float)
    return {"train_windows": train_windows, "test_years": test_years,
            "selection_rule": rule, "folds": folds, "stitched_oos": stats(stitched)}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True); ap.add_argument("--membership", required=True)
    ap.add_argument("--events", required=True); ap.add_argument("--outdir", required=True)
    ap.add_argument("--top-n", type=int, default=15); ap.add_argument("--transaction-cost", type=float, default=0.003)
    ap.add_argument("--rebalance-frequency", default="monthly")
    ap.add_argument("--nifty500-index", default="results/walk_forward_stability/nifty500_index.csv")
    a = ap.parse_args()
    root = Path(a.outdir); root.mkdir(parents=True, exist_ok=True)
    cache = Path(a.nifty500_index)
    if not cache.is_absolute(): cache = Path.cwd() / cache
    cache.parent.mkdir(parents=True, exist_ok=True)
    prepare_nifty_cache(a.prices, cache)
    a.nifty500_index = str(cache)

    costs = [0.0015, 0.003, 0.005]
    series_by_cost = {}
    for cost in costs:
        croot = root / f"cost_{cost:.4f}"
        args = SimpleNamespace(**vars(a)); args.transaction_cost = cost
        croot.mkdir(parents=True, exist_ok=True)
        for name, weights in CANDIDATES.items():
            run_candidate(args, name, weights, croot)
        series_by_cost[cost] = load_series(croot)

    evaluations = []
    for cost in costs:
        for train_years in [2, 3, 4]:
            for rule in ["sharpe", "cagr", "calmar"]:
                if cost != 0.003 and (train_years != 3 or rule != "sharpe"):
                    continue
                result = evaluate(series_by_cost[cost], train_years, 1, rule)
                result["transaction_cost"] = cost
                evaluations.append(result)

    consensus = {}
    for cost in costs:
        if cost == 0.003:
            consensus[cost] = evaluate_consensus(series_by_cost[cost], [2, 3, 4], 1, "sharpe")

    fixed = {}
    base_cost = series_by_cost[0.003]
    all_dates = sorted(set().union(*(s.index for s in base_cost.values())))
    first = pd.Timestamp(min(all_dates)).normalize()
    last = pd.Timestamp(max(all_dates)).normalize()
    test_start = pd.Timestamp(year=first.year + 3, month=1, day=1)
    while test_start <= last:
        test_end = min(pd.Timestamp(year=test_start.year, month=12, day=31), last)
        for name, s in base_cost.items():
            fixed.setdefault(name, []).append(s[(s.index >= test_start) & (s.index <= test_end)])
        test_start = pd.Timestamp(year=test_start.year + 1, month=1, day=1)
    fixed_stats = {name: stats(pd.concat(parts).sort_index()) for name, parts in fixed.items()}

    summary = {
        "methodology": {
            "candidate_weights_frozen_before_evaluation": True,
            "train_windows_years": [2,3,4],
            "test_window_years": 1,
            "selection_rules": ["sharpe","cagr","calmar"],
            "transaction_costs": costs,
            "cost_sensitivity_only": "3Y/1Y Sharpe selection",
            "objective_sensitivity_only": "0.30% cost, 1Y test",
            "calmar_definition": "training CAGR / abs(training max drawdown)",
            "fixed_benchmark": "same six candidates stitched over the 3Y/1Y calendar OOS periods",
        },
        "evaluations": evaluations,
        "consensus_evaluations": consensus,
        "fixed_candidate_benchmarks": fixed_stats,
        "note": "Stability diagnostic only. No candidate or weighting is promoted without further economic and statistical validation."
    }
    (root / "walk_forward_stability_summary.json").write_text(json.dumps(summary, indent=2, default=str))
    pd.DataFrame([
        {"cost": e["transaction_cost"], "train_years": e["train_years"], "rule": e["selection_rule"],
         "oos_cagr": e["stitched_oos"]["cagr"], "oos_sharpe": e["stitched_oos"]["sharpe"],
         "oos_max_drawdown": e["stitched_oos"]["max_drawdown"], "oos_final_nav": e["stitched_oos"]["final_nav"],
         "winners": ",".join(f["winner"] for f in e["folds"])}
        for e in evaluations
    ]).to_csv(root / "walk_forward_stability.csv", index=False)
    print(json.dumps({
        "evaluations": [
            (e["transaction_cost"], e["train_years"], e["selection_rule"], e["stitched_oos"])
            for e in evaluations
        ],
        "consensus_evaluations": consensus,
        "fixed_candidate_benchmarks": fixed_stats
    }, indent=2, default=str))

if __name__ == "__main__":
    main()
