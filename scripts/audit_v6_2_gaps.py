import argparse
from pathlib import Path
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument("--prices",required=True); p.add_argument("--membership",required=True)
p.add_argument("--outdir",default="data/processed/v6_2_gap_audit")
a=p.parse_args(); out=Path(a.outdir); out.mkdir(parents=True,exist_ok=True)
x=pd.read_csv(a.prices,low_memory=False); m=pd.read_csv(a.membership,low_memory=False)
x.date=pd.to_datetime(x.date); m.valid_from=pd.to_datetime(m.valid_from); m.valid_to=pd.to_datetime(m.valid_to)
m["to"]=m.valid_to.fillna(x.date.max()); dates=pd.DatetimeIndex(sorted(x.date.unique()))
rows=[]
for s,g in m.groupby("canonical_symbol"):
    active=set()
    for _,r in g.iterrows():
        active.update(dates[(dates>=r.valid_from)&(dates<=r["to"])])
    got=set(x.loc[x.canonical_symbol==s,"date"])
    if active:
        rows.append([s,len(active),len(active&got),len(active-got),100*len(active&got)/len(active)])
pd.DataFrame(rows,columns=["symbol","active_days","price_days","missing_days","coverage_pct"]).sort_values("coverage_pct").to_csv(out/"coverage_after_identity.csv",index=False)
print(out/"coverage_after_identity.csv")
