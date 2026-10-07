import argparse, json, io, time
from pathlib import Path
from urllib.request import Request, urlopen
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd

NSE_INDEX_URL = "https://archives.nseindia.com/content/indices/ind_close_all_{date}.csv"


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
    m["effective_date"]=pd.to_datetime(m[start],errors="coerce") if start else pd.NaT
    if end: m["end_date"]=pd.to_datetime(m[end],errors="coerce")
    return m[["symbol","effective_date"] + (["end_date"] if "end_date" in m.columns else [])]


def _fetch_nifty_day(dt):
    datestr=dt.strftime("%d%m%Y")
    url=NSE_INDEX_URL.format(date=datestr)
    for attempt in range(4):
        try:
            req=Request(url,headers={"User-Agent":"Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/140 Safari/537.36","Accept":"text/csv,*/*"})
            with urlopen(req,timeout=20) as response:
                raw=response.read()
            if len(raw)<5000:
                raise ValueError("short NSE response")
            x=pd.read_csv(io.BytesIO(raw))
            namec=find_col(x,["index_name"]); datec=find_col(x,["index_date"]); closec=find_col(x,["closing","close"])
            if not all([namec,datec,closec]): raise ValueError(f"Unexpected NSE index columns: {list(x.columns)}")
            x=x[x[namec].astype(str).str.strip().str.upper().eq("NIFTY 500")].copy()
            if x.empty: return None
            out=pd.DataFrame({"date":pd.to_datetime(x[datec],dayfirst=True,errors="coerce"),"nifty500_close":pd.to_numeric(x[closec],errors="coerce")}).dropna()
            out=out[out.date==pd.Timestamp(dt)]
            return out.iloc[0].to_dict() if not out.empty else None
        except Exception:
            if attempt==3: return None
            time.sleep(1.5*(attempt+1))
    return None


