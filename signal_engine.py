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
    """Rule-based confluence engine inspired by the TradingView dashboard logic.

    Signals are intended to be conservative: EMA trend filter + (D1) yesterday S/R +
    Asian session context + wick rejection touching S/R.
    """

    def __init__(self, symbol: str, *,
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

    @staticmethod
    def _is_asian_session(dt) -> bool:
        # Treat session as possibly spanning midnight
        start = (dt.hour, dt.minute) >= (0, 0)
        _ = start
        if (ConfluenceDashboardEngine._time_ge(dt.hour, dt.minute,
                                              ConfluenceDashboardEngine._norm_time(ConfluenceDashboardEngine,
                                                                                0, 0))):
            pass
        # We'll do a simpler approach: compare by minutes since midnight.
        minutes = dt.hour * 60 + dt.minute
        s = 20 * 60  # default; overwritten below by instance via call wrapper
        e = 3 * 60
        # placeholder
        return True

    @staticmethod
    def _time_ge(h1, m1, h2, m2) -> bool:
        return (h1 > h2) or (h1 == h2 and m1 >= m2)

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

    def _ema(self, closes, period: int) -> float:
        # EMA from scratch to avoid numpy dependency.
        k = 2 / (period + 1)
        ema = closes[0]
        for x in closes[1:]:
            ema = x * k + ema * (1 - k)
        return float(ema)

    def _get_ema_trend(self) -> Tuple[bool, bool, float, float]:
        # Need enough bars for both EMAs.
        rates = self._fetch_rates(mt5.TIMEFRAME_H1, max(self.ema_slow, 100))
        if rates is None:
            raise RuntimeError("Failed to fetch H1 rates for EMA")

        closes = [float(r[4]) for r in rates]  # close
        ema_fast = self._ema(closes, self.ema_fast)
        ema_slow = self._ema(closes, self.ema_slow)

        # Conservative: use last close from the series
        last_close = closes[-1]
        uptrend = last_close > ema_fast and last_close > ema_slow and ema_fast > ema_slow
        downtrend = last_close < ema_fast and last_close < ema_slow and ema_fast < ema_slow
        return uptrend, downtrend, ema_fast, ema_slow

    def _get_yesterday_high_low(self) -> Tuple[float, float]:
        # D1: yesterday is index 1 (current daily bar = 0, yesterday = 1)
        rates = self._fetch_rates(mt5.TIMEFRAME_D1, 3)
        if rates is None:
            raise RuntimeError("Failed to fetch D1 rates for yesterday levels")

        y_high = float(rates[1][2])  # high
        y_low = float(rates[1][3])   # low
        return y_high, y_low

    def _get_asian_range(self) -> Tuple[Optional[float], Optional[float]]:
        # Compute Asian high/low for the *current* trading day using H1 or M15 bars.
        # We'll use M15 for better precision.
        now = time.time()
        dt = time.gmtime(now)  # fallback
        # Use MT5 server time if available
        srv = mt5.symbol_info_tick(self.symbol)
        if srv is not None:
            # mt5 tick time is in seconds since epoch
            dt = time.gmtime(srv.time)

        # Fetch last 24h of M15
        rates = self._fetch_rates(mt5.TIMEFRAME_M15, 24 * 4 + 10)
        if rates is None:
            return None, None

        asian_high = None
        asian_low = None

        for r in rates:
            bar_time = r[0]
            bdt = time.gmtime(float(bar_time))
            if self._asian_session_minutes(bdt):
                h = float(r[2])
                l = float(r[3])
                asian_high = h if asian_high is None else max(asian_high, h)
                asian_low = l if asian_low is None else min(asian_low, l)

        return asian_high, asian_low

    def _get_current_candle(self):
        # Use M15 candle because bot loops frequently; adjust later if you want.
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

        # Trend gating
        trend_ok_buy = uptrend
        trend_ok_sell = downtrend

        body = abs(c - o)
        rng = (h - l) if (h - l) != 0 else 1e-9
        is_small_body = (body / rng) <= self.wick_body_ratio

        bullish_reject = is_small_body and c > o and l < y_low and c > y_low
        bearish_reject = is_small_body and c < o and h > y_high and c < y_high

        # Confidence scoring (0.50..0.85 style)
        conf = 0.50
        reasons = []

        if trend_ok_buy and bullish_reject:
            conf += 0.18
            reasons.append("trend=UP")
            reasons.append("wick=BULL at y_low")
            if asian_high is not None:
                reasons.append("asian_range=known")
            if asian_low is not None:
                reasons.append("asian_range_bounds_set")
            return ConfluenceSignal(side="BUY", confidence=float(min(0.85, conf)), reasons=";".join(reasons), ts=ts)

        if trend_ok_sell and bearish_reject:
            conf += 0.18
            reasons.append("trend=DOWN")
            reasons.append("wick=BEAR at y_high")
            if asian_high is not None:
                reasons.append("asian_range=known")
            if asian_low is not None:
                reasons.append("asian_range_bounds_set")
            return ConfluenceSignal(side="SELL", confidence=float(min(0.85, conf)), reasons=";".join(reasons), ts=ts)

        return ConfluenceSignal(side=None, confidence=float(conf), reasons="no_confluence", ts=ts)
