import unittest
from datetime import date

import pandas as pd

from scripts.repair_price_gaps_bhavcopy import parse_archive
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


if __name__ == "__main__":
    unittest.main()
