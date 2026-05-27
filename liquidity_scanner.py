import pandas as pd
from typing import Dict


class LiquidityScanner:
    def __init__(self, config):
        self.config = config

    def count_touches(self, df: pd.DataFrame, price: float, window: int) -> int:
        tolerance = price * 0.0005  # 0.05%
        recent_df = df.tail(window)
        high_touches = sum(abs(recent_df["high"] - price) < tolerance)
        low_touches = sum(abs(recent_df["low"] - price) < tolerance)
        return int(high_touches + low_touches)

    def detect_liquidity_levels(self, df: pd.DataFrame, window: int = 50) -> Dict:
        highs = df["high"].rolling(window, center=True).max()
        lows = df["low"].rolling(window, center=True).min()

        liquidity_highs = []
        liquidity_lows = []

        for i in range(window, len(df) - window):
            if df["high"].iloc[i] == highs.iloc[i]:
                liquidity_highs.append(
                    {
                        "price": float(df["high"].iloc[i]),
                        "time": df.index[i],
                        "touches": self.count_touches(df, float(df["high"].iloc[i]), window),
                    }
                )
            if df["low"].iloc[i] == lows.iloc[i]:
                liquidity_lows.append(
                    {
                        "price": float(df["low"].iloc[i]),
                        "time": df.index[i],
                        "touches": self.count_touches(df, float(df["low"].iloc[i]), window),
                    }
                )

        return {"resistance": liquidity_highs, "support": liquidity_lows}

    def detect_liquidity_sweep(self, df: pd.DataFrame) -> Dict:
        if len(df) < 3:
            return {"sweep_detected": False, "sweep_type": None, "levels": {"resistance": [], "support": []}}

        liquidity_levels = self.detect_liquidity_levels(df.tail(100))

        latest_candle = df.iloc[-1]
        prev_candle = df.iloc[-2]

        sweep_detected = False
        sweep_type = None

        for resist in liquidity_levels.get("resistance", [])[:5]:
            if latest_candle["high"] > resist["price"] and prev_candle["high"] <= resist["price"]:
                sweep_detected = True
                sweep_type = "LIQUIDITY_SWEEP_HIGH"
                break

        if not sweep_detected:
            for support in liquidity_levels.get("support", [])[:5]:
                if latest_candle["low"] < support["price"] and prev_candle["low"] >= support["price"]:
                    sweep_detected = True
                    sweep_type = "LIQUIDITY_SWEEP_LOW"
                    break

        return {
            "sweep_detected": sweep_detected,
            "sweep_type": sweep_type,
            "levels": liquidity_levels,
        }

    def calculate_insta_flow(self, df: pd.DataFrame) -> float:
        if len(df) < 60:
            return 0.0
        volume_imbalance = df["tick_volume"].tail(10).mean() / max(df["tick_volume"].tail(50).mean(), 1e-9)

        # Approx delta proxy
        high_low_ratio = df["high"].replace(0, 1e-9) - df["low"].replace(0, 0)
        high_low_ratio = (df["high"] - df["low"]).replace(0, 1e-9)
        delta_proxy = ((df["close"] - df["open"]) / (high_low_ratio).rolling(20).mean()).tail(5).mean()

        return float(volume_imbalance * delta_proxy)

