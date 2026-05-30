from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from mt5_live_trader import MT5LiveTrader

logger = logging.getLogger(__name__)


TIMEFRAME_MAP = {
    "M1": 1,
    "M5": 5,
    "M15": 15,
    "M30": 30,
    "H1": 60,
    "H4": 240,
    "D1": 1440,
}


def _ensure_float(x: Any) -> Optional[float]:
    try:
        if x is None:
            return None
        return float(x)
    except Exception:
        return None


class MT5Service:
    def __init__(self):
        self._trader: Optional[MT5LiveTrader] = None

    @property
    def connected(self) -> bool:
        return bool(self._trader and self._trader.connected)

    def connect(self, *, login: int, password: str, server: str, symbol: str = "XAUUSD") -> Dict[str, Any]:
        self._trader = MT5LiveTrader(symbol=symbol, account_info={"login": login, "password": password, "server": server})
        ok = self._trader.connect()
        if not ok:
            return {"success": False, "error": "MT5 connect failed"}
        return {"success": True, "balance": self._trader.balance, "symbol": symbol}

    def disconnect(self) -> None:
        if self._trader:
            self._trader.disconnect()
        self._trader = None

    def account_info(self) -> Optional[Dict[str, Any]]:
        if not self._trader or not self._trader.connected:
            return None
        # We rely on MT5LiveTrader.balance plus symbol spread info.
        # For full margin/free-margin etc., we would call MetaTrader5 directly.
        return {
            "login": self._trader.account_info.get("login", 0),
            "balance": self._trader.balance,
            "equity": self._trader.balance,
            "margin": 0.0,
            "free_margin": self._trader.balance,
            "margin_level": 0.0,
            "currency": ""
        }

    def get_symbols(self, limit: int = 50) -> List[str]:
        try:
            import MetaTrader5 as mt5  # type: ignore
            if not self.connected:
                return []
            symbols = mt5.symbols_get()
            if not symbols:
                return []
            return [s.name for s in symbols][:limit]
        except Exception as e:
            logger.warning("get_symbols failed: %s", e)
            return []

    def market_ohlc(self, *, symbol: str, timeframe: str = "M5", count: int = 100) -> Dict[str, Any]:
        if not self._trader or not self._trader.connected:
            return {"error": "Not connected"}

        if timeframe not in TIMEFRAME_MAP:
            timeframe = "M5"

        tf_minutes = TIMEFRAME_MAP[timeframe]

        # MT5LiveTrader.get_rates expects MT5 timeframe constant, but this repo's wrapper uses raw ints.
        # MetaTrader5 Python accepts timeframe as enum-like ints in many cases.
        df = self._trader.get_rates(timeframe=tf_minutes, count=count)
        if df is None or df.empty:
            return {"error": f"Failed to get data for {symbol}"}

        # Convert to OHLC for Lightweight Charts
        # DataFrame already has columns from MT5 rates: open/high/low/close/time
        out = []
        for t, row in df.iterrows():
            out.append({
                "time": int(pd.Timestamp(t).timestamp()),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
            })

        return {"symbol": symbol, "timeframe": timeframe, "data": out}

    def place_order(
        self,
        *,
        symbol: str,
        action: str,
        volume: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not self._trader or not self._trader.connected:
            return {"success": False, "error": "Not connected"}

        result = self._trader.place_market_order(
            action=action,
            lot_size=volume,
            sl=stop_loss,
            tp=take_profit,
            comment="Trading Dashboard",
        )

        if result is None:
            return {"success": False, "error": "order_send failed"}

        # Best-effort fields
        order_id = getattr(result, "order", None)
        price = getattr(result, "price", None)
        retcode = getattr(result, "retcode", None)
        comment = getattr(result, "comment", "")

        if retcode is not None and int(retcode) != 10009:  # TRADE_RETCODE_DONE common
            return {"success": False, "error": f"Order failed: {comment}"}

        # Best-effort notification (non-blocking)
        try:
            # IMPORTANT: do NOT use asyncio.run() inside FastAPI request threads.
            # notification_manager is best-effort; if it needs an event loop it should be handled there.
            from backend.notification_manager import notification_manager
            import os
            user_id = int(os.getenv('ADMIN_USER_ID', '1'))
            notify = {
                'symbol': symbol,
                'action': action,
                'volume': volume,
                'entry_price': _ensure_float(price),
                'order_id': order_id,
            }
            # If notification_manager exposes an async method, call it via create_task.
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(notification_manager.send_notification(user_id, 'trade', notify))
            except RuntimeError:
                # No running loop (rare). Fall back to direct call if it is sync.
                maybe_coro = notification_manager.send_notification(user_id, 'trade', notify)
                if asyncio.iscoroutine(maybe_coro):
                    # Can't await here; ignore.
                    pass

        except Exception:
            logger.exception('Failed to send place_order notification')

        return {
            "success": True,
            "order_id": order_id,
            "price": _ensure_float(price),
            "symbol": symbol,
            "volume": volume,
            "action": action,
        }


    def positions(self) -> List[Dict[str, Any]]:
        try:
            import MetaTrader5 as mt5  # type: ignore
            if not self.connected:
                return []
            pos = mt5.positions_get()
            if not pos:
                return []
            out = []
            for p in pos:
                ptype = "BUY" if int(p.type) == 0 else "SELL"
                out.append({
                    "ticket": int(p.ticket),
                    "symbol": p.symbol,
                    "type": ptype,
                    "volume": float(p.volume),
                    "price_open": float(p.price_open),
                    "price_current": float(p.price_current),
                    "profit": float(p.profit),
                    "sl": float(p.sl) if p.sl is not None else None,
                    "tp": float(p.tp) if p.tp is not None else None,
                })
            return out
        except Exception as e:
            logger.warning("positions failed: %s", e)
            return []

    def close_position(self, ticket: int) -> Dict[str, Any]:
        try:
            import MetaTrader5 as mt5  # type: ignore
            if not self.connected:
                return {"success": False, "error": "Not connected"}

            pos = mt5.positions_get(ticket=ticket)
            if not pos:
                return {"success": False, "error": "Position not found"}
            p = pos[0]

            tick = mt5.symbol_info_tick(p.symbol)
            if tick is None:
                return {"success": False, "error": "No tick data"}

            # If position is BUY, close with SELL at bid; if SELL, close with BUY at ask
            if int(p.type) == 0:
                order_type = mt5.ORDER_TYPE_SELL
                price = float(tick.bid)
            else:
                order_type = mt5.ORDER_TYPE_BUY
                price = float(tick.ask)

            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": p.symbol,
                "volume": float(p.volume),
                "type": order_type,
                "position": int(ticket),
                "price": price,
                "deviation": 10,
                "magic": int(getattr(p, "magic", 123456) or 123456),
                "comment": "Close via Trading Dashboard",
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }

            result = mt5.order_send(request)
            if result is None:
                return {"success": False, "error": "order_send returned None"}

            retcode = getattr(result, "retcode", None)
            comment = getattr(result, "comment", "")
            if retcode is not None and int(retcode) != 10009:
                return {"success": False, "error": f"Close failed: {comment}"}

            profit = float(getattr(p, "profit", 0.0) or 0.0)
            try:
                # Best-effort: update chat learning with realized outcome.
                from chat_learning_system import on_trade_complete

                trade = {
                    "ticket": int(ticket),
                    "symbol": p.symbol,
                    "type": "BUY" if int(p.type) == 0 else "SELL",
                    "factors": [],
                }
                on_trade_complete(trade, profit)
            except Exception:
                logger.exception("Failed to update chat learning on trade close")

            order_id = getattr(result, "order", None)
            return {"success": True, "ticket": int(ticket), "profit": profit, "order_id": int(order_id) if order_id is not None else None}


        except Exception as e:
            return {"success": False, "error": str(e)}

    def order_history(self, limit: int = 200) -> List[Dict[str, Any]]:
        try:
            import MetaTrader5 as mt5  # type: ignore
            if not self.connected:
                return []

            # Simple: fetch last deals without date filtering.
            deals = mt5.history_deals_get(None, None)
            if not deals:
                return []

            deals = list(deals)[-limit:]
            out = []
            for d in deals:
                out.append({
                    "ticket": int(d.ticket),
                    "order": int(getattr(d, "order", 0) or 0),
                    "symbol": d.symbol,
                    "type": "BUY" if int(d.type) == 0 else "SELL",
                    "volume": float(d.volume),
                    "price": float(d.price),
                    "profit": float(d.profit),
                    "time": int(d.time) if isinstance(d.time, (int, float)) else str(d.time),
                })
            return out
        except Exception as e:
            logger.warning("order_history failed: %s", e)
            return []

