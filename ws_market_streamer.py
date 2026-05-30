from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple

from mt5_service import MT5Service

logger = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.time() * 1000)


class WsMarketStreamer:
    """Background loop that polls MT5 and pushes updates via StreamManager.

    Note: MT5 order book level-2 is usually not available via the standard API.
    For the first real "B" stream, we publish:
    - tick (bid/ask/spread)
    - a derived depth proxy using repeated tick snapshots

    This keeps the architecture real (server pushes live data) while staying within MT5 constraints.
    """

    def __init__(self, *, mt5_service: MT5Service, stream_manager: Any) -> None:
        self.mt5 = mt5_service
        self.sm = stream_manager

        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()

        self._last_tick: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # depth proxy window
        self._depth_samples: Dict[Tuple[str, str], list] = {}

    def start(self) -> None:
        if self._task and not self._task.done():
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            try:
                await self._task
            except Exception:
                pass

    async def _run_loop(self) -> None:
        # Poll frequently; only broadcast on changes.
        while not self._stop.is_set():
            try:
                # We don't have symbol list per subscription here; instead
                # we poll the "current" MT5 connected symbol via market_ohlc calls.
                # The streamer will be conservative.
                #
                # If you want multi-symbol streaming, extend StreamManager to expose keys.

                # For now, we stream a single default symbol/timeframe.
                symbol = "XAUUSD"
                timeframe = "M5"

                await self._poll_and_broadcast(symbol=symbol, timeframe=timeframe)

            except Exception as e:
                logger.warning("WsMarketStreamer loop error: %s", e)

            await asyncio.sleep(0.8)

    async def _poll_and_broadcast(self, *, symbol: str, timeframe: str) -> None:
        # Tick
        tick = await self._get_tick_snapshot(symbol=symbol)
        if tick is None:
            return

        key = (symbol, timeframe)
        last = self._last_tick.get(key)

        # Deduplicate: only broadcast if bid/ask changed meaningfully
        if last and float(last.get("bid", 0)) == float(tick.get("bid", 0)) and float(last.get("ask", 0)) == float(tick.get("ask", 0)):
            return

        self._last_tick[key] = tick

        await self.sm.broadcast(
            {
                "type": "tick",
                "symbol": symbol,
                "timeframe": timeframe,
                "ts_ms": tick["ts_ms"],
                "bid": tick["bid"],
                "ask": tick["ask"],
                "spread": tick["spread"],
            },
            symbol=symbol,
            timeframe=timeframe,
        )

        # Depth proxy: store recent mid prices and map distribution to bid/ask bars.
        mid = (tick["bid"] + tick["ask"]) / 2.0
        self._depth_samples.setdefault(key, []).append(mid)
        if len(self._depth_samples[key]) > 30:
            self._depth_samples[key] = self._depth_samples[key][-30:]

        # Create a simple depth histogram: count samples in 5 bins around mid.
        samples = self._depth_samples[key]
        bins = 5
        span = max(1e-9, tick["spread"] * 2.0)
        counts = [0] * bins
        for s in samples:
            # map into 0..bins-1 where 0 is low side
            t = (s - (mid - span)) / (2 * span)
            idx = min(bins - 1, max(0, int(t * bins)))
            counts[idx] += 1

        # Bid bins are lower half (0..2), ask bins are upper half (3..4)
        bid_strength = sum(counts[:3])
        ask_strength = sum(counts[3:])
        denom = max(1, bid_strength + ask_strength)
        imbalance = (bid_strength - ask_strength) / denom

        await self.sm.broadcast(
            {
                "type": "depth_proxy",
                "symbol": symbol,
                "timeframe": timeframe,
                "ts_ms": tick["ts_ms"],
                "bid_strength": bid_strength,
                "ask_strength": ask_strength,
                "imbalance": imbalance,
            },
            symbol=symbol,
            timeframe=timeframe,
        )

    async def _get_tick_snapshot(self, *, symbol: str) -> Optional[Dict[str, Any]]:
        # MT5Service wrapper doesn't currently expose symbol_info_tick.
        # We'll import MetaTrader5 directly if available.
        try:
            import MetaTrader5 as mt5  # type: ignore

            if not self.mt5.connected:
                return None

            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                return None

            bid = float(tick.bid)
            ask = float(tick.ask)
            spread = float(tick.ask - tick.bid)

            return {
                "ts_ms": _now_ms(),
                "bid": bid,
                "ask": ask,
                "spread": spread,
            }
        except Exception as e:
            logger.warning("tick snapshot failed: %s", e)
            return None

