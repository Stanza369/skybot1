import pandas as pd
from typing import Dict, List, Optional, Any


class FVGDetector:
    """Fair Value Gap (FVG) detector (ICT concept).

    Implementation notes:
    - Works on OHLCV DataFrame with columns: open, high, low, close
    - Detects classical 3-candle imbalances:
        Bullish FVG: candle3.low > candle1.high
        Bearish FVG: candle3.high < candle1.low
    - Returns zones defined by (bottom, top).
    """

    def __init__(self, data: pd.DataFrame):
        self.data = data

    def find_fvgs(self) -> List[Dict[str, Any]]:
        df = self.data
        if df is None or len(df) < 3:
            return []

        # Ensure we can index by iloc
        cols = {c: c.lower() for c in df.columns}
        # Assume caller already lowercases columns in their pipeline.

        fvgs: List[Dict[str, Any]] = []
        for i in range(len(df) - 2):
            c1 = df.iloc[i]
            c2 = df.iloc[i + 1]
            c3 = df.iloc[i + 2]

            # Bullish FVG: gap between c1 high and c3 low
            if float(c3["low"]) > float(c1["high"]):
                fvgs.append(
                    {
                        "type": "BULLISH",
                        "top": float(c3["low"]),
                        "bottom": float(c1["high"]),
                        "index": i,
                        # Placeholder strength; ICT usually uses displacement context
                        "strength": "STRONG",
                    }
                )

            # Bearish FVG: gap between c1 low and c3 high
            elif float(c3["high"]) < float(c1["low"]):
                fvgs.append(
                    {
                        "type": "BEARISH",
                        "top": float(c1["low"]),
                        "bottom": float(c3["high"]),
                        "index": i,
                        "strength": "STRONG",
                    }
                )

        return fvgs

    def is_price_in_fvg(self, price: float, fvg: Dict[str, Any]) -> bool:
        if fvg.get("type") == "BULLISH":
            return float(fvg["bottom"]) <= float(price) <= float(fvg["top"])
        return float(fvg["top"]) <= float(price) <= float(fvg["bottom"])

    def get_nearest_fvg(self, current_price: float, *, max_distance: float = 0.0020) -> Optional[Dict[str, Any]]:
        fvgs = self.find_fvgs()
        if not fvgs:
            return None

        # Distance measured to zone boundary (bottom for bullish, top for bearish)
        def dist_to_zone(z: Dict[str, Any]) -> float:
            if z.get("type") == "BULLISH":
                return abs(float(current_price) - float(z["bottom"]))
            return abs(float(current_price) - float(z["top"]))

        nearest = min(fvgs, key=dist_to_zone)
        if dist_to_zone(nearest) < max_distance:
            return nearest
        return None

