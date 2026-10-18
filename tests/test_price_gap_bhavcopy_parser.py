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
    exchange_symbol,
    absences_requiring_replay,
    exclude_verified_no_trade_absences,
)
from scripts.membership_scope import (
    build_membership_session_windows,
    in_membership_research_window,
)
from scripts.audit_price_gap_readiness import accounting_summary
from scripts.run_fluidq_backtest import (
    load_membership, normalize_price_series, eq_tradable_rows, prepare_price_identity,
)
from scripts.symbol_lineage import load_symbol_rename_rows, symbol_map_fingerprint
from scripts.repair_missing_pairs_security_history import parse_security_history, classify_target_date, select_target_probe


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

    def test_security_history_parser_uses_requested_symbol_when_nse_omits_symbol_column(self):
        csv = (
            '"CH_SERIES","CH_TIMESTAMP","CH_PREVIOUS_CLS","CH_OPENING_PRICE",'
            '"CH_TRADE_HIGH_PRICE","CH_TRADE_LOW_PRICE","CH_LAST_TRADED_PRICE",'
            '"CH_CLOSING_PRICE","CH_TOT_TRADED_QTY"\n'
            '"EQ","07-May-2014","100","100","102","99","101","101","1000"\n'
            '"EQ","09-May-2014","101","101","103","100","102","102","1100"\n'
        )
        history = parse_security_history(csv, requested_symbol="DYNAMATECH")
        self.assertEqual(set(history["symbol"]), {"DYNAMATECH"})
        self.assertEqual(set(history["series"]), {"EQ"})
        outcome, exact = classify_target_date(history, "2014-05-08")
        self.assertEqual(outcome, "verified_no_trade")
        self.assertTrue(exact.empty)

    def test_security_history_parser_accepts_json_camel_case_with_symbol(self):
        payload = json.dumps({"data": [
            {"CH_SYMBOL": "MAHSCOOTER", "CH_SERIES": "EQ", "CH_TIMESTAMP": "28-Oct-2024",
             "CH_CLOSING_PRICE": "10050", "CH_TOT_TRADED_QTY": "1500"},
            {"CH_SYMBOL": "MAHSCOOTER", "CH_SERIES": "EQ", "CH_TIMESTAMP": "31-Oct-2024",
             "CH_CLOSING_PRICE": "10100", "CH_TOT_TRADED_QTY": "1700"},
        ]})
        history = parse_security_history(payload)
        self.assertEqual(len(history), 2)
        self.assertEqual(set(history["symbol"]), {"MAHSCOOTER"})
        self.assertEqual(list(history["date"].dt.strftime("%Y-%m-%d")), ["2024-10-28", "2024-10-31"])
        self.assertEqual(list(history["close"]), [10050.0, 10100.0])

    def test_security_history_timezone_stamps_compare_by_exchange_calendar_date(self):
        payload = json.dumps({"data": [
            {"CH_SYMBOL": "MAHSCOOTER", "CH_SERIES": "EQ",
             "CH_TIMESTAMP": "2024-10-27T18:30:00.000Z",
             "CH_CLOSING_PRICE": "10600", "CH_TOT_TRADED_QTY": "1000"},
            {"CH_SYMBOL": "MAHSCOOTER", "CH_SERIES": "EQ",
             "CH_TIMESTAMP": "2024-10-29T18:30:00.000Z",
             "CH_CLOSING_PRICE": "10650", "CH_TOT_TRADED_QTY": "1100"},
        ]})
        history = parse_security_history(payload)
        outcome, exact = classify_target_date(history, "2024-10-29")
        self.assertEqual(outcome, "verified_no_trade")
        self.assertTrue(exact.empty)

    def test_security_history_probe_prefers_price_in_alternate_series_over_no_trade_candidate(self):
        eq = parse_security_history(
            '"CH_SERIES","CH_TIMESTAMP","CH_CLOSING_PRICE"\n'
            '"EQ","25-Oct-2024","10888.10"\n'
            '"EQ","29-Oct-2024","10355.00"',
            requested_symbol="MAHSCOOTER",
        )
        be = parse_security_history(
            '"CH_SERIES","CH_TIMESTAMP","CH_CLOSING_PRICE"\n'
            '"BE","28-Oct-2024","10689.80"',
            requested_symbol="MAHSCOOTER",
        )
        probes = [
            {"url": "eq-no-trade", "history": eq, "radius_days": 3},
            {"url": "be-price", "history": be, "radius_days": 1},
        ]
        selected, outcome, exact = select_target_probe(probes, "2024-10-28")
        self.assertEqual(outcome, "observed_price")
        self.assertEqual(selected["url"], "be-price")
        self.assertEqual(exact["series"].iloc[0], "BE")

    def test_security_history_probe_rejects_rows_outside_requested_window(self):
        inconsistent_json = parse_security_history(
            '"CH_SERIES","CH_TIMESTAMP","CH_CLOSING_PRICE"\n'
            '"BE","06-Apr-2014","100"\n'
            '"BE","06-May-2014","101"\n'
            '"BE","06-Jun-2014","102"',
            requested_symbol="DYNAMATECH",
        )
        selected, outcome, _ = select_target_probe(
            [{"url": "out-of-range-json", "history": inconsistent_json,
              "radius_days": 1}],
            "2014-05-08",
        )
        self.assertEqual(outcome, "unverified_out_of_range_dates")
        self.assertEqual(selected["url"], "out-of-range-json")

    def test_security_history_parser_fails_closed_on_json_without_date_series_close(self):
        payload = json.dumps({"data": [{"CH_SYMBOL": "MAHSCOOTER", "CH_SERIES": "EQ"}]})
        with self.assertRaises(ValueError):
            parse_security_history(payload, requested_symbol="MAHSCOOTER")

    def test_security_history_parser_rejects_empty_json_rows_for_no_trade(self):
        payload = json.dumps({"data": []})
        history = parse_security_history(payload, requested_symbol="DYNAMATECH")
        outcome, _ = classify_target_date(history, "2014-05-08")
        self.assertEqual(outcome, "unverified")

    def test_security_history_parser_requires_trading_sessions_around_no_trade_date(self):
        csv = (
            '"Symbol  ","Series  ","Date  ","Prev Close  ","Open Price  ","High Price  ","Low Price  ","'
            'Last Price  ","Close Price  ","Average Price ","Total Traded Quantity  ","Turnover ₹","No. of Trades"\n'
            '"DYNAMATECH","EQ","07-May-2014","100","100","102","99","101","101","100.5","1000","100500","25"\n'
            '"DYNAMATECH","EQ","09-May-2014","101","101","103","100","102","102","101.5","1100","111650","30"\n'
        )
        history = parse_security_history(csv)
        outcome, exact = classify_target_date(history, "2014-05-08")
        self.assertEqual(outcome, "verified_no_trade")
        self.assertTrue(exact.empty)
        before_only = history.loc[history["date"].lt(pd.Timestamp("2014-05-08"))]
        outcome, _ = classify_target_date(before_only, "2014-05-08")
        self.assertEqual(outcome, "unverified")

    def test_truncated_nse_history_does_not_block_narrower_bracketing_probe(self):
        partial = parse_security_history(
            '"CH_SERIES","CH_TIMESTAMP","CH_CLOSING_PRICE"\n'
            '"EQ","07-May-2014","101"',
            requested_symbol="DYNAMATECH",
        )
        bracketed = parse_security_history(
            '"CH_SERIES","CH_TIMESTAMP","CH_CLOSING_PRICE"\n'
            '"EQ","07-May-2014","101"\n'
            '"EQ","09-May-2014","102"',
            requested_symbol="DYNAMATECH",
        )
        probes = [
            {"url": "broad-window", "history": partial, "radius_days": 5},
            {"url": "narrow-window", "history": bracketed, "radius_days": 1},
        ]

        selected, outcome, exact = select_target_probe(probes, "2014-05-08")

        self.assertEqual(outcome, "verified_no_trade")
        self.assertEqual(selected["url"], "narrow-window")
        self.assertTrue(exact.empty)

    def test_broad_bracketing_response_is_not_enough_to_verify_no_trade(self):
        broad = parse_security_history(
            '"CH_SERIES","CH_TIMESTAMP","CH_CLOSING_PRICE"\n'
            '"EQ","25-Oct-2024","10888.10"\n'
            '"EQ","29-Oct-2024","10355.00"',
            requested_symbol="MAHSCOOTER",
        )
        narrow = parse_security_history(
            '"CH_SERIES","CH_TIMESTAMP","CH_CLOSING_PRICE"\n'
            '"EQ","25-Oct-2024","10888.10"\n'
            '"EQ","29-Oct-2024","10355.00"',
            requested_symbol="MAHSCOOTER",
        )
        probes = [
            {"url": "broad-window", "history": broad, "radius_days": 5},
            {"url": "narrow-window", "history": narrow, "radius_days": 3},
        ]

        selected, outcome, exact = select_target_probe(probes, "2024-10-28")

        self.assertEqual(outcome, "verified_no_trade")
        self.assertEqual(selected["url"], "narrow-window")
        self.assertTrue(exact.empty)

    def test_security_history_target_row_with_blank_close_is_not_no_trade(self):
        csv = (
            '"Symbol  ","Series  ","Date  ","Prev Close  ","Open Price  ","High Price  ","Low Price  ","'
            'Last Price  ","Close Price  ","Average Price ","Total Traded Quantity  ","Turnover ₹","No. of Trades"\n'
            '"DYNAMATECH","EQ","07-May-2014","100","100","102","99","101","101","100.5","1000","100500","25"\n'
            '"DYNAMATECH","EQ","08-May-2014","101","","","","","","","","",""\n'
            '"DYNAMATECH","EQ","09-May-2014","101","101","103","100","102","102","101.5","1100","111650","30"\n'
        )
        history = parse_security_history(csv)
        outcome, _ = classify_target_date(history, "2014-05-08")
        self.assertEqual(outcome, "unverified_target_row_without_valid_close")

    def test_security_history_exact_date_is_an_observed_price(self):
        csv = (
            '"Symbol  ","Series  ","Date  ","Prev Close  ","Open Price  ","High Price  ","Low Price  ","'
            'Last Price  ","Close Price  ","Average Price ","Total Traded Quantity  ","Turnover ₹","No. of Trades"\n'
            '"MAHSCOOTER","EQ","28-Oct-2024","10000","10000","10100","9900","10050","10050","10020","1500","15030000","40"\n'
        )
        history = parse_security_history(csv)
        outcome, exact = classify_target_date(history, "2024-10-28")
        self.assertEqual(outcome, "observed_price")
        self.assertEqual(len(exact), 1)
        self.assertEqual(float(exact["close"].iloc[0]), 10050.0)

    def test_verified_no_trade_absences_are_not_double_counted(self):
        absences = [
            {"date": "2023-10-26", "symbol": "KIRLFER", "status": "unresolved_archive_absence"},
            {"date": "2023-10-27", "symbol": "KIRLFER", "status": "unresolved_archive_absence"},
            {"date": "2024-10-28", "symbol": "MAHSCOOTER", "status": "unresolved_archive_absence"},
        ]
        verified_pairs = {
            (pd.Timestamp("2023-10-26"), "KIRLFER"),
            (pd.Timestamp("2023-10-27"), "KIRLFER"),
        }
        remaining = exclude_verified_no_trade_absences(absences, verified_pairs)
        self.assertEqual([(x["date"], x["symbol"]) for x in remaining], [("2024-10-28", "MAHSCOOTER")])

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

    def test_historical_symbol_supplement_repairs_known_renames(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            base = root / "base.csv"
            supplement = root / "supplement.csv"
            pd.DataFrame([{
                "old_symbol": "IBSEC", "new_symbol": "IBVENTURES", "effective_from": "2015-04-01"
            }]).to_csv(base, index=False)
            pd.DataFrame([
                {"old_symbol": "IBVENTURES", "new_symbol": "DHANI", "effective_from": "2020-10-28"},
                {"old_symbol": "RUCHI", "new_symbol": "PATANJALI", "effective_from": "2022-07-13"},
                {"old_symbol": "SORILHOLD", "new_symbol": "IBULISL", "effective_from": "2018-06-08"},
                {"old_symbol": "IBPOW", "new_symbol": "RTNPOWER", "effective_from": "2014-11-20"},
                {"old_symbol": "PIPAVAVDOC", "new_symbol": "RDEL", "effective_from": "2016-03-18"},
                {"old_symbol": "RDEL", "new_symbol": "RNAVAL", "effective_from": "2017-09-18"},
                {"old_symbol": "STRTECH", "new_symbol": "STLTECH", "effective_from": "2020-10-29"},
                {"old_symbol": "JUBILANT", "new_symbol": "JUBLPHARMA", "effective_from": "2021-02-12"},
                {"old_symbol": "RNAVAL", "new_symbol": "SWANDEF", "effective_from": "2025-01-20"},
            ]).to_csv(supplement, index=False)
            rows = load_symbol_rename_rows(base, supplement)
            self.assertEqual(exchange_symbol("DHANI", "2018-06-13", rows), "IBVENTURES")
            self.assertEqual(exchange_symbol("PATANJALI", "2022-03-01", rows), "RUCHI")
            self.assertEqual(exchange_symbol("IBULISL", "2018-05-08", rows), "SORILHOLD")
            self.assertEqual(exchange_symbol("RTNPOWER", "2014-06-13", rows), "IBPOW")
            self.assertEqual(exchange_symbol("RNAVAL", "2014-06-16", rows), "PIPAVAVDOC")
            self.assertEqual(exchange_symbol("RNAVAL", "2016-06-15", rows), "RDEL")
            self.assertEqual(exchange_symbol("STLTECH", "2016-06-15", rows), "STRTECH")
            self.assertEqual(exchange_symbol("JUBLPHARMA", "2021-02-04", rows), "JUBILANT")
            self.assertEqual(exchange_symbol("RNAVAL", "2026-04-20", rows), "SWANDEF")
            self.assertEqual(len(symbol_map_fingerprint(rows)), 64)

            prior_absences = [
                {"date": "2018-06-13", "symbol": "DHANI", "exchange_symbol_checked": "DHANI"},
                {"date": "2022-03-01", "symbol": "PATANJALI", "exchange_symbol_checked": "PATANJALI"},
                {"date": "2014-06-16", "symbol": "RTNPOWER", "exchange_symbol_checked": "RTNPOWER"},
                {"date": "2014-06-16", "symbol": "RNAVAL", "exchange_symbol_checked": "RNAVAL"},
                {"date": "2016-06-15", "symbol": "STLTECH", "exchange_symbol_checked": "STLTECH"},
                {"date": "2021-02-04", "symbol": "JUBLPHARMA", "exchange_symbol_checked": "JUBLPHARMA"},
            ]
            self.assertEqual(
                absences_requiring_replay(prior_absences, rows),
                {
                    ("2018-06-13", "DHANI"),
                    ("2022-03-01", "PATANJALI"),
                    ("2014-06-16", "RTNPOWER"),
                    ("2014-06-16", "RNAVAL"),
                    ("2016-06-15", "STLTECH"),
                    ("2021-02-04", "JUBLPHARMA"),
                },
            )

    def test_price_identity_prefers_requested_symbol_for_repaired_old_ticker(self):
        frame = pd.DataFrame({
            "symbol": ["IBVENTURES", "DHANI"],
            "requested_symbol": ["DHANI", "DHANI"],
            "series": ["EQ", "EQ"],
            "close": [100.0, 110.0],
        })
        frame, identity_col, use_canonical = prepare_price_identity(frame)
        self.assertFalse(use_canonical)
        self.assertEqual(frame[identity_col].tolist(), ["DHANI", "DHANI"])

        canonical = pd.DataFrame({
            "symbol": ["IBVENTURES", "DHANI"],
            "requested_symbol": ["DHANI", "DHANI"],
            "canonical_symbol": [pd.NA, "DHANI"],
            "series": ["EQ", "EQ"],
        })
        canonical, identity_col, use_canonical = prepare_price_identity(canonical)
        self.assertTrue(use_canonical)
        self.assertEqual(canonical[identity_col].tolist(), ["DHANI", "DHANI"])

    def test_backtest_loads_valid_from_valid_to_membership_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "membership.csv"
            pd.DataFrame([{
                "symbol": "OLDCO",
                "canonical_symbol": "NEWCO",
                "valid_from": "2024-01-02",
                "valid_to": "2024-02-01",
            }]).to_csv(path, index=False)

            historical = load_membership(path)
            self.assertEqual(historical.loc[0, "symbol"], "OLDCO")
            self.assertEqual(historical.loc[0, "effective_date"], pd.Timestamp("2024-01-02"))
            self.assertEqual(historical.loc[0, "end_date"], pd.Timestamp("2024-02-01"))

            canonical = load_membership(path, canonical_symbols=True)
            self.assertEqual(canonical.loc[0, "symbol"], "NEWCO")

    def test_backtest_uses_be_bz_for_price_continuity_but_only_eq_for_new_entries(self):
        prices = pd.DataFrame({
            "series": ["EQ", "BE", "BZ", "E1", "SM"],
            "close": [100.0, 101.0, 99.0, 77.0, 88.0],
        })
        continuity = normalize_price_series(prices, "series")
        self.assertEqual(set(continuity["series"]), {"EQ", "BE", "BZ"})
        self.assertEqual(len(eq_tradable_rows(continuity)), 1)
        self.assertEqual(eq_tradable_rows(continuity)["series"].iloc[0], "EQ")

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


class ReferenceEvidenceLedgerTests(unittest.TestCase):
    def test_verified_no_trade_evidence_csv_has_stable_schema(self):
        path = Path("data/reference/verified_no_trade_evidence.csv")
        frame = pd.read_csv(path, low_memory=False)
        self.assertEqual(
            list(frame.columns),
            [
                "date", "symbol", "exchange_symbol_checked", "series",
                "status", "verification_source", "evidence_reference",
            ],
        )
        approved = frame[frame["status"].eq("verified_no_trade")]
        self.assertTrue(approved["verification_source"].notna().all())
        self.assertTrue(approved["evidence_reference"].notna().all())
        self.assertTrue(approved["evidence_reference"].astype(str).str.startswith("http").all())


class PriceQualityLineageTests(unittest.TestCase):
    def test_extreme_return_uses_terminal_ticker_alias(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prices = root / "prices.csv"
            outdir = root / "quality"
            pd.DataFrame([{
                "date": "2020-01-02", "symbol": "CADILAHC",
                "requested_symbol": "CADILAHC", "series": "EQ",
                "prev_close": 1000, "open": 100, "high": 110,
                "low": 90, "close": 100, "vwap": 100,
                "volume": 100, "turnover ₹": 10000,
            }]).to_csv(prices, index=False)
            subprocess.run([
                sys.executable, "scripts/audit_price_quality.py",
                "--prices", str(prices), "--outdir", str(outdir),
            ], check=True, capture_output=True, text=True)
            extremes = pd.read_csv(outdir / "extreme_returns_raw.csv")
            self.assertEqual(len(extremes), 1)
            self.assertEqual(extremes.loc[0, "canonical_symbol"], "ZYDUSLIFE")


if __name__ == "__main__":
    unittest.main()
