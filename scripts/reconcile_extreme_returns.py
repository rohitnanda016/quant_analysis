import argparse, json, re
from pathlib import Path
import pandas as pd

def parse_factor(purpose):
    p = str(purpose or "").upper()
    m = re.search(r"FROM\s+RS\s*([0-9.]+).*?TO\s+RS\s*([0-9.]+)", p)
    if m and ("SPLIT" in p or "CONSOLIDATION" in p or "SUB-DIVISION" in p):
        old, new = float(m.group(1)), float(m.group(2))
        return new / old, "split_or_consolidation"
    m = re.search(r"BONUS\s+(\d+)\s*:\s*(\d+)", p)
    if m:
        x, y = int(m.group(1)), int(m.group(2))
        return y / (x + y), "bonus"
    return None, None

def aliases(path):
    if not Path(path).exists(): return {}
    m = pd.read_csv(path)
    out={}
    for _,r in m.iterrows():
        old=str(r.get("old_symbol","")).strip().upper()
        new=str(r.get("new_symbol","")).strip().upper()
        if old and new and old!="NAN" and new!="NAN":
            out[old]=new; out[new]=new
    return out

p=argparse.ArgumentParser()
p.add_argument("--extremes",required=True)
p.add_argument("--actions",required=True)
p.add_argument("--symbol-map",required=False,default="")
p.add_argument("--out",required=True)
a=p.parse_args()

e=pd.read_csv(a.extremes)
e["date"]=pd.to_datetime(e["date"],errors="coerce")
e["symbol"]=e["canonical_symbol"].astype(str).str.upper().str.strip()
e["observed_factor"]=pd.to_numeric(e["prev_close"],errors="coerce")/pd.to_numeric(e["close"],errors="coerce")

ca=pd.read_csv(a.actions)
ca.columns=[str(c).strip().lower().replace(" ","_") for c in ca.columns]
ca["symbol"]=ca["symbol"].astype(str).str.upper().str.strip()
ca["ex_date"]=pd.to_datetime(ca["ex_date"],errors="coerce")
ca["purpose"]=ca.get("purpose","").fillna("").astype(str)
ca[["inferred_factor","action_type"]]=ca["purpose"].apply(lambda x: pd.Series(parse_factor(x)))

amap=aliases(a.symbol_map)
e["lookup_symbol"]=e["symbol"].map(lambda x: amap.get(x,x))
ca["lookup_symbol"]=ca["symbol"].map(lambda x: amap.get(x,x))

m=e.merge(ca,how="left",left_on=["lookup_symbol","date"],right_on=["lookup_symbol","ex_date"],suffixes=("_extreme","_action"))
m["factor_error"]=abs(m["observed_factor"]/m["inferred_factor"]-1)
m["status"]="NO_EXACT_ACTION"
has=m["purpose"].notna() & (m["purpose"].str.len()>0)
m.loc[has,"status"]="ACTION_ON_DATE"
exact_factor=has & m["inferred_factor"].notna() & (m["factor_error"]<=0.08)
m.loc[exact_factor,"status"]="EXACT_SPLIT_BONUS_RATIO_MATCH"
m.loc[has & m["inferred_factor"].isna(),"status"]="ACTION_ON_DATE_NON_PRICE_FACTOR"
m.loc[has & m["inferred_factor"].notna() & (m["factor_error"]>0.08),"status"]="ACTION_RATIO_MISMATCH"

cols=["symbol_extreme","date","prev_close","close","return","observed_factor","symbol_action","purpose","ex_date","record_date","face_value","inferred_factor","action_type","factor_error","status"]
cols=[c for c in cols if c in m.columns]
m[cols].sort_values(["date","symbol_extreme"]).to_csv(a.out,index=False)
summary=m["status"].value_counts(dropna=False).to_dict()
Path(a.out+".summary.json").write_text(json.dumps(summary,indent=2,default=str))
print(json.dumps(summary,indent=2,default=str))
