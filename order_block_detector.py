from typing import Any, Dict, List, Optional

import pandas as pd


class OrderBlockDetector:
    """ICT-inspired Order Block detector.

    Simplified logic (suitable for strategy confluence):
    - Detect displacement candles using a strong body relative to recent average body.
    - The order block is the last candle before the displacement.

    DataFrame columns expected: open, high, low, close
    """

    def __init__(self, data: pd.DataFrame):
        self.data = data

    def find_order_blocks(
        self,
        *,
        displacement_body_mult: float = 1.5,
        lookback_avg_bodies: int = 50,
        max_blocks: int = 20,
    ) -> List[Dict[str, Any]]:
        df = self.data
        if df is None or len(df) < 3:
            return []

        avg_body = (
            (df["close"].astype(float).diff().abs().fillna(0)).tail(lookback_avg_bodies).mean()
        )
        avg_body = float(avg_body) if avg_body and avg_body > 0 else 0.0

        order_blocks: List[Dict[str, Any]] = []

        # Last candle before displacement at i; displacement at i+1
        for i in range(len(df) - 2):
            current = df.iloc[i]
            next_candle = df.iloc[i + 1]

            current_body = abs(float(current["close"]) - float(current["open"]))
            next_body = abs(float(next_candle["close"]) - float(next_candle["open"]))

            if avg_body <= 0:
                continue

            if next_body > avg_body * displacement_body_mult:
                # Bullish displacement -> bullish OB (the pre-displacement candle)
                if float(next_candle["close"]) > float(next_candle["open"]):
                    order_blocks.append(
                        {
                            "type": "BULLISH",
                            "high": float(current["high"]),
                            "low": float(current["low"]),
                            "entry": float(current["low"]),
                            "stop": float(current["low"]) - (float(current["high"]) - float(current["low"])),
                            "strength": "HIGH",
                        }
                    )
                # Bearish displacement -> bearish OB
                elif float(next_candle["close"]) < float(next_candle["open"]):
                    order_blocks.append(
                        {
                            "type": "BEARISH",
                            "high": float(current["high"]),
                            "low": float(current["low"]),
                            "entry": float(current["high"]),
                            "stop": float(current["high"]) + (float(current["high"]) - float(current["low"])),
                            "strength": "HIGH",
                        }
                    )

            if len(order_blocks) >= max_blocks:
                break

        return order_blocks

    def get_mitigated_order_block(
        self,
        current_price: float,
        *,
        tolerance: float = 0.0005,
        scan_last_n: int = 5,
    ) -> Optional[Dict[str, Any]]:
        blocks = self.find_order_blocks()
        if not blocks:
            return None

        # Check recent blocks for near-touch (mitigation)
        for ob in blocks[-scan_last_n:]:
            if ob["type"] == "BULLISH":
                if abs(float(current_price) - float(ob["low"])) <= tolerance:
                    return ob
            else:
                if abs(float(current_price) - float(ob["high"])) <= tolerance:
                    return ob

        return None

