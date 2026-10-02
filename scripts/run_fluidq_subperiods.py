import argparse, json
from pathlib import Path
import pandas as pd, numpy as np

def stats(ret):
    ret=pd.Series(ret).dropna()
    if len(ret)<20: return {}
    nav=(1+ret).cumprod()
    years=(len(ret)/252)
    cagr=float(nav.iloc[-1]**(1/years)-1) if years else np.nan
    vol=float(ret.std(ddof=1)*np.sqrt(252))
    sharpe=float(ret.mean()/ret.std(ddof=1)*np.sqrt(252)) if ret.std(ddof=1)>0 else np.nan
    dd=nav/nav.cummax()-1
    return {"days":int(len(ret)),"cagr":cagr,"volatility":vol,"sharpe_rf0":sharpe,
            "max_drawdown":float(dd.min()),"final_nav":float(nav.iloc[-1])}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--portfolio",required=True); ap.add_argument("--signals",required=True)
    ap.add_argument("--outdir",required=True)
    a=ap.parse_args(); out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)
    p=pd.read_csv(a.portfolio,parse_dates=["date","signal_date"]).sort_values("date")
    s=pd.read_csv(a.signals,parse_dates=["date"]).sort_values("date")
    periods={
      "2014-2018":("2014-11-01","2018-12-31"),
      "2019-2022":("2019-01-01","2022-12-31"),
      "2023-2026":("2023-01-01","2026-08-31"),
      "2016-2017_bull":("2016-01-01","2017-12-31"),
      "2018_correction":("2018-01-01","2018-12-31"),
      "2020_covid_recovery":("2020-01-01","2020-12-31"),
      "2021_bull":("2021-01-01","2021-12-31"),
      "2022_correction":("2022-01-01","2022-12-31"),
      "2023-2024":("2023-01-01","2024-12-31"),
      "2025-2026":("2025-01-01","2026-08-31")
    }
    rows=[]
    for name,(start,end) in periods.items():
        m=p[(p.date>=start)&(p.date<=end)].copy()
        if m.empty: continue
        st=stats(m.ret)
        sig=s[(s.date>=start)&(s.date<=end)]
        rows.append({"period":name,"start":str(m.date.min().date()),"end":str(m.date.max().date()),
                     **st,"avg_exposure":float(sig.exposure.mean()) if not sig.empty else np.nan,
                     "avg_turnover":float(sig.turnover.mean()) if not sig.empty else np.nan,
                     "rebalance_count":int(len(sig))})
    df=pd.DataFrame(rows)
    df.to_csv(out/"subperiod_metrics.csv",index=False)
    payload={"periods":df.to_dict(orient="records"),
             "note":"Descriptive sub-period analysis of the existing baseline FLUID-Q portfolio. No parameters are changed or optimized by this analysis."}
    (out/"subperiod_metrics.json").write_text(json.dumps(payload,indent=2))
    print(json.dumps(payload,indent=2))

if __name__=="__main__": main()
