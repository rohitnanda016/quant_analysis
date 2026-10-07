import argparse, json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from run_fluidq_backtest import find_col, load_membership, load_nifty500_index


FACTORS = ["ret_6m", "ret_12m_ex1m", "rs6", "trend", "ram"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", required=True)
    ap.add_argument("--membership", required=True)
    ap.add_argument("--outdir", required=True)
    args = ap.parse_args()

    out = Path(args.outdir)
    out.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(args.prices, low_memory=False)
    datec = find_col(df, ["date"])
    symc = find_col(df, ["canonical_symbol", "symbol"])
    closec = find_col(df, ["close"])
    if not all([datec, symc, closec]):
        raise ValueError("Required price columns missing")

    if symc != "symbol" and "symbol" in df.columns:
        df = df.drop(columns=["symbol"])
    df = df.rename(columns={datec: "date", symc: "symbol", closec: "close"})
    df["date"] = pd.to_datetime(df["date"])
    df["symbol"] = df["symbol"].astype(str).str.upper().str.strip()
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    df = df.sort_values(["symbol", "date"]).drop_duplicates(["symbol", "date"])

    g = df.groupby("symbol", sort=False)
    df["ret_6m"] = g["close"].pct_change(126)
    df["ret_12m_ex1m"] = g["close"].shift(21).div(g["close"].shift(252)) - 1
    df["dma200"] = g["close"].transform(lambda s: s.rolling(200, min_periods=200).mean())
    df["trend"] = df["close"] / df["dma200"] - 1
    df["vol126"] = g["close"].transform(
        lambda s: s.pct_change().rolling(126, min_periods=100).std()
    ) * np.sqrt(252)
    df["ram"] = df["ret_6m"] / df["vol126"].replace(0, np.nan)
    df["forward_21d"] = g["close"].shift(-21).div(df["close"]) - 1

    nifty = load_nifty500_index(df["date"].unique())
    df = df.merge(
        nifty[["date", "nifty500_ret_6m"]],
        on="date",
        how="left",
    )

    members = load_membership(args.membership)
    period_key = df["date"].dt.to_period("M")
    reb_dates = df.groupby(period_key)["date"].max().tolist()

    corr_rows = []
    ic_rows = []
    overlap_rows = []
    rank_identity_rows = []

    for rd in reb_dates:
        snap = df[df.date == rd].copy()
        if snap.empty:
            continue

        mm = members[members.effective_date <= rd].copy()
        if mm.empty:
            continue
        if "end_date" in mm.columns:
            mm = mm[(mm.end_date.isna()) | (mm.end_date >= rd)]
            active = mm[["symbol"]].drop_duplicates()
        else:
            latest = mm.effective_date.max()
            active = mm.loc[mm.effective_date.eq(latest), ["symbol"]].drop_duplicates()

        snap = snap.merge(active, on="symbol", how="inner")
        snap["rs6"] = snap["ret_6m"] - snap["nifty500_ret_6m"].iloc[0]

        usable = snap.dropna(subset=FACTORS)
        if len(usable) < 30:
            continue

        ranks = usable[FACTORS].rank(pct=True)
        ranks["date"] = rd
        corr = ranks[FACTORS].corr(method="spearman")
        for f1 in FACTORS:
            for f2 in FACTORS:
                if f1 < f2:
                    corr_rows.append({
                        "date": rd,
                        "factor_1": f1,
                        "factor_2": f2,
                        "spearman": float(corr.loc[f1, f2]),
                        "n": len(usable),
                    })

        for f in FACTORS:
            x = usable[[f, "forward_21d"]].dropna()
            if len(x) >= 30:
                ic_rows.append({
                    "date": rd,
                    "factor": f,
                    "ic_spearman": float(x[f].corr(x.forward_21d, method="spearman")),
                    "n": len(x),
                })

        top = {f: set(usable.nlargest(30, f).symbol) for f in FACTORS}
        for i, f1 in enumerate(FACTORS):
            for f2 in FACTORS[i + 1:]:
                inter = len(top[f1] & top[f2])
                union = len(top[f1] | top[f2])
                overlap_rows.append({
                    "date": rd,
                    "factor_1": f1,
                    "factor_2": f2,
                    "top30_overlap": inter / 30.0,
                    "jaccard": inter / union if union else np.nan,
                })

        r6 = usable["ret_6m"].rank(method="first")
        rs = usable["rs6"].rank(method="first")
        rank_identity_rows.append({
            "date": rd,
            "n": len(usable),
            "rank_mismatches": int((r6 != rs).sum()),
            "max_abs_rank_diff": int((r6 - rs).abs().max()),
        })

    corr_df = pd.DataFrame(corr_rows)
    ic_df = pd.DataFrame(ic_rows)
    overlap_df = pd.DataFrame(overlap_rows)
    identity_df = pd.DataFrame(rank_identity_rows)

    corr_df.to_csv(out / "factor_pairwise_correlations.csv", index=False)
    ic_df.to_csv(out / "factor_forward_ic.csv", index=False)
    overlap_df.to_csv(out / "factor_top30_overlap.csv", index=False)
    identity_df.to_csv(out / "six_month_vs_rs6_identity.csv", index=False)

    summary = {}
    if not corr_df.empty:
        summary["mean_pairwise_spearman"] = (
            corr_df.groupby(["factor_1", "factor_2"]).spearman.mean()
            .reset_index()
            .sort_values("spearman", ascending=False)
            .to_dict("records")
        )
        summary["median_pairwise_spearman"] = (
            corr_df.groupby(["factor_1", "factor_2"]).spearman.median()
            .reset_index()
            .sort_values("spearman", ascending=False)
            .to_dict("records")
        )

        # Average monthly correlation matrix -> eigenvalue-based effective rank.
        matrices = []
        for _, grp in corr_df.groupby("date"):
            m = np.eye(len(FACTORS))
            idx = {f: i for i, f in enumerate(FACTORS)}
            for row in grp.itertuples():
                i, j = idx[row.factor_1], idx[row.factor_2]
                m[i, j] = m[j, i] = row.spearman
            matrices.append(m)
        avg_corr = np.mean(matrices, axis=0)
        eig = np.clip(np.linalg.eigvalsh(avg_corr), 0, None)
        p = eig / eig.sum()
        effective_rank = float(np.exp(-(p[p > 0] * np.log(p[p > 0])).sum()))
        summary["average_correlation_matrix"] = {
            f: {g: float(avg_corr[i, j]) for j, g in enumerate(FACTORS)}
            for i, f in enumerate(FACTORS)
        }
        summary["correlation_eigenvalues"] = eig.tolist()
        summary["effective_factor_rank"] = effective_rank

    if not ic_df.empty:
        summary["forward_ic"] = (
            ic_df.groupby("factor").ic_spearman.agg(["mean", "median", "std", "count"])
            .reset_index()
            .to_dict("records")
        )

    if not overlap_df.empty:
        summary["top30_overlap"] = (
            overlap_df.groupby(["factor_1", "factor_2"])
            .agg(top30_overlap=("top30_overlap", "mean"), jaccard=("jaccard", "mean"))
            .reset_index()
            .sort_values("top30_overlap", ascending=False)
            .to_dict("records")
        )

    if not identity_df.empty:
        summary["six_month_rs6_identity"] = {
            "months_tested": int(len(identity_df)),
            "months_with_any_mismatch": int((identity_df.rank_mismatches > 0).sum()),
            "max_rank_mismatches": int(identity_df.rank_mismatches.max()),
            "max_abs_rank_diff": int(identity_df.max_abs_rank_diff.max()),
        }

    (out / "factor_diagnostics_summary.json").write_text(
        json.dumps(summary, indent=2, default=float)
    )

    print(json.dumps(summary, indent=2, default=float))


if __name__ == "__main__":
    main()
