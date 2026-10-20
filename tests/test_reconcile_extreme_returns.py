import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class ReconcileExtremeReturnsTests(unittest.TestCase):
    def test_parsed_action_factor_is_not_rejected_for_ex_date_market_move(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            extremes = temp / "extremes.csv"
            actions = temp / "actions.csv"
            output = temp / "reconciliation.csv"

            # A 1:1 bonus implies a 2x share-count factor. The observed close
            # ratio differs by >8% because the stock also falls on the ex-date.
            # The inferred action factor remains 2x; the residual market return
            # is -10%, not a corporate-action ratio error.
            pd.DataFrame([{
                "canonical_symbol": "TESTCO",
                "date": "2024-01-10",
                "prev_close": 100.0,
                "close": 45.0,
                "return": -0.55,
            }]).to_csv(extremes, index=False)
            pd.DataFrame([{
                "symbol": "TESTCO",
                "ex_date": "2024-01-10",
                "purpose": "Bonus 1:1",
                "rec_date": "2024-01-11",
                "face_val": "10",
            }]).to_csv(actions, index=False)

            completed = subprocess.run([
                sys.executable,
                str(repo_root / "scripts" / "reconcile_extreme_returns.py"),
                "--extremes", str(extremes),
                "--actions", str(actions),
                "--out", str(output),
                "--supplemental-actions", str(temp / "no-manual-actions.csv"),
                "--symbol-map-supplement", str(temp / "no-symbol-map.csv"),
            ], cwd=repo_root, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr + "\n" + completed.stdout)

            result = pd.read_csv(output).iloc[0]
            self.assertEqual(result["status"], "ACTION_FACTOR_IDENTIFIED")
            self.assertAlmostEqual(float(result["inferred_factor"]), 2.0)
            self.assertGreater(float(result["factor_error"]), 0.08)
            self.assertAlmostEqual(float(result["factor_adjusted_return"]), -0.10, places=6)
            self.assertTrue(pd.isna(result["nearby_action_date"]))


    def test_nearby_action_is_reported_without_becoming_exact_match(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            extremes = temp / "extremes.csv"
            actions = temp / "actions.csv"
            output = temp / "reconciliation.csv"

            pd.DataFrame([{
                "canonical_symbol": "TESTCO",
                "date": "2024-01-10",
                "prev_close": 100.0,
                "close": 45.0,
                "return": -0.55,
            }]).to_csv(extremes, index=False)
            pd.DataFrame([{
                "symbol": "TESTCO",
                "ex_date": "2024-01-11",
                "purpose": "Bonus 1:1",
                "rec_date": "2024-01-11",
                "face_val": "10",
            }]).to_csv(actions, index=False)

            completed = subprocess.run([
                sys.executable,
                str(repo_root / "scripts" / "reconcile_extreme_returns.py"),
                "--extremes", str(extremes),
                "--actions", str(actions),
                "--out", str(output),
                "--supplemental-actions", str(temp / "no-manual-actions.csv"),
                "--symbol-map-supplement", str(temp / "no-symbol-map.csv"),
            ], cwd=repo_root, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr + "\n" + completed.stdout)

            result = pd.read_csv(output).iloc[0]
            self.assertEqual(result["status"], "NO_EXACT_ACTION")
            self.assertEqual(result["nearby_action_date"], "2024-01-11")
            self.assertEqual(int(result["nearby_action_distance_days"]), 1)
            self.assertEqual(result["nearby_action_class"], "BONUS")
            self.assertAlmostEqual(float(result["nearby_action_factor"]), 2.0)


    def test_verified_listing_day_disposition_overrides_no_exact_action(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            extremes = temp / "extremes.csv"
            actions = temp / "actions.csv"
            verified = temp / "verified_events.csv"
            output = temp / "reconciliation.csv"

            pd.DataFrame([{
                "canonical_symbol": "TESTIPO",
                "date": "2024-01-10",
                "prev_close": 100.0,
                "close": 150.0,
                "return": 0.50,
            }]).to_csv(extremes, index=False)
            pd.DataFrame(columns=["symbol", "ex_date", "purpose"]).to_csv(actions, index=False)
            pd.DataFrame([{
                "symbol": "TESTIPO",
                "event_date": "2024-01-10",
                "event_type": "IPO_LISTING_DAY",
                "treatment": "exclude_listing_session_return_from_daily_returns",
                "source": "https://www.nseindia.com/get-quotes/equity?symbol=TESTIPO",
                "confidence": "high",
                "notes": "Listing-session reference-price gain is not a close-to-close daily return.",
            }]).to_csv(verified, index=False)

            completed = subprocess.run([
                sys.executable,
                str(repo_root / "scripts" / "reconcile_extreme_returns.py"),
                "--extremes", str(extremes),
                "--actions", str(actions),
                "--out", str(output),
                "--verified-events", str(verified),
                "--supplemental-actions", str(temp / "no-manual-actions.csv"),
                "--symbol-map", str(temp / "no-symbol-map.csv"),
                "--symbol-map-supplement", str(temp / "no-symbol-map-supplement.csv"),
            ], cwd=repo_root, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr + "\n" + completed.stdout)

            result = pd.read_csv(output).iloc[0]
            self.assertEqual(result["status"], "LISTING_DAY_PRICE_DISCOVERY")
            self.assertEqual(result["event_class"], "IPO_LISTING")
            self.assertEqual(result["verified_event_type"], "IPO_LISTING_DAY")
            self.assertIn("TESTIPO", result["verified_event_source"])

    def test_historical_symbol_alias_matches_manual_split_action_without_double_count(self):
        repo_root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            extremes = temp / "extremes.csv"
            actions = temp / "actions.csv"
            manual = temp / "manual_actions.csv"
            output = temp / "reconciliation.csv"

            pd.DataFrame([{
                "canonical_symbol": "IPAPPM",
                "date": "2024-09-11",
                "prev_close": 586.45,
                "close": 110.40,
                "return": 110.40 / 586.45 - 1,
            }]).to_csv(extremes, index=False)
            # Include a purpose column as the real NSE response does; the
            # matched event row is blank and must fall back row-wise to the
            # manual subject field.
            pd.DataFrame([
                {"symbol": "UNRELATED", "ex_date": "2024-01-02", "purpose": "Dividend"},
                {"symbol": "ANDHRAPAP", "ex_date": "2024-09-11", "purpose": ""},
            ]).to_csv(actions, index=False)
            pd.DataFrame([{
                "symbol": "IPAPPM",
                "ex_date": "2024-09-11",
                "subject": "Face Value Split From Rs 10 to Rs 2",
                "inferred_factor": 5.0,
                "action_type": "split",
                "source": "NSE Circular CML63530",
                "confidence": "high",
            }]).to_csv(manual, index=False)

            completed = subprocess.run([
                sys.executable,
                str(repo_root / "scripts" / "reconcile_extreme_returns.py"),
                "--extremes", str(extremes),
                "--actions", str(actions),
                "--out", str(output),
                "--supplemental-actions", str(manual),
                "--symbol-map", str(repo_root / "data" / "input" / "verified_symbol_map.csv"),
                "--symbol-map-supplement", str(repo_root / "data" / "reference" / "nse_historical_symbol_changes.csv"),
            ], cwd=repo_root, check=False, capture_output=True, text=True)
            self.assertEqual(completed.returncode, 0, completed.stderr + "\n" + completed.stdout)

            result = pd.read_csv(output).iloc[0]
            self.assertEqual(result["status"], "ACTION_FACTOR_IDENTIFIED")
            self.assertAlmostEqual(float(result["inferred_factor"]), 5.0)
            self.assertAlmostEqual(float(result["factor_adjusted_return"]), 110.40 * 5.0 / 586.45 - 1, places=6)
            self.assertEqual(result["verified_event_type"], "SPLIT")
            self.assertEqual(result["verified_event_treatment"], "back_adjust_5x")
            self.assertEqual(result["event_class"], "SPLIT_OR_CONSOLIDATION")


if __name__ == "__main__":
    unittest.main()
