import unittest
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from models import Headline
from scorer import analyze_market


class ScorerTests(unittest.TestCase):
    def make_df(self, rising=True):
        n = 120
        close = np.linspace(100, 130, n) if rising else np.linspace(130, 100, n)
        idx = pd.date_range(datetime.now(timezone.utc) - timedelta(minutes=5*(n-1)), periods=n, freq="5min")
        return pd.DataFrame({
            "Open": close - (0.1 if rising else -0.1),
            "High": close + 0.4,
            "Low": close - 0.4,
            "Close": close,
            "Volume": np.linspace(1000, 2200, n),
        }, index=idx)

    def test_rising_nq_scores_bullish(self):
        df = self.make_df(True)
        ctx = {"^TNX": -0.2, "breadth_proxy": 82.0, "DX-Y.NYB": -0.1}
        headlines = [Headline("Treasury yields fall as rate cut hopes grow", "", datetime.now(timezone.utc), impact=2.5)]
        a = analyze_market("NQ", df, ctx, headlines, [])
        self.assertGreater(a.score, 58)
        self.assertEqual(a.direction, "BULLISH")

    def test_falling_gold_with_rising_dollar_scores_bearish(self):
        df = self.make_df(False)
        ctx = {"^TNX": 0.2, "breadth_proxy": 50.0, "DX-Y.NYB": 0.2}
        headlines = [Headline("Dollar strengthens as Treasury yields rise", "", datetime.now(timezone.utc), impact=-2.0)]
        a = analyze_market("GC", df, ctx, headlines, [])
        self.assertLess(a.score, 42)
        self.assertEqual(a.direction, "BEARISH")


if __name__ == "__main__":
    unittest.main()
