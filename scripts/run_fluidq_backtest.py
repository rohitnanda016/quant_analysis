import argparse, json
from pathlib import Path
import numpy as np
import pandas as pd

def find_col(df, candidates):
    low={c.lower().strip():c for c in df.columns}
    for x in candidates:
        if x.lower() in low: return low[x.lower()]
    for c in df.columns:
        cl=c.lower().replace(" ","_")
        if any(x in cl for x in candidates): return c
    return None

def load_membership(path):
    m=pd.read_csv(path)
    sym=find_col(m,["symbol","security","security_symbol","ticker"])
    if not sym: raise ValueError(f"Could not identify membership symbol column: {list(m.columns)}")
    m=m.rename(columns={sym:"symbol"})
    m["symbol"]=m["symbol"].astype(str).str.upper().str.strip()
    start=find_col(m,["review_date","effective_date","start_date","date"])
    end=find_col(m,["end_date"])
    if start:
        m["effective_date"]=pd.to_datetime(m[start],errors="coerce")
    else:
        m["effective_date"]=pd.NaT
    if end: m["end_date"]=pd.to_datetime(m[end],errors="coerce")
    return m[["symbol","effective_date"]+([ "end_date"] if "end_date" in m else [])]

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--prices",required=True); ap.add_argument("--membership",required=True)
    ap.add_argument("--events",required=True); ap.add_argument("--outdir",required=True)
    a=ap.parse_args(); out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)

    df=pd.read_csv(a.prices,low_memory=False)
    datec=find_col(df,["date"]); symc=find_col(df,["canonical_symbol","symbol"])
    closec=find_col(df,["close"]); vwapc=find_col(df,["vwap"])
    turnc=find_col(df,["turnover_₹","turnover","turnover_rs"])
    if not all([datec,symc,closec]): raise ValueError("Required price columns missing")
    ren={datec:"date",symc:"symbol",closec:"close"}
    if vwapc: ren[vwapc]="vwap"
    if turnc: ren[turnc]="turnover"
    df=df.rename(columns=ren)
    df["date"]=pd.to_datetime(df["date"]); df["symbol"]=df["symbol"].astype(str).str.upper().str.strip()
    for c in ["close","vwap","turnover"]:
        if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.sort_values(["symbol","date"]).drop_duplicates(["symbol","date"])
    g=df.groupby("symbol",sort=False)
    df["ret_6m"]=g["close"].pct_change(126)
    df["ret_12m_ex1m"]=g["close"].pct_change(252).div(1+g["close"].pct_change(21))-0 # approximation, later ranked
    df["dma200"]=g["close"].transform(lambda s:s.rolling(200,min_periods=200).mean())
    df["trend"]=df["close"]/df["dma200"]-1
    df["vol126"]=g["close"].transform(lambda s:s.pct_change().rolling(126,min_periods=100).std())*np.sqrt(252)
    df["ram"]=df["ret_6m"]/df["vol126"].replace(0,np.nan)
    if "turnover" in df:
        df["adv60"]=g["turnover"].transform(lambda s:s.rolling(60,min_periods=40).mean())
    else: df["adv60"]=np.nan

    members=load_membership(a.membership)
    events=pd.read_csv(a.events); events["event_date"]=pd.to_datetime(events["event_date"],errors="coerce")
    corporate=set(events.loc[events.treatment=="corporate_event","symbol"].astype(str).str.upper())
    # Monthly rebalance dates: last observed trading day in each calendar month.
    reb_dates=df.groupby(df["date"].dt.to_period("M"))["date"].max().tolist()
    snapshots=[]; holdings=set(); nav=1.0; daily=[]
    price_dates=np.sort(df["date"].unique())
    for rd in reb_dates:
        snap=df[df.date==rd].copy()
        if snap.empty: continue
        # Point-in-time membership: latest membership review at or before rebalance.
        if members["effective_date"].notna().any():
            mm=members[members.effective_date<=rd]
            if not mm.empty:
                latest=mm.groupby("symbol")["effective_date"].max().reset_index()
                snap=snap.merge(latest,on="symbol",how="inner")
        # Cross-sectional relative strength proxy versus contemporaneous universe median.
        med6=snap["ret_6m"].median()
        snap["rs6"]=snap["ret_6m"]-med6
        cols=["ret_6m","ret_12m_ex1m","rs6","trend","ram"]
        for c in cols: snap[c+"_pct"]=snap[c].rank(pct=True)*100
        snap["score"]=(snap["ret_6m_pct"]*.20+snap["ret_12m_ex1m_pct"]*.15+
                       snap["rs6_pct"]*.20+snap["trend_pct"]*.20+snap["ram_pct"]*.15)/.90
        eligible=snap[(snap["close"]>snap["dma200"])&(snap["ret_6m"]>0)&(snap["rs6"]>0)]
        if "adv60" in snap: eligible=eligible[eligible["adv60"]>=1e8]
        eligible=eligible.sort_values(["score","ret_6m"],ascending=False)
        rank=eligible["score"].rank(method="first",ascending=False)
        eligible=eligible.assign(rank=rank)
        keep=[s for s in holdings if s in set(eligible.loc[eligible.score>=65,"symbol"]) and
              s in set(eligible.loc[eligible["rank"]<=30,"symbol"])]
        candidates=eligible[(eligible.score>=75)&(eligible["rank"]<=30)]
        chosen=[]
        for s in keep: chosen.append(s)
        for s in candidates.symbol:
            if s not in chosen and len(chosen)<15: chosen.append(s)
        if len(chosen)<15:
            for s in eligible.symbol:
                if s not in chosen and len(chosen)<15: chosen.append(s)
        chosen=chosen[:15]
        # Market regime proxy: breadth, median 6M momentum, median RS.
        breadth=float((snap["close"]>snap["dma200"]).mean())
        healthy=int(breadth>=.60)+int(float(snap["ret_6m"].median())>0)+int(float(snap["rs6"].median())>0)
        exposure={3:1.0,2:.75,1:.50,0:.25}[healthy]
        # Exclude securities with explicit demerger/scheme event on the rebalance date.
        day_events=set(events.loc[events.event_date==rd,"symbol"].astype(str).str.upper())
        chosen=[s for s in chosen if not (s in corporate and s in day_events)]
        turnover=(len(set(chosen)^set(holdings))/2)/max(len(chosen),1)
        snapshots.append({"date":rd,"n_eligible":len(eligible),"holdings":",".join(chosen),
                          "exposure":exposure,"regime_healthy":healthy,"breadth":breadth,
                          "median_6m":float(snap.ret_6m.median()),"turnover":turnover})
        holdings=set(chosen)
    sig=pd.DataFrame(snapshots)
    if sig.empty: raise ValueError("No rebalance snapshots produced")
    # Build daily equal-weight portfolio from signal holdings, using next trading day's VWAP as execution proxy.
    sig["date"]=pd.to_datetime(sig.date)
    for _,r in sig.iterrows():
        d=pd.Timestamp(r.date); pos=[x for x in str(r.holdings).split(",") if x]
        if not pos: continue
        future=price_dates[price_dates>d]
        if len(future)==0: continue
        execd=pd.Timestamp(future[0])
        px=df[(df.date==execd)&df.symbol.isin(pos)].copy()
        if px.empty: continue
        daily_ret=float(px["close"].pct_change().mean()) if False else np.nan
        # Record execution basket; daily NAV is approximated from equal-weight close-to-close returns.
        px2=df[df.symbol.isin(pos)&(df.date>=execd)].copy()
        piv=px2.pivot(index="date",columns="symbol",values="close").sort_index()
        rets=piv.pct_change().mean(axis=1).fillna(0)*float(r.exposure)
        cost=float(r.turnover)*0.003
        if len(rets): rets.iloc[0]-=cost
        for dd,rr in rets.items(): daily.append((dd,float(rr),d))
    dr=pd.DataFrame(daily,columns=["date","ret","signal_date"]).drop_duplicates("date").sort_values("date")
    if dr.empty: raise ValueError("No daily portfolio series produced")
    dr["nav"]=(1+dr["ret"]).cumprod()
    years=(dr.date.iloc[-1]-dr.date.iloc[0]).days/365.25
    cagr=float(dr.nav.iloc[-1]**(1/years)-1) if years>0 else np.nan
    peak=dr.nav.cummax(); dd=dr.nav/peak-1
    metrics={"start":str(dr.date.iloc[0].date()),"end":str(dr.date.iloc[-1].date()),
             "cagr":cagr,"max_drawdown":float(dd.min()),"final_nav":float(dr.nav.iloc[-1]),
             "rebalance_count":int(len(sig)),"avg_turnover":float(sig.turnover.mean()),
             "note":"Sector momentum/sector caps are not applied because the supplied point-in-time membership artifact contains no verified historical sector field; weights are therefore renormalized over the five available cross-sectional factors."}
    sig.to_csv(out/"rebalance_signals.csv",index=False); dr.to_csv(out/"portfolio_daily.csv",index=False)
    (out/"metrics.json").write_text(json.dumps(metrics,indent=2))
    print(json.dumps(metrics,indent=2))

if __name__=="__main__": main()
