import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

import pandas as pd

from scripts.repair_price_gaps_bhavcopy import (
    parse_archive,
    checkpoint_matches,
    target_inventory_fingerprint,
    inventory_attempts_complete,
)
from scripts.membership_scope import (
    build_membership_session_windows,
    in_membership_research_window,
)
from scripts.audit_price_gap_readiness import accounting_summary


class ParseBhavcopyTests(unittest.TestCase):
    def test_legacy_archive_columns(self):
        csv = (
            "SYMBOL,SERIES,DATE,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,"
            "LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,NO_OF_TRADES\n"
            "IBVENTURES,EQ,29-Jun-2018,498.55,500,505,490,499,501,498,12345,61.7,321\n"
            "IBVENTURES,E1,29-Jun-2018,100,100,101,99,100,100,100,100,1,12\n"
        )
        frame = parse_archive(csv, date(2018, 6, 29))
        self.assertEqual(len(frame), 1)
        row = frame.iloc[0]
        self.assertEqual(row["symbol"], "IBVENTURES")
        self.assertEqual(row["series"], "EQ")
        self.assertAlmostEqual(float(row["close"]), 501.0)
        self.assertAlmostEqual(float(row["open"]), 500.0)
        self.assertAlmostEqual(float(row["prev_close"]), 498.55)
        self.assertAlmostEqual(float(row["volume"]), 12345.0)
        self.assertAlmostEqual(float(row["traded_value"]), 6170000.0)

    def test_udiff_archive_columns(self):
        csv = (
            "TradDt,BizDt,Sgmt,TckrSymb,SctySrs,ISIN,OpnPric,HghPric,LwPric,"
            "ClsPric,LastPric,PrvsClsgPric,AvgPric,TtlTradgVol,TtlTrfVal,TtlNbOfTxsExctd\n"
            "2024-07-08,2024-07-08,CM,IBVENTURES,EQ,INE244H01027,410,420,400,"
            "415,414,409,412,12345,5100000,321\n"
            "2024-07-08,2024-07-08,CM,IBVENTURES,E1,INE9274G01018,100,101,99,"
            "100,100,99,100,500,50000,10\n"
        )
        frame = parse_archive(csv, date(2024, 7, 8))
        self.assertEqual(len(frame), 1)
        row = frame.iloc[0]
        self.assertEqual(row["symbol"], "IBVENTURES")
        self.assertEqual(row["series"], "EQ")
        self.assertAlmostEqual(float(row["close"]), 415.0)
        self.assertAlmostEqual(float(row["open"]), 410.0)
        self.assertAlmostEqual(float(row["prev_close"]), 409.0)
        self.assertAlmostEqual(float(row["volume"]), 12345.0)
        self.assertAlmostEqual(float(row["traded_value"]), 5100000.0)

    def test_alternate_series_rows_are_preserved_for_price_continuity(self):
        csv = (
            "SYMBOL,SERIES,DATE,PREV_CLOSE,OPEN_PRICE,HIGH_PRICE,LOW_PRICE,"
            "LAST_PRICE,CLOSE_PRICE,AVG_PRICE,TTL_TRD_QNTY,TURNOVER_LACS,NO_OF_TRADES\n"
            "AARTIIND,EQ,03-Jul-2019,100,100,103,99,102,102,101,1000,1,10\n"
            "AARTIIND,BE,04-Jul-2019,102,102,104,101,103,103,103,800,0.8,8\n"
            "AARTIIND,BZ,05-Jul-2019,103,103,104,102,103,103,103,500,0.5,5\n"
        )
        frame = parse_archive(csv, date(2019, 7, 4), filter_eq=False)
        self.assertEqual(set(frame["series"]), {"EQ", "BE", "BZ"})
        self.assertEqual(len(frame), 3)
        self.assertEqual(frame.loc[frame["series"].eq("BE"), "close"].iloc[0], 103)

    def test_accounting_includes_unresolved_pairs_without_approving_them(self):
        result = accounting_summary(100, 20, 0, 5, 70, 5)
        self.assertEqual(result["accounted"], 100)
        self.assertFalse(result["mismatch"])
        self.assertEqual(result["buckets"]["unresolved_archive_absence"], 70)
        self.assertEqual(result["buckets"]["unresolved_fetch_error"], 5)

    def test_accounting_detects_double_count_or_missing_pairs(self):
        result = accounting_summary(100, 20, 0, 5, 69, 5)
        self.assertTrue(result["mismatch"])
        self.assertEqual(result["accounted"], 99)

    def test_rejects_archive_missing_identity_or_close(self):
        csv = "FOO,BAR\nx,y\n"
        with self.assertRaises(ValueError):
            parse_archive(csv, date(2024, 7, 8))

    def test_checkpoint_resume_requires_matching_inventory(self):
        checkpoint = {
            "date_start": "2014-01-01",
            "date_end": "2026-08-31",
            "target_symbol_date_pairs": 42628,
            "total_dates": 2892,
        }
        self.assertTrue(checkpoint_matches(checkpoint, "2014-01-01", "2026-08-31", 42628, 2892))
        self.assertFalse(checkpoint_matches(checkpoint, "2014-01-01", "2026-08-31", 42627, 2892))
        self.assertFalse(checkpoint_matches(checkpoint, "2014-01-01", "2026-08-30", 42628, 2892))
        self.assertFalse(checkpoint_matches({}, "2014-01-01", "2026-08-31", 42628, 2892))

        inventory = {pd.Timestamp("2024-01-02"): {"ABC", "XYZ"}}
        fingerprint = target_inventory_fingerprint(inventory)
        checkpoint.update({
            "membership_warmup_sessions": 252,
            "target_inventory_sha256": fingerprint,
        })
        self.assertTrue(checkpoint_matches(
            checkpoint, "2014-01-01", "2026-08-31", 42628, 2892, 252, fingerprint
        ))
        self.assertFalse(checkpoint_matches(
            checkpoint, "2014-01-01", "2026-08-31", 42628, 2892, 126, fingerprint
        ))
        self.assertFalse(checkpoint_matches(
            checkpoint, "2014-01-01", "2026-08-31", 42628, 2892, 252, "different"
        ))

    def test_batch_completes_after_every_date_is_attempted_even_with_failures(self):
        self.assertFalse(inventory_attempts_complete({"2024-01-01"}, 3))
        self.assertTrue(inventory_attempts_complete({"2024-01-01", "2024-01-02", "2024-01-03"}, 3))
        # Failed dates are attempted too; readiness will report their fetch errors.
        attempted = {"2024-01-01", "2024-01-02"}
        self.assertTrue(inventory_attempts_complete(attempted, 2))

    def test_membership_scope_includes_signal_warmup_and_exit_session(self):
        calendar = pd.date_range("2024-01-01", periods=12, freq="D")
        membership = pd.DataFrame([{
            "symbol": "ABC",
            "canonical_symbol": "ABC",
            "source_symbol": "OLDABC",
            "valid_from": "2024-01-06",
            "valid_to": "2024-01-08",
        }])
        windows = build_membership_session_windows(membership, calendar, warmup_sessions=2)
        self.assertTrue(in_membership_research_window("ABC", 3, windows))
        self.assertTrue(in_membership_research_window("OLDABC", 8, windows))
        self.assertFalse(in_membership_research_window("ABC", 2, windows))
        self.assertFalse(in_membership_research_window("ABC", 9, windows))

    def test_mixed_date_formats_do_not_create_false_duplicate_keys(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prices = root / "prices.csv"
            outdir = root / "quality"
            pd.DataFrame([
                {"symbol": "DRDATSONS", "series": "EQ", "date": "2024-01-02", "prev_close": 9.5, "open": 9.6, "high": 10.0, "low": 9.4, "close": 9.85, "vwap": 9.8, "volume": 100, "turnover ₹": 1000},
                {"symbol": "DRDATSONS", "series": "EQ", "date": "03-Jan-2024", "prev_close": 9.85, "open": 9.8, "high": 9.9, "low": 9.6, "close": 9.75, "vwap": 9.7, "volume": 110, "turnover ₹": 1100},
                {"symbol": "DRDATSONS", "series": "EQ", "date": "2024/01/04", "prev_close": 9.75, "open": 9.7, "high": 9.8, "low": 9.3, "close": 9.4, "vwap": 9.5, "volume": 120, "turnover ₹": 1200},
            ]).to_csv(prices, index=False)
            subprocess.run([
                sys.executable, "scripts/audit_price_quality.py",
                "--prices", str(prices), "--outdir", str(outdir),
            ], check=True, capture_output=True, text=True)
            summary = json.loads((outdir / "price_quality_summary.json").read_text())
            self.assertEqual(summary["invalid_date_rows"], 0)
            self.assertEqual(summary["duplicate_date_symbol"], 0)
            self.assertEqual(summary["rows"], 3)

    def test_resumed_merge_removes_only_exact_duplicate_rows(self):
        from scripts.repair_price_gaps_bhavcopy import deduplicate_price_rows

        frame = pd.DataFrame([
            {"date": "2024-01-02", "symbol": "ABC", "series": "EQ", "close": 10},
            {"date": "2024-01-02", "symbol": "ABC", "series": "EQ", "close": 10},
            {"date": "2024-01-02", "symbol": "ABC", "series": "EQ", "close": 11},
            {"date": "2024-01-02", "symbol": "ABC", "series": "BE", "close": 10},
        ])
        result = deduplicate_price_rows(frame)
        self.assertEqual(len(result), 3)
        self.assertEqual(set(result["close"]), {10, 11})


if __name__ == "__main__":
    unittest.main()
