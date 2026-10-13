"""Load verified and supplemental historical NSE symbol changes consistently."""
from hashlib import sha256
from pathlib import Path

import pandas as pd

DEFAULT_SUPPLEMENT = "data/reference/nse_historical_symbol_changes.csv"
REQUIRED_COLUMNS = ("old_symbol", "new_symbol", "effective_from")


def load_symbol_rename_rows(base_path, supplement_path=DEFAULT_SUPPLEMENT):
    """Return sorted (old_symbol, new_symbol, effective_from) rows from both sources."""
    frames = []
    for raw_path in (base_path, supplement_path):
        if not raw_path:
            continue
        path = Path(raw_path)
        if not path.exists():
            if str(raw_path) == str(base_path):
                raise FileNotFoundError(f"Verified symbol map not found: {path}")
            continue
        frame = pd.read_csv(path, low_memory=False)
        missing = set(REQUIRED_COLUMNS) - set(frame.columns)
        if missing:
            raise ValueError(f"Symbol map {path} lacks required columns: {sorted(missing)}")
        frame = frame.loc[:, list(REQUIRED_COLUMNS)].copy()
        frame["old_symbol"] = frame["old_symbol"].astype(str).str.strip().str.upper()
        frame["new_symbol"] = frame["new_symbol"].astype(str).str.strip().str.upper()
        frame["effective_from"] = pd.to_datetime(
            frame["effective_from"], errors="coerce", format="mixed"
        )
        frame = frame.dropna(subset=["effective_from"])
        frame = frame[
            frame["old_symbol"].ne("")
            & frame["new_symbol"].ne("")
            & frame["old_symbol"].ne("NAN")
            & frame["new_symbol"].ne("NAN")
            & frame["old_symbol"].ne(frame["new_symbol"])
        ]
        frames.append(frame)
    if not frames:
        raise FileNotFoundError("No verified or supplemental historical symbol map exists.")
    merged = pd.concat(frames, ignore_index=True).drop_duplicates()
    merged = merged.sort_values(["effective_from", "old_symbol", "new_symbol"])
    return [
        (str(row.old_symbol), str(row.new_symbol), pd.Timestamp(row.effective_from))
        for row in merged.itertuples(index=False)
    ]


def symbol_map_fingerprint(rename_rows):
    """Stable fingerprint used to detect when old gap absences need replay."""
    records = sorted(
        (old, new, pd.Timestamp(effective).date().isoformat())
        for old, new, effective in rename_rows
    )
    payload = "\n".join(f"{old}|{new}|{date}" for old, new, date in records).encode("utf-8")
    return sha256(payload).hexdigest()
