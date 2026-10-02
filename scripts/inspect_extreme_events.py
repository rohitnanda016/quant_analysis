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
e['symbol']=(e['canonical_symbol'] if 'canonical_symbol' in e.columns else e['symbol']).astype(str).str.upper().str.strip()
x['symbol']=x['symbol'].astype(str).str.upper().str.strip()

if {'prev_close_raw','close_raw'}.issubset(e.columns):
    e['raw_factor_from_prices']=e['prev_close_raw']/e['close_raw']
elif {'prev_close','close'}.issubset(e.columns):
    e['raw_factor_from_prices']=e['prev_close']/e['close']
else:
    e['raw_factor_from_prices']=pd.NA

rows=[]
for _,r in e.iterrows():
    cand=x[(x.symbol==r.symbol)&(x.ex_date.between(r.date-pd.Timedelta(days=3),r.date+pd.Timedelta(days=3)))].copy()
    if len(cand):
        cand['event_date']=r.date
        cand['raw_prev_close']=r.get('prev_close_raw',r.get('prev_close'))
        cand['raw_close']=r.get('close_raw',r.get('close'))
        cand['raw_return']=r.get('return')
        cand['adjusted_return']=r.get('adjusted_return')
        cand['abs_adjusted_return']=r.get('abs_adjusted_return')
        cand['status']=r.get('status')
        rows.append(cand)

near=pd.concat(rows,ignore_index=True) if rows else pd.DataFrame()
worst=e.sort_values('abs_adjusted_return',ascending=False).head(a.top) if 'abs_adjusted_return' in e.columns else e.sort_values('return',key=lambda s:s.abs(),ascending=False).head(a.top)
print('EVENT FILE COLUMNS')
print(','.join(e.columns))
print('TOP EXTREME EVENTS')
print(worst.to_string(index=False))
print('NEARBY NSE ACTIONS FOR EXTREME EVENTS')
print(near.sort_values(['event_date','symbol']).to_string(index=False) if len(near) else 'NONE')
