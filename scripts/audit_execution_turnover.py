import argparse, json
from pathlib import Path
import pandas as pd

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--signals",required=True)
    ap.add_argument("--portfolio",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    s=pd.read_csv(a.signals,parse_dates=["date"])
    p=pd.read_csv(a.portfolio,parse_dates=["date","signal_date"])
    s=s.sort_values("date").reset_index(drop=True)
    issues=[]
    expected=[]
    prev=set()
    for _,r in s.iterrows():
        cur={x for x in str(r["holdings"]).split(",") if x}
        expected_turn=((len(cur^prev)/2)/max(len(cur),1)) if cur else (1.0 if prev else 0.0)
        if abs(float(r["turnover"])-expected_turn)>1e-12:
            issues.append({"type":"turnover_mismatch","date":str(r.date.date()),"reported":float(r.turnover),"expected":expected_turn})
        if not (0 <= float(r.turnover) <= 1):
            issues.append({"type":"turnover_out_of_range","date":str(r.date.date()),"value":float(r.turnover)})
        expected.append(expected_turn); prev=cur
    if s.date.duplicated().any(): issues.append({"type":"duplicate_signal_date"})
    if p.empty: issues.append({"type":"empty_portfolio"})
    else:
        bad=p[p.date<=p.signal_date]
        if not bad.empty: issues.append({"type":"lookahead_execution_rows","count":len(bad)})
        if p.date.duplicated().any(): issues.append({"type":"duplicate_portfolio_date"})
        if p["ret"].isna().any(): issues.append({"type":"nan_returns"})
    result={"signal_rows":len(s),"portfolio_rows":len(p),"turnover_mean":float(s.turnover.mean()),"turnover_max":float(s.turnover.max()),"execution_start":str(p.date.min().date()) if not p.empty else None,"first_signal":str(s.date.min().date()) if not s.empty else None,"issues":issues,"status":"PASS" if not issues else "FAIL"}
    Path(a.out).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    if issues: raise SystemExit(1)

if __name__=="__main__": main()
