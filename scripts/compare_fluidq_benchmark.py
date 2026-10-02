import argparse, json
from pathlib import Path
import requests, pandas as pd, numpy as np

def fetch_tri(start,end):
    payload={"cinfo":f"{{'name':'NIFTY 500','startDate':'{start}','endDate':'{end}','indexName':'NIFTY 500'}}"}
    r=requests.post(
      "https://www.niftyindices.com/Backpage.aspx/getTotalReturnIndexString",
      headers={"Content-Type":"application/json; charset=UTF-8","X-Requested-With":"XMLHttpRequest",
               "Referer":"https://www.niftyindices.com/reports/historical-data",
               "User-Agent":"Mozilla/5.0"},
      json=payload,timeout=60)
    r.raise_for_status()
    rows=json.loads(r.json()["d"])
    return pd.DataFrame(rows)

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
    start=p.date.min().strftime("%d-%b-%Y"); end=p.date.max().strftime("%d-%b-%Y")
    tri=fetch_tri(start,end)
    if tri.empty: raise ValueError("Nifty 500 TRI returned no rows")
    tri.columns=[str(x).strip().lower().replace(" ","_") for x in tri.columns]
    date_col=next(c for c in tri.columns if "date" in c)
    val_col=next(c for c in tri.columns if c in ("index_value","close","value","index_close") or ("index" in c and "value" in c))
    tri["date"]=pd.to_datetime(tri[date_col],dayfirst=True,errors="coerce")
    tri["value"]=pd.to_numeric(tri[val_col],errors="coerce")
    tri=tri.dropna(subset=["date","value"]).sort_values("date").drop_duplicates("date")
    tri["ret"]=tri.value.pct_change()

    m=p[["date","ret","signal_date"]].merge(tri[["date","ret"]],on="date",how="inner",suffixes=("_fluidq","_nifty500tri"))
    if len(m)<1000: raise ValueError(f"Too few benchmark overlap rows: {len(m)}")
    base=stats(m.ret_fluidq); bench=stats(m.ret_nifty500tri)

    sig=s[["date","exposure"]].copy().rename(columns={"date":"signal_date"})
    m=m.merge(sig,on="signal_date",how="left")
    missing=int(m.exposure.isna().sum())
    if missing:
        raise ValueError(f"Missing regime exposure for {missing} portfolio rows")

    # Apply the exact regime exposure associated with the signal that generated each execution-day return.
    m["matched_bench_ret"]=m.ret_nifty500tri*m.exposure
    matched=stats(m.matched_bench_ret)

    # A daily active-return series is informative, but the primary comparison is the
    # full and regime-matched benchmark CAGR calculated above.
    active=(1+m.ret_fluidq)/(1+m.ret_nifty500tri)-1
    active_stats=stats(active)

    outd={"overlap_start":str(m.date.min().date()),"overlap_end":str(m.date.max().date()),
          "overlap_days":int(len(m)),"fluidq":base,"nifty500_tri":bench,
          "regime_matched_nifty500":matched,
          "daily_active_return_stats":active_stats,
          "fluidq_minus_full_benchmark_cagr":base["cagr"]-bench["cagr"],
          "fluidq_minus_regime_matched_cagr":base["cagr"]-matched["cagr"]}
    (out/"benchmark_comparison.json").write_text(json.dumps(outd,indent=2))
    m.to_csv(out/"benchmark_daily_comparison.csv",index=False)
    print(json.dumps(outd,indent=2))

if __name__=="__main__": main()
