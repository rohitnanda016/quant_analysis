#!/usr/bin/env python3
import argparse, json, subprocess, sys
from pathlib import Path
import numpy as np
import pandas as pd

CANDIDATES = {
    "compressed_baseline": "0.40,0.15,0,0.20,0.15",
    "equal_4factor": "0.25,0.25,0,0.25,0.25",
    "momentum_heavy": "0.50,0.15,0,0.20,0.15",
    "long_momentum_heavy": "0.30,0.30,0,0.20,0.20",
    "trend_heavy": "0.30,0.15,0,0.35,0.20",
    "ram_heavy": "0.30,0.15,0,0.20,0.35",
}

def stats(x):
    x = pd.Series(x).dropna()
    if x.empty:
        return {"cagr": np.nan, "sharpe": np.nan, "max_drawdown": np.nan, "final_nav": np.nan}
    nav = (1 + x).cumprod()
    years = max((len(x) / 252.0), 1e-9)
    cagr = float(nav.iloc[-1] ** (1 / years) - 1)
    vol = float(x.std(ddof=1) * np.sqrt(252)) if len(x) > 1 else np.nan
    sharpe = float(x.mean() / x.std(ddof=1) * np.sqrt(252)) if len(x) > 1 and x.std(ddof=1) > 0 else np.nan
    dd = nav / nav.cummax() - 1
    return {"cagr": cagr, "sharpe": sharpe, "max_drawdown": float(dd.min()), "final_nav": float(nav.iloc[-1])}

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
    ]
    subprocess.run(cmd, check=True)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--membership", required=True)
    ap.add_argument("--events", required=True)
    ap.add_argument("--outdir", required=True)
    ap.add_argument("--top-n", type=int, default=15)
    ap.add_argument("--transaction-cost", type=float, default=0.003)
    ap.add_argument("--rebalance-frequency", choices=["monthly", "quarterly"], default="monthly")
    ap.add_argument("--train-years", type=int, default=3)
    ap.add_argument("--test-years", type=int, default=1)
    a = ap.parse_args()
    root = Path(a.outdir); root.mkdir(parents=True, exist_ok=True)
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=len(CANDIDATES)) as ex:
        futures = [ex.submit(run_candidate, a, name, weights, root) for name, weights in CANDIDATES.items()]
        for fut in as_completed(futures):
            fut.result()

    series = {}
    for name in CANDIDATES:
        p = pd.read_csv(root / name / "portfolio_daily.csv", parse_dates=["date"])
        series[name] = p.set_index("date")["ret"].sort_index()

    all_dates = sorted(set().union(*(s.index for s in series.values())))
    first = pd.Timestamp(min(all_dates)).normalize()
    last = pd.Timestamp(max(all_dates)).normalize()
    folds = []
    test_start = pd.Timestamp(year=first.year + a.train_years, month=1, day=1)
    while test_start <= last:
        train_start = pd.Timestamp(year=test_start.year - a.train_years, month=1, day=1)
        test_end = pd.Timestamp(year=test_start.year + a.test_years - 1, month=12, day=31)
        if test_end > last: test_end = last
        train_rows = []
        for name, s in series.items():
            x = s[(s.index >= train_start) & (s.index < test_start)]
            st = stats(x)
            train_rows.append((name, st))
        train_df = pd.DataFrame([{"candidate": n, **st} for n, st in train_rows])
        # Pre-specified selection rule: highest training Sharpe; CAGR is the deterministic tie-break.
        train_df = train_df.sort_values(["sharpe", "cagr"], ascending=False, kind="mergesort")
        winner = str(train_df.iloc[0]["candidate"])
        oos = series[winner][(series[winner].index >= test_start) & (series[winner].index <= test_end)]
        oos_st = stats(oos)
        folds.append({
            "test_start": str(test_start.date()),
            "test_end": str(test_end.date()),
            "train_start": str(train_start.date()),
            "winner": winner,
            "winner_weights": CANDIDATES[winner],
            "oos": oos_st,
            "training_rank": train_df.to_dict(orient="records"),
        })
        test_start = pd.Timestamp(year=test_start.year + a.test_years, month=1, day=1)

    stitched = []
    for f in folds:
        winner = f["winner"]
        s = series[winner]
        stitched.append(s[(s.index >= pd.Timestamp(f["test_start"])) & (s.index <= pd.Timestamp(f["test_end"]))])
    stitched = pd.concat(stitched).sort_index() if stitched else pd.Series(dtype=float)
    overall = stats(stitched)

    out = {
        "methodology": {
            "candidate_count": len(CANDIDATES),
            "candidates": CANDIDATES,
            "train_years": a.train_years,
            "test_years": a.test_years,
            "selection_rule": "highest training-period daily Sharpe (risk-free 0), CAGR deterministic tie-break",
            "oos_only_evaluation": True,
            "candidate_weights_frozen_before_walk_forward": True,
        },
        "folds": folds,
        "stitched_oos": overall,
        "note": "This is a walk-forward model-selection diagnostic. Candidate weights are fixed ex ante; each test period is evaluated only after selecting on preceding training data. It does not constitute evidence that the selected adaptive strategy is superior without further economic and statistical validation."
    }
    (root / "walk_forward_summary.json").write_text(json.dumps(out, indent=2, default=str))
    pd.DataFrame([{
        "test_start": f["test_start"], "test_end": f["test_end"], "winner": f["winner"],
        "weights": f["winner_weights"], "oos_cagr": f["oos"]["cagr"],
        "oos_sharpe": f["oos"]["sharpe"], "oos_max_drawdown": f["oos"]["max_drawdown"],
        "oos_final_nav": f["oos"]["final_nav"],
    } for f in folds]).to_csv(root / "walk_forward_folds.csv", index=False)
    print(json.dumps({"stitched_oos": overall, "fold_winners": [(f["test_start"], f["winner"]) for f in folds]}, indent=2))

if __name__ == "__main__":
    main()
