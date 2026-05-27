from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


@dataclass
class ScalpingSignal:
    action: str  # BUY/SELL/NEUTRAL
    entry: float
    stop_loss: float
    take_profit: float
    confidence: float
    reason: str
    scalp_type: str
    timeframe: str
    atr: float
    meta: Dict


class ICTScalpingEngine:
    """ICT/SMC specialized for short-horizon scalps."""

    def analyze(self, data: pd.DataFrame) -> Optional[ScalpingSignal]:
        if data is None or len(data) < 20:
            return None

        current = data.iloc[-1]
        current_price = float(current.get("close", np.nan))
        atr = float(current.get("atr", np.nan)) if "atr" in data.columns else self._calculate_atr(data, 14).iloc[-1]
        atr = float(atr) if np.isfinite(atr) and atr > 0 else 2.0

        sweep = self._detect_liquidity_sweep(data)
        fvg = self._detect_fvg(data)
        displacement = self._detect_displacement(data)

        # BUY
        if sweep and sweep["type"] == "BUY_SWEEP" and displacement:
            stop_pips = max(10.0, float(atr) * 5.0)  # adaptive-ish fallback for repo price scale
            target_pips = stop_pips * 1.5
            stop = current_price - (stop_pips / 10000.0)
            tp = current_price + (target_pips / 10000.0)
            return ScalpingSignal(
                action="BUY",
                entry=current_price,
                stop_loss=stop,
                take_profit=tp,
                confidence=0.75,
                reason=f"Liquidity sweep + displacement ({sweep['level']:.5f})",
                scalp_type="liquidity",
                timeframe="M1",
                atr=atr,
                meta={"sweep": sweep, "fvg": fvg},
            )

        # SELL
        if sweep and sweep["type"] == "SELL_SWEEP" and displacement:
            stop_pips = max(10.0, float(atr) * 5.0)
            target_pips = stop_pips * 1.5
            stop = current_price + (stop_pips / 10000.0)
            tp = current_price - (target_pips / 10000.0)
            return ScalpingSignal(
                action="SELL",
                entry=current_price,
                stop_loss=stop,
                take_profit=tp,
                confidence=0.75,
                reason=f"Liquidity sweep + displacement ({sweep['level']:.5f})",
                scalp_type="liquidity",
                timeframe="M1",
                atr=atr,
                meta={"sweep": sweep, "fvg": fvg},
            )

        # FVG
        if fvg and fvg["type"] == "BULLISH":
            bottom = float(fvg["bottom"])
            if abs(current_price - bottom) < 0.0005:
                stop = current_price - 0.0010
                tp = float(fvg["top"])
                return ScalpingSignal(
                    action="BUY",
                    entry=current_price,
                    stop_loss=stop,
                    take_profit=tp,
                    confidence=0.70,
                    reason=f"FVG retest ({bottom:.5f})",
                    scalp_type="fvg",
                    timeframe="M1",
                    atr=atr,
                    meta={"fvg": fvg},
                )

        if fvg and fvg["type"] == "BEARISH":
            top = float(fvg["top"])
            if abs(current_price - top) < 0.0005:
                stop = current_price + 0.0010
                tp = float(fvg["bottom"])
                return ScalpingSignal(
                    action="SELL",
                    entry=current_price,
                    stop_loss=stop,
                    take_profit=tp,
                    confidence=0.70,
                    reason=f"FVG retest ({top:.5f})",
                    scalp_type="fvg",
                    timeframe="M1",
                    atr=atr,
                    meta={"fvg": fvg},
                )

        return None

    def _detect_liquidity_sweep(self, data: pd.DataFrame) -> Optional[Dict]:
        if len(data) < 10:
            return None

        last10 = data.tail(10)
        highs = last10["high"].values
        lows = last10["low"].values

        recent_high = float(max(highs[:-1]))
        recent_low = float(min(lows[:-1]))
        current = data.iloc[-1]

        # Buy-side sweep (price above high, then closes below)
        if float(current["high"]) > recent_high and float(current["close"]) < recent_high:
            return {"type": "SELL_SWEEP", "level": recent_high}

        # Sell-side sweep (price below low, then closes above)
        if float(current["low"]) < recent_low and float(current["close"]) > recent_low:
            return {"type": "BUY_SWEEP", "level": recent_low}

        return None

    def _detect_fvg(self, data: pd.DataFrame) -> Optional[Dict]:
        if len(data) < 3:
            return None

        last3 = data.tail(3)
        c1, c2, c3 = last3.iloc[0], last3.iloc[1], last3.iloc[2]

        if float(c3["low"]) > float(c1["high"]):
            return {"type": "BULLISH", "top": float(c3["low"]), "bottom": float(c1["high"])}
        if float(c3["high"]) < float(c1["low"]):
            return {"type": "BEARISH", "top": float(c1["low"]), "bottom": float(c3["high"])}

        return None

    def _detect_displacement(self, data: pd.DataFrame) -> bool:
        if len(data) < 5:
            return False

        last = data.iloc[-1]
        prev = data.iloc[-2]

        body = abs(float(last["close"]) - float(last["open"]))
        bodies = (data["close"].diff().abs()).tail(20)
        avg_body = float(bodies.mean()) if len(bodies) else 0.0
        return body > avg_body * 1.5 if avg_body > 0 else False

    def _calculate_atr(self, data: pd.DataFrame, period: int) -> pd.Series:
        high_low = data["high"] - data["low"]
        high_close = (data["high"] - data["close"].shift()).abs()
        low_close = (data["low"] - data["close"].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(period).mean()


class MomentumScalpingEngine:
    """Fast momentum scalps with volume/EMA confirmation."""

    def analyze(self, data: pd.DataFrame) -> Optional[ScalpingSignal]:
        if data is None or len(data) < 10:
            return None

        current = data.iloc[-1]
        prev = data.iloc[-2]

        current_price = float(current.get("close", np.nan))
        atr = float(current.get("atr", np.nan)) if "atr" in data.columns else 2.0
        atr = float(atr) if np.isfinite(atr) and atr > 0 else 2.0

        momentum_1 = float(current["close"]) - float(prev["close"])
        momentum_5 = float(current["close"]) - float(data["close"].iloc[-6]) if len(data) >= 6 else 0.0

        vol = float(current.get("volume", 0.0))
        if "volume" in data.columns:
            vol_avg = float(data["volume"].rolling(10).mean().iloc[-1]) if len(data) >= 10 else 0.0
        else:
            vol_avg = 0.0
        volume_surge = vol_avg > 0 and vol > vol_avg * 1.5

        ema5 = data["close"].ewm(span=5, adjust=False).mean().iloc[-1]
        ema10 = data["close"].ewm(span=10, adjust=False).mean().iloc[-1]
        ema_cross_bull = float(ema5) > float(ema10)

        # thresholds tuned to repo price scale (not true pips)
        if momentum_1 > 0.3 and momentum_5 > 0 and (volume_surge or vol_avg == 0) and ema_cross_bull:
            entry = current_price
            stop = entry - (atr * 0.75)  # price units fallback
            tp = entry + (atr * 1.2)
            conf = min(0.85, 0.6 + (momentum_1 / 1.0))
            return ScalpingSignal(
                action="BUY",
                entry=entry,
                stop_loss=stop,
                take_profit=tp,
                confidence=float(conf),
                reason=f"Momentum up: {momentum_1:.4f} + EMA confirm",
                scalp_type="momentum",
                timeframe="M1",
                atr=atr,
                meta={"momentum_1": momentum_1, "momentum_5": momentum_5},
            )

        if momentum_1 < -0.3 and momentum_5 < 0 and (volume_surge or vol_avg == 0) and not ema_cross_bull:
            entry = current_price
            stop = entry + (atr * 0.75)
            tp = entry - (atr * 1.2)
            conf = min(0.85, 0.6 + (abs(momentum_1) / 1.0))
            return ScalpingSignal(
                action="SELL",
                entry=entry,
                stop_loss=stop,
                take_profit=tp,
                confidence=float(conf),
                reason=f"Momentum down: {momentum_1:.4f} + EMA confirm",
                scalp_type="momentum",
                timeframe="M1",
                atr=atr,
                meta={"momentum_1": momentum_1, "momentum_5": momentum_5},
            )

        return None


class BreakoutScalpingEngine:
    """Range breakout scalps (session-ish / micro breakout)."""

    def analyze(self, data: pd.DataFrame) -> Optional[ScalpingSignal]:
        if data is None or len(data) < 20:
            return None

        current_price = float(data["close"].iloc[-1])
        atr = float(data["atr"].iloc[-1]) if "atr" in data.columns else 2.0
        atr = float(atr) if np.isfinite(atr) and atr > 0 else 2.0

        range_high = float(data["high"].tail(15).max())
        range_low = float(data["low"].tail(15).min())

        if current_price > range_high:
            entry = current_price
            stop = entry - (atr * 0.8)
            tp = entry + (atr * 1.6)
            return ScalpingSignal(
                action="BUY",
                entry=entry,
                stop_loss=stop,
                take_profit=tp,
                confidence=0.68,
                reason=f"Breakout above {range_high:.5f}",
                scalp_type="breakout",
                timeframe="M5",
                atr=atr,
                meta={"range_high": range_high},
            )

        if current_price < range_low:
            entry = current_price
            stop = entry + (atr * 0.8)
            tp = entry - (atr * 1.6)
            return ScalpingSignal(
                action="SELL",
                entry=entry,
                stop_loss=stop,
                take_profit=tp,
                confidence=0.68,
                reason=f"Breakdown below {range_low:.5f}",
                scalp_type="breakout",
                timeframe="M5",
                atr=atr,
                meta={"range_low": range_low},
            )

        return None


class GoldScalpingOrchestrator:
    def __init__(self) -> None:
        self.ict = ICTScalpingEngine()
        self.momentum = MomentumScalpingEngine()
        self.breakout = BreakoutScalpingEngine()

    def analyze(self, data: pd.DataFrame) -> Optional[Dict]:
        """Return repo-compatible signal dict."""
        if data is None or len(data) < 25:
            return None

        candidates: list[ScalpingSignal] = []
        for engine in (self.ict, self.momentum, self.breakout):
            sig = engine.analyze(data)
            if sig is not None:
                candidates.append(sig)

        if not candidates:
            return None

        best = max(candidates, key=lambda s: s.confidence)

        return {
            "signal": best.action,
            "entry": best.entry,
            "stop_loss": best.stop_loss,
            "take_profit": best.take_profit,
            "atr": best.atr,
            "confidence": float(best.confidence),
            "ai_prediction": {
                "confidence": float(best.confidence),
                "probability": float(best.confidence),
                "model": best.scalp_type,
            },
            "scalp_type": best.scalp_type,
            "scalp_timeframe": best.timeframe,
            "scalp_reason": best.reason,
            "meta": best.meta,
            "timestamp": time.time(),
        }

