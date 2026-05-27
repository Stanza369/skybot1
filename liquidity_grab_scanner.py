from typing import Any, Dict, List, Optional, Tuple

import pandas as pd


class LiquidityGrabScanner:
    """ICT-style liquidity grab (stop-hunt) scanner.

    This module is intentionally heuristic (no external data needed) and is designed
    to plug into the existing repo's strategy engine.

    Expected DataFrame columns: open, high, low, close (indexable with iloc)
    """

    def __init__(self, data: pd.DataFrame):
        self.data = data

    def _find_swing_points(self, *, period: int = 5) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        df = self.data
        if df is None or len(df) < (period * 2 + 3):
            return [], []

        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)

        swing_highs: List[Dict[str, Any]] = []
        swing_lows: List[Dict[str, Any]] = []

        for i in range(period, len(df) - period):
            window_high = highs[i - period : i + period + 1]
            window_low = lows[i - period : i + period + 1]

            if highs[i] == window_high.max():
                swing_highs.append({"price": float(highs[i]), "index": i, "time": df.index[i]})
            if lows[i] == window_low.min():
                swing_lows.append({"price": float(lows[i]), "index": i, "time": df.index[i]})

        return swing_highs, swing_lows

    def detect_liquidity_grab(self, *, current_price: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """Return grab dict or None.

        BUY_SIDE_GRAB  -> price swept below (sell-side) and reversed up.
        SELL_SIDE_GRAB -> price swept above (buy-side) and reversed down.

        Output format examples:
            {"type":"BUY_SIDE_GRAB","grabbed_level": recent_low, "strength":"HIGH"}
            {"type":"SELL_SIDE_GRAB","grabbed_level": recent_high, "strength":"HIGH"}
        """
        df = self.data
        if df is None or len(df) < 10:
            return None

        last = df.iloc[-1]
        prev = df.iloc[-2]

        if current_price is None:
            current_price = float(last["close"])

        swing_highs, swing_lows = self._find_swing_points(period=5)
        if not swing_highs or not swing_lows:
            return None

        # Use recent swings (last 3) as candidate stop clusters
        recent_high = max(h["price"] for h in swing_highs[-3:])
        recent_low = min(l["price"] for l in swing_lows[-3:])

        last_high = float(last["high"])
        last_low = float(last["low"])
        last_close = float(last["close"])
        prev_close = float(prev["close"])

        # Sell-side grab after buy-side sweep: sweep above recent_high then close back below
        if last_high > float(recent_high) and last_close < float(recent_high) and last_close < prev_close:
            return {
                "type": "SELL_SIDE_GRAB",
                "grabbed_level": float(recent_high),
                "strength": "HIGH",
            }

        # Buy-side grab after sell-side sweep: sweep below recent_low then close back above
        if last_low < float(recent_low) and last_close > float(recent_low) and last_close > prev_close:
            return {
                "type": "BUY_SIDE_GRAB",
                "grabbed_level": float(recent_low),
                "strength": "HIGH",
            }

        return None

