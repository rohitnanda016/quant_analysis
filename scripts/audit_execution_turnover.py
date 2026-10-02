import argparse, json
from pathlib import Path
import pandas as pd

def holding_set(value):
    return {x.strip() for x in str(value).split(",") if x.strip()}

def turnover_from_holdings(cur, prev):
    if not cur:
        return 1.0 if prev else 0.0
    return (len(cur ^ prev) / 2) / max(len(cur), 1)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--signals",required=True)
    ap.add_argument("--portfolio",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()

    s=pd.read_csv(a.signals,parse_dates=["date"]).sort_values("date").reset_index(drop=True)
    p=pd.read_csv(a.portfolio,parse_dates=["date","signal_date"]).sort_values("date").reset_index(drop=True)
    issues=[]

    # Only signals that actually feed the realized portfolio are audited.
    # Earlier signals can exist because the factor history starts before the
    # first date for which a complete execution series is produced.
    execution_signal_start = p["signal_date"].min() if not p.empty else None
    audited = s[s["date"] >= execution_signal_start].copy() if execution_signal_start is not None else s.iloc[0:0].copy()

    prev=set()
    for _,r in audited.iterrows():
        cur=holding_set(r["holdings"])
        expected_turn=turnover_from_holdings(cur, prev)
        reported=float(r["turnover"])
        if abs(reported-expected_turn)>1e-12:
            issues.append({
                "type":"turnover_mismatch",
                "date":str(r.date.date()),
                "reported":reported,
                "expected":expected_turn,
                "current_count":len(cur),
                "previous_count":len(prev),
                "symmetric_difference":len(cur ^ prev)
            })
        if not (0 <= reported <= 1):
            issues.append({"type":"turnover_out_of_range","date":str(r.date.date()),"value":reported})
        prev=cur

    if s.date.duplicated().any():
        issues.append({"type":"duplicate_signal_date"})
    if p.empty:
        issues.append({"type":"empty_portfolio"})
    else:
        bad=p[p.date<=p.signal_date]
        if not bad.empty:
            issues.append({"type":"lookahead_execution_rows","count":len(bad)})
        if p.date.duplicated().any():
            issues.append({"type":"duplicate_portfolio_date"})
        if p["ret"].isna().any():
            issues.append({"type":"nan_returns"})

    result={
        "signal_rows":len(s),
        "audited_signal_rows":len(audited),
        "portfolio_rows":len(p),
        "turnover_mean":float(audited.turnover.mean()) if not audited.empty else None,
        "turnover_max":float(audited.turnover.max()) if not audited.empty else None,
        "execution_start":str(p.date.min().date()) if not p.empty else None,
        "execution_signal_start":str(execution_signal_start.date()) if execution_signal_start is not None else None,
        "first_signal":str(s.date.min().date()) if not s.empty else None,
        "issues":issues,
        "status":"PASS" if not issues else "FAIL"
    }
    Path(a.out).write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
    if issues:
        raise SystemExit(1)

if __name__=="__main__":
    main()
