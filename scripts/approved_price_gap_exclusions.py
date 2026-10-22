"""Explicit scoped exclusions for unresolved price gaps.

An exclusion is an audit scope decision, never an observed market price or
verified no-trade fact. It only applies when the exact symbol/date is present
as an unresolved absence in the replay artifact.
"""
from pathlib import Path
import pandas as pd

REQUIRED_LEDGER_COLUMNS = {
    "date", "symbol", "status", "reason", "approval_reference"
}
ABSENCE_COLUMNS = {"date", "symbol", "status"}
EXCLUSION_STATUS = "excluded_unresolved"
ABSENCE_STATUS = "unresolved_archive_absence"


def _normalise_pair(date_value, symbol_value):
    date = pd.to_datetime(date_value, errors="coerce")
    if pd.isna(date):
        return None
    symbol = str(symbol_value).strip().upper()
    if not symbol or symbol.lower() in {"nan", "none", "<na>"}:
        return None
    return (pd.Timestamp(date).normalize(), symbol)


def load_scope_exclusions(path):
    """Load and strictly validate the approved excluded/unresolved ledger."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f"Scope-exclusion ledger is missing: {path}")
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = REQUIRED_LEDGER_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"Scope-exclusion ledger missing columns: {sorted(missing)}")

    rows = []
    seen = set()
    for line_no, row in frame.iterrows():
        pair = _normalise_pair(row["date"], row["symbol"])
        if pair is None:
            raise ValueError(f"Invalid date/symbol in scope-exclusion ledger row {line_no + 2}")
        status = row["status"].strip().lower()
        if status != EXCLUSION_STATUS:
            raise ValueError(
                f"Scope-exclusion ledger row {line_no + 2} must use status "
                f"{EXCLUSION_STATUS!r}; got {status!r}"
            )
        if not row["reason"].strip() or not row["approval_reference"].strip():
            raise ValueError(
                f"Scope-exclusion ledger row {line_no + 2} requires reason and approval_reference"
            )
        if pair in seen:
            raise ValueError(f"Duplicate scope-exclusion pair: {pair[1]} {pair[0].date()}")
        seen.add(pair)
        rows.append({
            "date": pair[0].date().isoformat(),
            "symbol": pair[1],
            "status": EXCLUSION_STATUS,
            "reason": row["reason"].strip(),
            "approval_reference": row["approval_reference"].strip(),
            "_pair": pair,
        })
    return rows


def match_scope_exclusions_to_archive_absences(exclusion_rows, absence_path):
    """Return exact matches to replay absences; mismatches are never accepted."""
    path = Path(absence_path)
    if not path.is_file():
        return set(), list(exclusion_rows), [f"Archive-absence report is missing: {path}"]

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    missing = ABSENCE_COLUMNS - set(frame.columns)
    if missing:
        return set(), list(exclusion_rows), [
            f"Archive-absence report missing columns: {sorted(missing)}"
        ]

    absences = set()
    for _, row in frame.iterrows():
        if row["status"].strip().lower() != ABSENCE_STATUS:
            continue
        pair = _normalise_pair(row["date"], row["symbol"])
        if pair is not None:
            absences.add(pair)

    matched = set()
    unmatched = []
    for exclusion in exclusion_rows:
        pair = exclusion["_pair"]
        if pair in absences:
            matched.add(pair)
        else:
            unmatched.append(exclusion)

    issues = []
    if unmatched:
        labels = ", ".join(
            f"{row['symbol']} {row['date']}" for row in unmatched
        )
        issues.append(
            "Scope exclusion(s) did not match an exact unresolved_archive_absence "
            f"row in the replay artifact: {labels}"
        )
    return matched, unmatched, issues
