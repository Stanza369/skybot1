import os
import sys

import pandas as pd

# Ensure repo root is on sys.path for local test runs
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from strategy_engine import StrategyEngine



class DummyAI:
    def predict(self, df):
        return {"direction": "BULLISH", "confidence": 0.8}


class DummySMC:
    pass


class DummyLiquidity:
    def detect_liquidity_sweep(self, df_tail):
        return {"sweep_detected": False}

    def calculate_insta_flow(self, df):
        return 0.6


class DummyDataCollector:
    def compute_features(self, df):
        # StrategyEngine.compute_features expects `atr`, `volume_ratio`, etc.
        # Provide minimal columns needed.
        df = df.copy()
        df["atr"] = 2.0
        df["atr_surge"] = 2.0
        df["volume_ratio"] = 2.0
        df["volume_trend"] = 1.0
        return df

    def get_rates(self, timeframe, count):
        # Return bullish close series
        idx = pd.date_range("2024-01-01", periods=30, freq="min")

        df = pd.DataFrame({"close": [1.0 + i * 0.01 for i in range(len(idx))]})
        df.index = idx
        return df


class DummyConfig:
    TIMEFRAMES = {"M1": 1, "M5": 5, "M15": 15, "H1": 60}
    MIN_ATR_SURGE = 1.5


def test_generate_signal_returns_buy_when_conditions_match():
    config = DummyConfig()
    engine = StrategyEngine(config, DummyAI(), DummySMC(), DummyLiquidity())

    dc = DummyDataCollector()

    idx = pd.date_range("2024-01-01", periods=60, freq="min")

    df = pd.DataFrame(
        {
            "open": [1.0 for _ in range(len(idx))],
            "high": [1.0 for _ in range(len(idx))],
            "low": [1.0 for _ in range(len(idx))],
            "close": [1.0 + i * 0.001 for i in range(len(idx))],
            "tick_volume": [100 for _ in range(len(idx))],
        },
        index=idx,
    )

    sig = engine.generate_signal(df, dc)
    assert sig["signal"] in ("BUY", "NEUTRAL", "SELL")

    # In our dummy setup, it should be BUY most of the time.
    assert sig["signal"] == "BUY"

