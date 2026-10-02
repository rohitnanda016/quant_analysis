import json
from pathlib import Path
import numpy as np
import pandas as pd

def main():
    p=Path("results/backtest")
    dr=pd.read_csv(p/"portfolio_daily.csv",parse_dates=["date"])
    sig=pd.read_csv(p/"rebalance_signals.csv",parse_dates=["date"])
    dr=dr.sort_values("date").drop_duplicates("date")
    r=pd.to_numeric(dr["ret"],errors="coerce").fillna(0.0)
    nav=pd.to_numeric(dr["nav"],errors="coerce")
    years=(dr.date.iloc[-1]-dr.date.iloc[0]).days/365.25
    ann_vol=float(r.std(ddof=1)*np.sqrt(252))
    sharpe=float(r.mean()/r.std(ddof=1)*np.sqrt(252)) if r.std(ddof=1)>0 else np.nan
    downside=r.where(r<0,0)
    downside_dev=float(np.sqrt((downside**2).mean())*np.sqrt(252))
    sortino=float(r.mean()*252/downside_dev) if downside_dev>0 else np.nan
    cagr=float(nav.iloc[-1]**(1/years)-1) if years>0 else np.nan
    dd=nav/nav.cummax()-1
    calmar=float(cagr/abs(dd.min())) if dd.min()<0 else np.nan
    monthly=(1+r).groupby(dr.date.dt.to_period("M")).prod()-1
    annual=(1+r).groupby(dr.date.dt.year).prod()-1
    out={
      "annualized_volatility":ann_vol,
      "sharpe_rf0":sharpe,
      "sortino_rf0":sortino,
      "calmar":calmar,
      "daily_win_rate":float((r>0).mean()),
      "monthly_win_rate":float((monthly>0).mean()),
      "positive_years":int((annual>0).sum()),
      "negative_years":int((annual<0).sum()),
      "best_year":int(annual.idxmax()),
      "best_year_return":float(annual.max()),
      "worst_year":int(annual.idxmin()),
      "worst_year_return":float(annual.min()),
      "avg_regime_exposure":float(sig["exposure"].mean()),
      "min_regime_exposure":float(sig["exposure"].min()),
      "max_regime_exposure":float(sig["exposure"].max()),
      "median_eligible":float(sig["n_eligible"].median()),
      "median_monthly_turnover":float(sig["turnover"].median()),
      "max_monthly_turnover":float(sig["turnover"].max())
    }
    (p/"validation_metrics.json").write_text(json.dumps(out,indent=2))
    (p/"annual_returns.csv").write_csv if False else None
    pd.DataFrame({"year":annual.index.astype(int),"return":annual.values}).to_csv(p/"annual_returns.csv",index=False)
    print(json.dumps(out,indent=2))
if __name__=="__main__":
    main()