def load_nifty500_index(required_dates):
    required=pd.DatetimeIndex(sorted(pd.to_datetime(required_dates).unique()))
    rows=[]
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures={ex.submit(_fetch_nifty_day, pd.Timestamp(d)): d for d in required}
        for fut in as_completed(futures):
            r=fut.result()
            if r: rows.append(r)
    idx=pd.DataFrame(rows)
    if idx.empty: raise ValueError("Could not retrieve any Nifty 500 index observations from NSE archives")
    idx["date"]=pd.to_datetime(idx["date"])
    idx=idx.sort_values("date").drop_duplicates("date")
    idx["nifty500_ret_6m"]=idx["nifty500_close"].pct_change(126)
    idx["nifty500_dma200"]=idx["nifty500_close"].rolling(200,min_periods=200).mean()
    coverage=float(idx["date"].isin(required).mean())
    if len(idx)<500 or coverage<0.95:
        raise ValueError(f"Insufficient Nifty 500 index history from NSE archives: {len(idx)} rows, coverage={coverage:.1%}, requested={len(required)}")
    return idx


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--prices",required=True); ap.add_argument("--membership",required=True)
    ap.add_argument("--events",required=True); ap.add_argument("--outdir",required=True)
    ap.add_argument("--top-n",type=int,default=15)
    ap.add_argument("--transaction-cost",type=float,default=0.003)
    ap.add_argument("--rebalance-frequency",choices=["monthly","quarterly"],default="monthly")
    ap.add_argument("--sector-membership",default=None)
    ap.add_argument("--sector-constrained",action="store_true")
    ap.add_argument("--factor-weights",default="0.20,0.15,0.20,0.20,0.15")
    a=ap.parse_args(); out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)
    raw_weights=[float(x.strip()) for x in a.factor_weights.split(",")]
    if len(raw_weights)!=5 or any(x<0 for x in raw_weights) or sum(raw_weights)<=0: raise ValueError("--factor-weights must contain five non-negative values with positive sum")
    factor_weights=np.array(raw_weights,dtype=float)/sum(raw_weights)
    w6m,w12,wr6,wtrend,wram=factor_weights

    df=pd.read_csv(a.prices,low_memory=False)
    datec=find_col(df,["date"]); symc=find_col(df,["canonical_symbol","symbol"])
    closec=find_col(df,["close"]); vwapc=find_col(df,["vwap"])
    turnc=find_col(df,["turnover_₹","turnover","turnover_rs"])
    if not all([datec,symc,closec]): raise ValueError("Required price columns missing")
    if symc != "symbol" and "symbol" in df.columns: df=df.drop(columns=["symbol"])
    ren={datec:"date",symc:"symbol",closec:"close"}
    if vwapc: ren[vwapc]="vwap"
    if turnc: ren[turnc]="turnover"
    df=df.rename(columns=ren)
    if list(df.columns).count("symbol")>1:
        inds=[i for i,c in enumerate(df.columns) if c=="symbol"]
        df=df.iloc[:,[i for i,c in enumerate(df.columns) if c!="symbol" or i==inds[-1]]]
    df["date"]=pd.to_datetime(df["date"]); df["symbol"]=df["symbol"].astype(str).str.upper().str.strip()
    for c in ["close","vwap","turnover"]:
        if c in df: df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.sort_values(["symbol","date"]).drop_duplicates(["symbol","date"])

    g=df.groupby("symbol",sort=False)
    df["ret_6m"]=g["close"].pct_change(126)
    df["ret_12m_ex1m"]=g["close"].shift(21).div(g["close"].shift(252))-1
    df["dma200"]=g["close"].transform(lambda s:s.rolling(200,min_periods=200).mean())
    df["trend"]=df["close"]/df["dma200"]-1
    df["vol126"]=g["close"].transform(lambda s:s.pct_change().rolling(126,min_periods=100).std())*np.sqrt(252)
    df["ram"]=df["ret_6m"]/df["vol126"].replace(0,np.nan)
    df["adv60"]=g["turnover"].transform(lambda s:s.rolling(60,min_periods=40).mean()) if "turnover" in df else np.nan

    nifty=load_nifty500_index(df["date"].unique())
    df=df.merge(nifty[["date","nifty500_close","nifty500_ret_6m","nifty500_dma200"]],on="date",how="left")

    members=load_membership(a.membership)
    sector_members=None
    if a.sector_constrained:
        if not a.sector_membership:
            raise ValueError("--sector-membership is required with --sector-constrained")
        sector_members=pd.read_csv(a.sector_membership,parse_dates=["valid_from","valid_to"])
        sector_members["symbol"]=sector_members["symbol"].astype(str).str.upper().str.strip()
        sector_members["sector"]=sector_members["sector"].astype(str).str.strip()
        sector_members["valid_from"]=pd.to_datetime(sector_members["valid_from"],errors="coerce")
        sector_members["valid_to"]=pd.to_datetime(sector_members["valid_to"],errors="coerce")
    events=pd.read_csv(a.events); events["event_date"]=pd.to_datetime(events["event_date"],errors="coerce")
    corporate=set(events.loc[events.treatment=="corporate_event","symbol"].astype(str).str.upper())
    period_key=df["date"].dt.to_period("M") if a.rebalance_frequency=="monthly" else df["date"].dt.to_period("Q")
    reb_dates=df.groupby(period_key)["date"].max().tolist(); snapshots=[]; holdings=set(); price_dates=np.sort(df["date"].unique())

    for rd in reb_dates:
        snap=df[df.date==rd].copy()
        if snap.empty: continue
        if members["effective_date"].notna().any():
            mm=members[members.effective_date<=rd].copy()
            if not mm.empty:
                if "end_date" in mm.columns:
                    mm=mm[(mm["end_date"].isna()) | (mm["end_date"]>=rd)]
                    active=mm[["symbol"]].drop_duplicates()
                else:
                    # Snapshot-form PIT file: each review date contains the full
                    # constituent set. Use only the latest snapshot as of rd;
                    # do not carry exited constituents forward indefinitely.
                    latest_review=mm["effective_date"].max()
                    active=mm.loc[mm["effective_date"].eq(latest_review),["symbol"]].drop_duplicates()
                snap=snap.merge(active,on="symbol",how="inner")
        nifty6=float(snap["nifty500_ret_6m"].iloc[0]) if snap["nifty500_ret_6m"].notna().any() else np.nan
        nifty_dma=float(snap["nifty500_dma200"].iloc[0]) if snap["nifty500_dma200"].notna().any() else np.nan
        snap["rs6"]=snap["ret_6m"]-nifty6
        if sector_members is not None:
            sm=sector_members[(sector_members.valid_from<=rd)&((sector_members.valid_to.isna())|(sector_members.valid_to>=rd))]
            sm=sm[["symbol","sector"]].drop_duplicates("symbol")
            snap=snap.merge(sm,on="symbol",how="left")
            sector_mom=snap.dropna(subset=["sector"]).groupby("sector")["ret_6m"].mean().rename("sector_momentum")
            snap=snap.merge(sector_mom,on="sector",how="left")
            snap["sector_momentum_pct"]=snap["sector_momentum"].rank(pct=True)*100
        cols=["ret_6m","ret_12m_ex1m","rs6","trend","ram"]
        for c in cols: snap[c+"_pct"]=snap[c].rank(pct=True)*100
        if sector_members is not None:
            snap["sector_momentum_pct"]=snap["sector_momentum_pct"].fillna(50.0)
            snap["score"]=(snap["ret_6m_pct"]*.20+snap["ret_12m_ex1m_pct"]*.15+snap["rs6_pct"]*.20+snap["trend_pct"]*.20+snap["ram_pct"]*.15+snap["sector_momentum_pct"]*.10)
        else:
            snap["score"]=(snap["ret_6m_pct"]*w6m+snap["ret_12m_ex1m_pct"]*w12+snap["rs6_pct"]*wr6+snap["trend_pct"]*wtrend+snap["ram_pct"]*wram)
        eligible=snap[(snap["close"]>snap["dma200"])&(snap["ret_6m"]>0)&(snap["rs6"]>0)]
        if "adv60" in snap: eligible=eligible[eligible["adv60"]>=1e8]
        eligible=eligible.sort_values(["score","ret_6m"],ascending=False); eligible=eligible.assign(rank=eligible["score"].rank(method="first",ascending=False))
        eligible_set=set(eligible["symbol"])
        keep=[s for s in holdings if s in eligible_set and s in set(eligible.loc[eligible.score>=65,"symbol"]) and s in set(eligible.loc[eligible["rank"]<=30,"symbol"])]
        candidates=eligible[(eligible.score>=75)&(eligible["rank"]<=30)]
        chosen=[]
        sector_counts={}
        def can_add(sym):
            if sector_members is None:
                return True
            row=snap.loc[snap.symbol.eq(sym),"sector"]
            sec=row.iloc[0] if not row.empty else np.nan
            if pd.isna(sec):
                return True
            return sector_counts.get(sec,0) < max(1,int(np.floor(a.top_n*0.25)))
        def add(sym):
            chosen.append(sym)
            if sector_members is not None:
                row=snap.loc[snap.symbol.eq(sym),"sector"]
                if not row.empty and pd.notna(row.iloc[0]):
                    sec=row.iloc[0]
                    sector_counts[sec]=sector_counts.get(sec,0)+1
        for s in keep:
            if len(chosen)<a.top_n and can_add(s): add(s)
        for s in candidates.symbol:
            if s not in chosen and len(chosen)<a.top_n and can_add(s): add(s)
        chosen=chosen[:a.top_n]
        breadth=float((snap["close"]>snap["dma200"]).mean())
        healthy=int(breadth>=.60)+int(nifty6>0)+int(nifty_dma>0 and float(snap["nifty500_close"].iloc[0])>nifty_dma)
        exposure={3:1.0,2:.75,1:.50,0:.25}[healthy]
        day_events=set(events.loc[events.event_date==rd,"symbol"].astype(str).str.upper())
        chosen=[s for s in chosen if not (s in corporate and s in day_events)]
        turnover=(len(set(chosen)^set(holdings))/2)/max(len(chosen),1) if chosen else (1.0 if holdings else 0.0)
        snapshots.append({"date":rd,"n_eligible":len(eligible),"holdings":",".join(chosen),"exposure":exposure,"regime_healthy":healthy,"breadth":breadth,"nifty500_ret_6m":nifty6,"nifty500_above_dma200":bool(nifty_dma>0 and float(snap["nifty500_close"].iloc[0])>nifty_dma),"turnover":turnover})
        holdings=set(chosen)

    sig=pd.DataFrame(snapshots)
    if sig.empty: raise ValueError("No rebalance snapshots produced")
    sig["date"]=pd.to_datetime(sig.date); daily=[]
    for i,r in sig.iterrows():
        signal_date=pd.Timestamp(r.date); next_signal=pd.Timestamp(sig.iloc[i+1].date) if i+1<len(sig) else pd.Timestamp(price_dates[-1]); pos=[x for x in str(r.holdings).split(",") if x]
        if not pos: continue
        future=price_dates[price_dates>signal_date]
        if len(future)==0: continue
        execd=pd.Timestamp(future[0]); px2=df[df.symbol.isin(pos)&(df.date>=execd)&(df.date<=next_signal)].copy()
        if px2.empty: continue
        piv=px2.pivot(index="date",columns="symbol",values="close").sort_index()
        # Preserve intended equal weights; never renormalize because a selected name
        # happens to be missing from a daily price panel.
        price_returns=piv.pct_change(fill_method=None).reindex(columns=pos)
        if set(pos)-set(price_returns.columns):
            missing=sorted(set(pos)-set(price_returns.columns))
            raise ValueError(f"Missing selected symbols in execution window {signal_date.date()}: {missing}")
        rets=price_returns.mean(axis=1,skipna=False).fillna(0)*float(r.exposure); cost=float(r.turnover)*a.transaction_cost
        if len(rets): rets.iloc[0]-=cost
        for dd,rr in rets.items(): daily.append((dd,float(rr),signal_date))
    dr=pd.DataFrame(daily,columns=["date","ret","signal_date"]).sort_values(["date","signal_date"]); dr=dr.groupby("date",as_index=False).agg({"ret":"first","signal_date":"first"}).sort_values("date")
    if dr.empty: raise ValueError("No daily portfolio series produced")
    dr["nav"]=(1+dr["ret"]).cumprod(); years=(dr.date.iloc[-1]-dr.date.iloc[0]).days/365.25; cagr=float(dr.nav.iloc[-1]**(1/years)-1) if years>0 else np.nan; peak=dr.nav.cummax(); dd=dr.nav/peak-1
    metrics={"start":str(dr.date.iloc[0].date()),"end":str(dr.date.iloc[-1].date()),"cagr":cagr,"max_drawdown":float(dd.min()),"final_nav":float(dr.nav.iloc[-1]),"rebalance_count":int(len(sig)),"avg_turnover":float(sig.turnover.mean()),"top_n":a.top_n,"transaction_cost":a.transaction_cost,"rebalance_frequency":a.rebalance_frequency,"factor_weights":{"ret_6m":float(w6m),"ret_12m_ex1m":float(w12),"rs6":float(wr6),"trend":float(wtrend),"ram":float(wram)},"relative_strength_source":"NSE daily multi-index archive, Nifty 500 price index","relative_strength_definition":"stock 6M return minus Nifty 500 6M price return","regime_definition":"Nifty 500 breadth >=60%, Nifty 500 6M return >0, and Nifty 500 above 200-DMA","sector_constrained":bool(a.sector_constrained),"sector_max_holdings":max(1,int(np.floor(a.top_n*0.25))) if a.sector_constrained else None,"sector_momentum_weight":0.10 if a.sector_constrained else 0.0,"note":"Sector-constrained mode uses reconstructed historical NSE sector-index membership; sector momentum is equal-weight mean stock 6M return within the historical sector membership. Unclassified stocks receive neutral sector-momentum rank and are exempt from sector caps."}
    sig.to_csv(out/"rebalance_signals.csv",index=False); dr.to_csv(out/"portfolio_daily.csv",index=False); (out/"metrics.json").write_text(json.dumps(metrics,indent=2)); print(json.dumps(metrics,indent=2))

if __name__=="__main__": main()
