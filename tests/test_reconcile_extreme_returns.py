import csv
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


class ReconcileExtremeReturnsTests(unittest.TestCase):
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

            subprocess.run([
                sys.executable,
                str(repo_root / "scripts" / "reconcile_extreme_returns.py"),
                "--extremes", str(extremes),
                "--actions", str(actions),
                "--out", str(output),
                "--supplemental-actions", str(temp / "no-manual-actions.csv"),
                "--symbol-map-supplement", str(temp / "no-symbol-map.csv"),
            ], cwd=repo_root, check=True, capture_output=True, text=True)

            result = pd.read_csv(output).iloc[0]
            self.assertEqual(result["status"], "NO_EXACT_ACTION")
            self.assertEqual(result["nearby_action_date"], "2024-01-11")
            self.assertEqual(int(result["nearby_action_distance_days"]), 1)
            self.assertEqual(result["nearby_action_class"], "BONUS")
            self.assertAlmostEqual(float(result["nearby_action_factor"]), 2.0)


if __name__ == "__main__":
    unittest.main()
