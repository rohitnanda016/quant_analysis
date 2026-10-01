import argparse
import pandas as pd

p=argparse.ArgumentParser()
p.add_argument('--events',required=True)
p.add_argument('--actions',required=True)
p.add_argument('--top',type=int,default=120)
a=p.parse_args()
e=pd.read_csv(a.events,low_memory=False)
x=pd.read_csv(a.actions,low_memory=False)
e['date']=pd.to_datetime(e['date'],errors='coerce')
x['ex_date']=pd.to_datetime(x['ex_date'],errors='coerce')
e['symbol']=e['canonical_symbol'].astype(str).str.upper().str.strip()
x['symbol']=x['symbol'].astype(str).str.upper().str.strip()
e['raw_factor_from_prices']=e['prev_close']/e['close']
rows=[]
for _,r in e.iterrows():
    cand=x[(x.symbol==r.symbol)&(x.ex_date.between(r.date-pd.Timedelta(days=3),r.date+pd.Timedelta(days=3)))].copy()
    if len(cand):
        cand['event_date']=r.date
        cand['raw_prev_close']=r.prev_close
        cand['raw_close']=r.close
        cand['raw_return']=r['return']
        rows.append(cand)
near=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()
worst=e.sort_values('return',key=lambda s:s.abs(),ascending=False).head(a.top)
print('\nTOP RAW EXTREME EVENTS')
print(worst.to_string(index=False))
print('\nNEARBY NSE ACTIONS FOR EXTREME EVENTS')
print(near.sort_values(['event_date','symbol']).to_string(index=False) if len(near) else 'NONE')
