import argparse, json, time
from pathlib import Path

import pandas as pd
import requests

API_HOSTS = [
    "https://www.nseindia.com",
    "https://www.nseindia.com",
]
API_PATH = "/api/corporates-corporateActions"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def make_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive",
        "DNT": "1",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Referer": "https://www.nseindia.com/",
    })
    return s


def fetch_session():
    # NSE can intermittently reject the landing-page request from hosted CI IPs.
    # Treat a successful JSON API response as sufficient session establishment;
    # do not require the homepage to return 200.
    last_error = None

    for base in API_HOSTS:
        s = make_session()

        for attempt in range(6):
            try:
                # Warm the session, but don't make this request a hard prerequisite.
                try:
                    s.get(base + "/", timeout=20)
                except requests.RequestException:
                    pass

                probe = s.get(
                    base + API_PATH,
                    params={
                        "index": "equities",
                        "from_date": "01-01-2026",
                        "to_date": "02-01-2026",
                    },
                    timeout=45,
                )

                if probe.status_code == 200:
                    obj = probe.json()
                    if isinstance(obj, (dict, list)):
                        return s

                last_error = RuntimeError(
                    f"NSE probe returned HTTP {probe.status_code}"
                )
            except Exception as exc:
                last_error = exc

            time.sleep(min(2 ** attempt, 20))

    raise RuntimeError(f"Could not establish NSE API session: {last_error}")


def get_range(s, start, end):
    params = {
        "index": "equities",
        "from_date": start.strftime("%d-%m-%Y"),
        "to_date": end.strftime("%d-%m-%Y"),
    }

    last_error = None
    for attempt in range(7):
        try:
            r = s.get(
                "https://www.nseindia.com" + API_PATH,
                params=params,
                timeout=90,
            )

            if r.status_code == 200:
                obj = r.json()
                data = obj.get("data", []) if isinstance(obj, dict) else obj
                return pd.DataFrame(data if isinstance(data, list) else [])

            last_error = RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
        except Exception as exc:
            last_error = exc

        # Refresh cookies after throttling/server errors.
        if attempt in (2, 4):
            try:
                s.get("https://www.nseindia.com/", timeout=20)
            except requests.RequestException:
                pass

        time.sleep(min(2 ** attempt, 30))

    raise RuntimeError(
        f"NSE corporate-actions request failed for "
        f"{start.date()}..{end.date()}: {last_error}"
    )


p = argparse.ArgumentParser()
p.add_argument("--start", required=True)
p.add_argument("--end", required=True)
p.add_argument("--out", required=True)
a = p.parse_args()

start, end = pd.Timestamp(a.start), pd.Timestamp(a.end)
s = fetch_session()

frames = []
cur = start

while cur <= end:
    nxt = min(cur + pd.Timedelta(days=89), end)
    df = get_range(s, cur, nxt)

    if not df.empty:
        frames.append(df)

    cur = nxt + pd.Timedelta(days=1)
    time.sleep(0.5)

out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()

if not out.empty:
    out.columns = [
        str(c).strip().lower().replace(" ", "_") for c in out.columns
    ]

    if "symbol" not in out.columns or "ex_date" not in out.columns:
        raise RuntimeError(
            "NSE corporate-action response is missing required symbol/ex_date columns"
        )

    out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
    out["ex_date"] = pd.to_datetime(out["ex_date"], errors="coerce")
    out = (
        out.drop_duplicates()
        .sort_values(["ex_date", "symbol"], na_position="last")
    )

Path(a.out).parent.mkdir(parents=True, exist_ok=True)
out.to_csv(a.out, index=False)

summary = {
    "rows": int(len(out)),
    "start": str(start.date()),
    "end": str(end.date()),
    "source": "https://www.nseindia.com" + API_PATH,
    "chunks": int(((end - start).days // 90) + 1),
}

Path(a.out + ".summary.json").write_text(json.dumps(summary, indent=2))
print(json.dumps({"rows": int(len(out)), "out": a.out}, indent=2))
