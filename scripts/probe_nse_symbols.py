import argparse, io, json
from pathlib import Path
import requests, pandas as pd

URLS = [
    "https://www.nseindia.com/api/historicalOR/generateSecurityWiseHistoricalData",
    "https://www.nseindia.com/api/historical/securityArchives",
]
SYMBOLS = ["IIFLWAM", "BURGERKING", "CADILAHC", "PHILIPCARB", "ADANITRANS"]

def clean(c):
    return " ".join(str(c).replace("\ufeff","").replace("\xa0"," ").strip().strip('"').split()).lower()

def probe(session, symbol, start, end):
    params = {
        "symbol": symbol, "from": start, "to": end, "series": "EQ",
        "type": "priceVolumeDeliverable", "csv": "true",
        "dataType": "priceVolumeDeliverable",
    }
    out=[]
    for url in URLS:
        try:
            r=session.get(url, params=params, timeout=45)
            item={"symbol":symbol,"endpoint":url,"status":r.status_code,
                  "content_type":r.headers.get("content-type",""),
                  "bytes":len(r.content),
                  "url":r.url,
                  "prefix":r.content[:300].decode("utf-8","replace")}
            if r.status_code == 200 and len(r.content)>0:
                raw=r.content.decode("utf-8-sig",errors="replace")
                try:
                    d=pd.read_csv(io.StringIO(raw),skipinitialspace=True)
                    item["parse"]="csv"
                    item["columns"]=[clean(c) for c in d.columns.tolist()]
                    item["rows"]=int(len(d))
                except Exception as e:
                    item["parse_error"]=str(e)[:200]
                    try:
                        obj=r.json()
                        rows=obj.get("data",obj) if isinstance(obj,dict) else obj
                        item["parse"]="json"
                        item["json_rows"]=int(len(rows)) if hasattr(rows,"__len__") else None
                        item["json_keys"]=list(obj.keys())[:30] if isinstance(obj,dict) else []
                    except Exception as je:
                        item["json_error"]=str(je)[:200]
            out.append(item)
        except Exception as e:
            out.append({"symbol":symbol,"endpoint":url,"exception":repr(e)[:300]})
    return out

p=argparse.ArgumentParser()
p.add_argument("--start",default="23-06-2022"); p.add_argument("--end",default="30-06-2022")
p.add_argument("--out",default="results/latest/nse_symbol_probe.json")
a=p.parse_args()
s=requests.Session()
s.headers.update({"User-Agent":"Mozilla/5.0","Accept":"*/*","Referer":"https://www.nseindia.com/"})
try: s.get("https://www.nseindia.com/report-detail/eq_security",timeout=30)
except Exception as e: print("session warmup:",repr(e))
results=[]
for sym in SYMBOLS:
    results.extend(probe(s,sym,a.start,a.end))
Path(a.out).parent.mkdir(parents=True,exist_ok=True)
Path(a.out).write_text(json.dumps({"start":a.start,"end":a.end,"results":results},indent=2))
print(Path(a.out).read_text())
