"""Point-in-time membership windows for limiting research-data gap repair.

A missing price is relevant to this strategy only while a security belongs to
Nifty 500 or during the lookback needed to calculate its entry signals.
"""
from collections import defaultdict

import pandas as pd

MEMBERSHIP_ALIAS_COLUMNS = (
    "symbol",
    "source_symbol",
    "canonical_symbol",
    "acquisition_symbol",
)


def build_membership_session_windows(membership, calendar, warmup_sessions=252):
    """Map known symbol aliases to inclusive (start, end) session-index windows.

    Each membership interval is expanded backwards by warmup_sessions so
    momentum/200-day features have sufficient pre-entry prices, and by one
    session after valid_to to observe a possible exit mark. Membership dates
    are mapped onto the supplied exchange-session calendar.
    """
    if warmup_sessions < 0:
        raise ValueError("warmup_sessions must be non-negative")
    dates = pd.DatetimeIndex(pd.to_datetime(calendar, errors="coerce", format="mixed")).dropna().sort_values().unique()
    if len(dates) == 0:
        return {}
    dates = pd.DatetimeIndex(dates)
    if isinstance(membership, (str, bytes)):
        frame = pd.read_csv(membership, low_memory=False)
    else:
        frame = membership.copy()
    required = {"valid_from", "valid_to", "symbol"}
    if not required.issubset(frame.columns):
        raise ValueError(f"Membership file must contain {sorted(required)}")

    windows = defaultdict(list)
    max_date = pd.Timestamp(dates[-1])
    for row in frame.to_dict("records"):
        start = pd.to_datetime(row.get("valid_from"), errors="coerce", format="mixed")
        raw_end = row.get("valid_to")
        end = max_date if pd.isna(raw_end) or str(raw_end).strip() == "" else pd.to_datetime(raw_end, errors="coerce", format="mixed")
        if pd.isna(start) or pd.isna(end) or end < dates[0] or start > dates[-1]:
            continue
        start_i = int(dates.searchsorted(pd.Timestamp(start), side="left"))
        end_i = int(dates.searchsorted(pd.Timestamp(end), side="right")) - 1
        if start_i >= len(dates) or end_i < 0 or start_i > end_i:
            continue
        low_i = max(0, start_i - int(warmup_sessions))
        high_i = min(len(dates) - 1, end_i + 1)
        aliases = set()
        for col in MEMBERSHIP_ALIAS_COLUMNS:
            value = str(row.get(col, "") or "").strip().upper()
            if value and value not in {"NAN", "NONE", "<NA>"}:
                aliases.add(value)
        for alias in aliases:
            windows[alias].append((low_i, high_i))

    return {alias: sorted(set(ranges)) for alias, ranges in windows.items()}


def in_membership_research_window(symbol, session_index, windows):
    """Whether a symbol/session is inside a membership interval or its warm-up."""
    value = str(symbol).strip().upper()
    return any(start <= int(session_index) <= end for start, end in windows.get(value, ()))
