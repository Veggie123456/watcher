import unittest
import numpy as np
import pandas as pd

from indicators import add_indicators


class IndicatorTests(unittest.TestCase):
    def test_indicators_are_created(self):
        n = 120
        close = np.linspace(100, 120, n)
        df = pd.DataFrame({
            "Open": close - 0.2,
            "High": close + 0.5,
            "Low": close - 0.5,
            "Close": close,
            "Volume": np.linspace(1000, 1800, n),
        })
        out = add_indicators(df)
        for col in ["EMA9", "EMA21", "RSI14", "ATR14", "VWAP", "MOM5", "VOL_Z", "HH20", "LL20"]:
            self.assertIn(col, out.columns)
        self.assertGreater(out["EMA9"].iloc[-1], out["EMA21"].iloc[-1])
        self.assertGreater(out["RSI14"].iloc[-1], 50)
        self.assertGreater(out["ATR14"].iloc[-1], 0)


if __name__ == "__main__":
    unittest.main()
