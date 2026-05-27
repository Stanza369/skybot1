import pandas as pd
from typing import Dict, List


class SMCDetector:
    def __init__(self):
        self.order_blocks: List[Dict] = []
        self.fair_value_gaps: List[Dict] = []
        self.bos_points: List[Dict] = []

    def detect_order_blocks(self, df: pd.DataFrame) -> List[Dict]:
        order_blocks = []
        for i in range(1, len(df) - 1):
            candle = df.iloc[i]
            prev_candle = df.iloc[i - 1]
            next_candle = df.iloc[i + 1]

            if (
                prev_candle["close"] < prev_candle["open"]
                and candle["close"] > candle["open"]
                and candle["body"] > candle["high_low_ratio"] * 2
            ):
                order_blocks.append(
                    {
                        "type": "BULLISH",
                        "price": float(candle["low"]),
                        "time": df.index[i],
                        "strength": float(candle["body"]) / float(candle["high_low_ratio"]),
                    }
                )
            elif (
                prev_candle["close"] > prev_candle["open"]
                and candle["close"] < candle["open"]
                and candle["body"] > candle["high_low_ratio"] * 2
            ):
                order_blocks.append(
                    {
                        "type": "BEARISH",
                        "price": float(candle["high"]),
                        "time": df.index[i],
                        "strength": float(candle["body"]) / float(candle["high_low_ratio"]),
                    }
                )
        return order_blocks

    def detect_fair_value_gaps(self, df: pd.DataFrame) -> List[Dict]:
        fvgs = []
        for i in range(2, len(df)):
            prev_prev = df.iloc[i - 2]
            prev = df.iloc[i - 1]
            curr = df.iloc[i]

            if prev["low"] > curr["high"]:
                fvgs.append(
                    {
                        "type": "BULLISH",
                        "upper": float(prev["low"]),
                        "lower": float(curr["high"]),
                        "time": df.index[i],
                        "size": float(prev["low"] - curr["high"]),
                    }
                )
            elif prev["high"] < curr["low"]:
                fvgs.append(
                    {
                        "type": "BEARISH",
                        "upper": float(curr["low"]),
                        "lower": float(prev["high"]),
                        "time": df.index[i],
                        "size": float(curr["low"] - prev["high"]),
                    }
                )
        return fvgs

    def detect_break_of_structure(self, df: pd.DataFrame, lookback: int = 20) -> List[Dict]:
        bos_points = []
        highs = df["high"].rolling(lookback, center=True).max()
        lows = df["low"].rolling(lookback, center=True).min()

        prev_high = None
        prev_low = None

        for i in range(lookback, len(df) - lookback):
            current_high = highs.iloc[i]
            current_low = lows.iloc[i]

            if prev_high is not None and current_high > prev_high:
                bos_points.append(
                    {"type": "BULLISH_BOS", "price": float(current_high), "time": df.index[i]}
                )
            if prev_low is not None and current_low < prev_low:
                bos_points.append(
                    {"type": "BEARISH_BOS", "price": float(current_low), "time": df.index[i]}
                )

            prev_high = current_high
            prev_low = current_low

        return bos_points

    def analyze_market_structure(self, df: pd.DataFrame) -> Dict:
        return {
            "order_blocks": self.detect_order_blocks(df),
            "fair_value_gaps": self.detect_fair_value_gaps(df),
            "break_of_structure": self.detect_break_of_structure(df),
        }

