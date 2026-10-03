import argparse, json
from pathlib import Path
from urllib.request import urlopen, Request
import io
import pandas as pd

SOURCE_URL = "https://raw.githubusercontent.com/aditya-jha/nse-historical-membership/main/index_history/data/index_membership_history.csv"

SECTOR_PRIORITY = {
    "Nifty Financial Services": "Financial Services",
    "Nifty Bank": "Financial Services",
    "Nifty Private Bank": "Financial Services",
    "Nifty PSU Bank": "Financial Services",
    "Nifty IT": "IT",
    "Nifty FMCG": "FMCG",
    "Nifty Pharma": "Pharma",
    "Nifty Auto": "Auto",
    "Nifty Metal": "Metal",
    "Nifty Realty": "Realty",
    "Nifty Energy": "Energy",
    "Nifty Oil & Gas": "Energy",
    "Nifty Healthcare Index": "Healthcare",
    "Nifty Consumer Durables": "Consumer Durables",
    "Nifty Media": "Media",
}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--out",required=True)
    ap.add_argument("--symbol-map",default="data/input/verified_symbol_map.csv")
    a=ap.parse_args()

    req=Request(SOURCE_URL,headers={"User-Agent":"Mozilla/5.0"})
    raw=urlopen(req,timeout=60).read()
    m=pd.read_csv(io.BytesIO(raw),low_memory=False)
    m["index_name"]=m["index_name"].astype(str).str.strip()
    m=m[m["index_name"].isin(SECTOR_PRIORITY)].copy()
    m["valid_from"]=pd.to_datetime(m["valid_from"],errors="coerce")
    m["valid_to"]=pd.to_datetime(m["valid_to"],errors="coerce")
    m["symbol"]=m["symbol"].astype(str).str.upper().str.strip()

    sm=pd.read_csv(a.symbol_map)
    sm["old_symbol"]=sm["old_symbol"].astype(str).str.upper().str.strip()
    sm["new_symbol"]=sm["new_symbol"].astype(str).str.upper().str.strip()
    changes=dict(zip(sm["new_symbol"],sm["old_symbol"]))
    def historical(sym, d):
        cur=sym
        seen=set()
        while cur not in seen:
            seen.add(cur)
            rows=sm[(sm.new_symbol==cur)&(pd.to_datetime(sm.effective_from,errors="coerce")>d)]
            if rows.empty: break
            cur=str(rows.sort_values("effective_from").iloc[0].old_symbol).upper()
        return cur

    m["sector"]=m["index_name"].map(SECTOR_PRIORITY)
    m["source_symbol"]=m["symbol"]
    m["symbol"]= [historical(s, d) if pd.notna(d) else s for s,d in zip(m.symbol,m.valid_from)]
    # Resolve overlapping sector indices into one broad sector.  Financial-sector
    # sub-indices are deliberately grouped together to prevent double counting.
    m=m[["symbol","sector","valid_from","valid_to","index_name","source_symbol","source"]].drop_duplicates()
    m=m.sort_values(["valid_from","symbol","sector"])
    # If a stock belongs to multiple mapped sectors on the same date, retain the
    # first deterministic sector by the explicit priority order above.
    order={v:i for i,v in enumerate(dict.fromkeys(SECTOR_PRIORITY.values()))}
    m["_priority"]=m["sector"].map(order)
    m=m.sort_values(["valid_from","valid_to","symbol","_priority"]).drop_duplicates(["symbol","valid_from","valid_to"],keep="first")
    m=m.drop(columns="_priority").reset_index(drop=True)
    Path(a.out).parent.mkdir(parents=True,exist_ok=True)
    m.to_csv(a.out,index=False)
    print(json.dumps({
        "rows":len(m),
        "symbols":int(m.symbol.nunique()),
        "sectors":sorted(m.sector.unique().tolist()),
        "start":str(m.valid_from.min().date()),
        "end":str(m.valid_to.max().date()) if m.valid_to.notna().any() else None,
        "source":SOURCE_URL,
    },indent=2))

if __name__=="__main__":
    main()
