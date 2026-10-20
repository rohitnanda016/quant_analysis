import unittest
import pandas as pd

from scripts.run_fluidq_backtest import mask_unresolved_corporate_event_windows


class CorporateEventFeatureMaskTests(unittest.TestCase):
    def make_prices(self, symbol, count):
        return pd.DataFrame({
            "symbol": [symbol] * count,
            "date": pd.date_range("2024-01-01", periods=count, freq="D"),
            "ret_6m": [0.20] * count,
            "ret_12m_ex1m": [0.30] * count,
            "dma200": [100.0] * count,
            "trend": [0.10] * count,
            "vol126": [0.25] * count,
        })

    def test_event_blackout_masks_only_feature_windows_affected_by_event(self):
        prices = pd.concat([
            self.make_prices("TESTCO", 350),
            self.make_prices("OTHER", 350),
        ], ignore_index=True)
        event_date = pd.Timestamp("2024-01-11")  # TESTCO row index 10
        events = pd.DataFrame([{
            "symbol": "TESTCO",
            "event_date": event_date,
            "treatment": "corporate_event",
        }])

        masked, counts = mask_unresolved_corporate_event_windows(prices, events)
        testco = masked[masked.symbol.eq("TESTCO")].reset_index(drop=True)
        other = masked[masked.symbol.eq("OTHER")].reset_index(drop=True)

        self.assertTrue(testco.loc[10:135, "ret_6m"].isna().all())
        self.assertFalse(pd.isna(testco.loc[136, "ret_6m"]))
        self.assertTrue(testco.loc[31:261, "ret_12m_ex1m"].isna().all())
        self.assertFalse(pd.isna(testco.loc[262, "ret_12m_ex1m"]))
        self.assertTrue(testco.loc[10:209, "dma200"].isna().all())
        self.assertTrue(testco.loc[10:209, "trend"].isna().all())
        self.assertFalse(pd.isna(testco.loc[210, "trend"]))
        self.assertTrue(testco.loc[10:135, "vol126"].isna().all())
        self.assertFalse(pd.isna(testco.loc[136, "vol126"]))

        self.assertTrue(other["ret_6m"].notna().all())
        self.assertTrue(other["ret_12m_ex1m"].notna().all())
        self.assertTrue(other["dma200"].notna().all())
        self.assertEqual(counts["ret_6m_rows_masked"], 126)
        self.assertEqual(counts["ret_12m_ex1m_rows_masked"], 231)
        self.assertEqual(counts["dma200_rows_masked"], 200)
        self.assertEqual(counts["trend_rows_masked"], 200)
        self.assertEqual(counts["vol126_rows_masked"], 126)

    def test_no_corporate_event_preserves_features(self):
        prices = self.make_prices("TESTCO", 20)
        events = pd.DataFrame([{
            "symbol": "OTHER",
            "event_date": pd.Timestamp("2024-01-05"),
            "treatment": "corporate_event",
        }])

        masked, counts = mask_unresolved_corporate_event_windows(prices, events)

        pd.testing.assert_series_equal(masked["ret_6m"], prices["ret_6m"])
        pd.testing.assert_series_equal(masked["trend"], prices["trend"])
        self.assertTrue(all(value == 0 for value in counts.values()))

    def test_empty_event_table_is_safe(self):
        prices = self.make_prices("TESTCO", 20)
        events = pd.DataFrame(columns=["symbol", "event_date", "treatment"])

        masked, counts = mask_unresolved_corporate_event_windows(prices, events)

        pd.testing.assert_frame_equal(masked, prices)
        self.assertTrue(all(value == 0 for value in counts.values()))


if __name__ == "__main__":
    unittest.main()
