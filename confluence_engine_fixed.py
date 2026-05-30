import logging
import math
import time
from dataclasses import dataclass
from typing import Optional, Tuple

import MetaTrader5 as mt5

logger = logging.getLogger(__name__)


@dataclass
class ConfluenceSignal:
    side: Optional[str]  # "BUY" | "SELL" | None
    confidence: float
    reasons: str
    ts: float


class ConfluenceDashboardEngine:
    """Rule-based confluence engine.

    Implements (in spirit) the dashboard logic:
      - Trend filter using EMA(20)/EMA(50) on H1
      - Yesterday's High/Low from D1
      - Asian session range (optional context) computed from M15 in server time
      - Wick rejection at yesterday's S/R with small-body candles
    """

    def __init__(
        self,
        symbol: str,
        *,
        ema_fast: int = 20,
        ema_slow: int = 50,
        wick_body_ratio: float = 0.30,
        asian_start_hour: int = 20,
        asian_start_minute: int = 0,
        asian_end_hour: int = 3,
        asian_end_minute: int = 0,
    ):
        self.symbol = symbol
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.wick_body_ratio = wick_body_ratio
        self.asian_start_hour = asian_start_hour
        self.asian_start_minute = asian_start_minute
        self.asian_end_hour = asian_end_hour
        self.asian_end_minute = asian_end_minute

    def _asian_session_minutes(self, dt) -> bool:
        minutes = dt.hour * 60 + dt.minute
        s = self.asian_start_hour * 60 + self.asian_start_minute
        e = self.asian_end_hour * 60 + self.asian_end_minute

        if s <= e:
            return s <= minutes < e
        # spans midnight
        return minutes >= s or minutes < e

    def _fetch_rates(self, timeframe: int, count: int):
        rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, count)
        if rates is None or len(rates) < count:
            return None
        return rates

    @staticmethod
    def _ema_from_closes(closes, period: int) -> float:
        k = 2 / (period + 1)
        ema = float(closes[0])
        for x in closes[1:]:
            ema = float(x) * k + ema * (1 - k)
        return float(ema)

    def _get_ema_trend(self) -> Tuple[bool, bool, float, float]:
        rates = self._fetch_rates(mt5.TIMEFRAME_H1, max(self.ema_slow, 120))
        if rates is None:
            raise RuntimeError("Failed to fetch H1 rates for EMA")

        closes = [float(r[4]) for r in rates]
        ema_fast = self._ema_from_closes(closes, self.ema_fast)
        ema_slow = self._ema_from_closes(closes, self.ema_slow)
        last_close = closes[-1]

        uptrend = last_close > ema_fast and last_close > ema_slow and ema_fast > ema_slow
        downtrend = last_close < ema_fast and last_close < ema_slow and ema_fast < ema_slow
        return uptrend, downtrend, ema_fast, ema_slow

    def _get_yesterday_high_low(self) -> Tuple[float, float]:
        rates = self._fetch_rates(mt5.TIMEFRAME_D1, 3)
        if rates is None:
            raise RuntimeError("Failed to fetch D1 rates for yesterday levels")

        y_high = float(rates[1][2])  # high
        y_low = float(rates[1][3])   # low
        return y_high, y_low

    def _get_asian_range(self) -> Tuple[Optional[float], Optional[float]]:
        rates = self._fetch_rates(mt5.TIMEFRAME_M15, 24 * 4 + 20)
        if rates is None:
            return None, None

        asian_high = None
        asian_low = None

        for r in rates:
            bar_time = float(r[0])
            bdt = time.gmtime(bar_time)
            if self._asian_session_minutes(bdt):
                h = float(r[2])
                l = float(r[3])
                asian_high = h if asian_high is None else max(asian_high, h)
                asian_low = l if asian_low is None else min(asian_low, l)

        return asian_high, asian_low

    def _get_current_candle(self):
        rates = self._fetch_rates(mt5.TIMEFRAME_M15, 5)
        if rates is None:
            raise RuntimeError("Failed to fetch M15 rates for price action")
        last = rates[-1]
        o = float(last[1])
        h = float(last[2])
        l = float(last[3])
        c = float(last[4])
        return o, h, l, c

    def evaluate(self, *, min_confidence: float = 0.70) -> ConfluenceSignal:
        ts = time.time()
        try:
            uptrend, downtrend, _, _ = self._get_ema_trend()
            y_high, y_low = self._get_yesterday_high_low()
            asian_high, asian_low = self._get_asian_range()
            o, h, l, c = self._get_current_candle()
        except Exception as e:
            return ConfluenceSignal(side=None, confidence=0.0, reasons=f"engine_error: {e}", ts=ts)

        body = abs(c - o)
        rng = (h - l) if (h - l) != 0 else 1e-9
        is_small_body = (body / rng) <= self.wick_body_ratio

        bullish_reject = is_small_body and c > o and l < y_low and c > y_low
        bearish_reject = is_small_body and c < o and h > y_high and c < y_high

        if uptrend and bullish_reject:
            conf = 0.68
            if asian_high is not None and asian_low is not None:
                conf += 0.07
            return ConfluenceSignal(
                side="BUY",
                confidence=float(max(0.50, min(0.85, conf))),
                reasons="trend=UP;wick=BULL_y_low;asian_range_set" if asian_high is not None else "trend=UP;wick=BULL_y_low",
                ts=ts,
            )

        if downtrend and bearish_reject:
            conf = 0.68
            if asian_high is not None and asian_low is not None:
                conf += 0.07
            return ConfluenceSignal(
                side="SELL",
                confidence=float(max(0.50, min(0.85, conf))),
                reasons="trend=DOWN;wick=BEAR_y_high;asian_range_set" if asian_high is not None else "trend=DOWN;wick=BEAR_y_high",
                ts=ts,
            )

        return ConfluenceSignal(side=None, confidence=0.50, reasons="no_confluence", ts=ts)
