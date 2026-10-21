import unittest
import numpy as np
import pandas as pd
from scripts.run_fluidq_backtest import fill_verified_no_trade_prices

class VerifiedNoTradePriceFillTests(unittest.TestCase):
    def test_only_verified_no_trade_cells_are_filled(self):
        idx = pd.date_range('2024-01-01', periods=4)
        prices = pd.DataFrame({'AAA': [10.0, np.nan, np.nan, 13.0], 'BBB': [20.0, np.nan, 22.0, 23.0]}, index=idx)
        verified = pd.DataFrame({'AAA': [False, True, False, False], 'BBB': [False, False, False, False]}, index=idx)
        filled, count = fill_verified_no_trade_prices(prices, verified)
        self.assertEqual(filled.loc[idx[1], 'AAA'], 10.0)
        self.assertTrue(pd.isna(filled.loc[idx[2], 'AAA']))
        self.assertTrue(pd.isna(filled.loc[idx[1], 'BBB']))
        self.assertEqual(count, 1)

    def test_misaligned_mask_fails_closed(self):
        prices = pd.DataFrame({'AAA': [10.0, np.nan]}, index=pd.date_range('2024-01-01', periods=2))
        verified = pd.DataFrame({'AAA': [True]}, index=pd.date_range('2024-01-01', periods=1))
        with self.assertRaises(ValueError):
            fill_verified_no_trade_prices(prices, verified)

if __name__ == '__main__':
    unittest.main()
