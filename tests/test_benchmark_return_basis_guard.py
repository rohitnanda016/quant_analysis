import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "compare_fluidq_benchmark.py"
SPEC = importlib.util.spec_from_file_location("compare_fluidq_benchmark", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class TestBenchmarkReturnBasisGuard(unittest.TestCase):
    def test_tri_comparison_is_blocked_for_price_return_strategy(self):
        dates = pd.bdate_range("2020-01-01", periods=1100)
        portfolio = pd.DataFrame({
            "date": dates,
            "ret": np.full(len(dates), 0.001),
            "signal_date": dates,
        })
        signals = pd.DataFrame({"date": dates, "exposure": np.ones(len(dates))})
        tri = pd.DataFrame({
            "date": dates,
            "value": 1000.0 * (1.0005 ** np.arange(len(dates))),
        })

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            portfolio_path = root / "portfolio.csv"
            signals_path = root / "signals.csv"
            outdir = root / "out"
            portfolio.to_csv(portfolio_path, index=False)
            signals.to_csv(signals_path, index=False)
            argv = [
                "compare_fluidq_benchmark.py",
                "--portfolio", str(portfolio_path),
                "--signals", str(signals_path),
                "--outdir", str(outdir),
            ]
            with patch.object(sys, "argv", argv), patch.object(MODULE, "fetch_tri", return_value=tri):
                MODULE.main()

            result = json.loads((outdir / "benchmark_comparison.json").read_text())
            daily = pd.read_csv(outdir / "benchmark_daily_comparison.csv")
            self.assertEqual(result["comparison_status"], "BLOCKED_RETURN_BASIS_MISMATCH")
            self.assertFalse(result["comparison_allowed"])
            self.assertIsNone(result["daily_active_return_stats"])
            self.assertIsNone(result["regime_matched_nifty500"])
            self.assertIsNone(result["fluidq_minus_full_benchmark_cagr"])
            self.assertIsNone(result["fluidq_minus_regime_matched_cagr"])
            self.assertTrue(daily["matched_bench_ret"].isna().all())


if __name__ == "__main__":
    unittest.main()
