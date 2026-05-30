"""Order execution abstraction.

This repository currently implements a *paper* execution mode for the
FastAPI UI/API so CI and local tests can run without broker connectivity.

If you want real entries (MT5/venue execution), replace `PaperBroker`
with an MT5 broker implementation.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

Side = Literal["BUY", "SELL"]


@dataclass
class OrderResult:
    success: bool
    order_id: str
    side: Side
    volume: float
    price: float
    timestamp: str
    message: str
    extra: Dict[str, Any]


class PaperBroker:
    """In-memory/paper broker used by the API."""

    def execute(
        self,
        *,
        side: Side,
        volume: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        symbol: str = "XAUUSD",
    ) -> OrderResult:
        now = datetime.utcnow().isoformat()
        order_id = f"ORD_{int(datetime.utcnow().timestamp())}"

        msg = f"{side} {volume} lots executed at ${price:.2f}"
        extra: Dict[str, Any] = {
            "symbol": symbol,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
        }

        return OrderResult(
            success=True,
            order_id=order_id,
            side=side,
            volume=volume,
            price=price,
            timestamp=now,
            message=msg,
            extra=extra,
        )

class MT5Broker:
    """Real execution via MetaTrader 5."""

    def __init__(self, symbol: str = "XAUUSD"):
        if platform.system() != "Windows":
            raise RuntimeError("MetaTrader5 Python API is only available on Windows.")
        
        import MetaTrader5 as mt5
        self.mt5 = mt5
        self.symbol = symbol
        
        if not self.mt5.initialize():
            logger.error(f"MT5 initialize failed: {self.mt5.last_error()}")
            raise RuntimeError("Could not connect to MT5 Terminal.")

    def execute(
        self,
        *,
        side: Side,
        volume: float,
        price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
        symbol: str = "XAUUSD",
    ) -> OrderResult:
        # Ensure symbol is selected
        self.mt5.symbol_select(symbol, True)
        
        # Get filling mode (common for many brokers)
        symbol_info = self.mt5.symbol_info(symbol)
        if symbol_info is None:
            return OrderResult(False, "0", side, volume, price, "", f"{symbol} not found", {})

        order_type = self.mt5.ORDER_TYPE_BUY if side == "BUY" else self.mt5.ORDER_TYPE_SELL
        # Use current market price rather than passed price for Market execution
        curr_price = self.mt5.symbol_info_tick(symbol).ask if side == "BUY" else self.mt5.symbol_info_tick(symbol).bid

        request = {
            "action": self.mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": curr_price,
            "magic": 234000,
            "comment": "Skybot Elite Execution",
            "type_time": self.mt5.ORDER_TIME_GTC,
            "type_filling": self.mt5.ORDER_FILLING_IOC,
        }

        if stop_loss:
            request["sl"] = stop_loss
        if take_profit:
            request["tp"] = take_profit

        result = self.mt5.order_send(request)
        
        if result.retcode != self.mt5.TRADE_RETCODE_DONE:
            return OrderResult(
                success=False,
                order_id="0",
                side=side,
                volume=volume,
                price=curr_price,
                timestamp=datetime.utcnow().isoformat(),
                message=f"FAILED: {result.comment} (Code: {result.retcode})",
                extra={"error": self.mt5.last_error()}
            )

        return OrderResult(
            success=True,
            order_id=str(result.order),
            side=side,
            volume=volume,
            price=result.price,
            timestamp=datetime.utcnow().isoformat(),
            message=f"SUCCESS: {side} order filled at {result.price}",
            extra={"deal": result.deal}
        )
