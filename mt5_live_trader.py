# mt5_live_trader.py

import logging
from typing import Any, Dict, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5  # type: ignore

    MT5_AVAILABLE = True
except Exception:  # pragma: no cover
    MT5_AVAILABLE = False


class MT5LiveTrader:
    """Minimal MT5 execution wrapper.

    This file is meant to be imported safely even if MetaTrader5 is not installed.
    """

    def __init__(
        self,
        *,
        symbol: str = "XAUUSD",
        magic_number: int = 123456,
        slippage: int = 10,
        account_info: Optional[Dict[str, Any]] = None,
    ):
        self.symbol = symbol
        self.magic_number = magic_number
        self.slippage = slippage
        self.account_info = account_info or {"login": 0, "password": "", "server": ""}

        self.connected = False
        self.balance: float = 0.0

    def connect(self) -> bool:
        if not MT5_AVAILABLE:
            logger.error("MetaTrader5 is not available. Install with: pip install MetaTrader5")
            return False

        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return False

        login = int(self.account_info.get("login", 0) or 0)
        if login:
            authorized = mt5.login(
                login=login,
                password=self.account_info.get("password", ""),
                server=self.account_info.get("server", ""),
            )
            if not authorized:
                logger.error("MT5 login failed")
                mt5.shutdown()
                return False

        self.connected = True
        acc = mt5.account_info()
        if acc is not None:
            self.balance = float(getattr(acc, "balance", 0.0) or 0.0)
        logger.info(f"Connected to MT5. Balance: {self.balance:.2f}")
        return True

    def disconnect(self) -> None:
        if self.connected and MT5_AVAILABLE:
            mt5.shutdown()
        self.connected = False

    def get_symbol_info(self, symbol: Optional[str] = None) -> Dict[str, Any]:
        if not self.connected:
            return {}
        info = mt5.symbol_info(symbol or self.symbol)
        if info is None:
            return {}
        return {
            "name": info.name,
            "spread": info.spread,
            "digits": info.digits,
            "volume_min": info.volume_min,
            "volume_max": info.volume_max,
            "volume_step": info.volume_step,
        }

    def get_rates(self, *, timeframe: int, count: int = 200):
        if not self.connected:
            return None
        rates = mt5.copy_rates_from_pos(self.symbol, timeframe, 0, count)
        if rates is None:
            return None
        import pandas as pd

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        return df

    def get_current_bid_ask(self) -> tuple[Optional[float], Optional[float]]:
        if not self.connected:
            return None, None
        tick = mt5.symbol_info_tick(self.symbol)
        if tick is None:
            return None, None
        return float(tick.bid), float(tick.ask)

    def place_market_order(
        self,
        *,
        action: str,
        lot_size: float,
        sl: Optional[float] = None,
        tp: Optional[float] = None,
        comment: str = "ICT Bot",
    ):
        if not self.connected:
            return None

        action_u = action.upper()
        bid, ask = self.get_current_bid_ask()
        if bid is None or ask is None:
            return None

        if action_u == "BUY":
            price = ask
            order_type = mt5.ORDER_TYPE_BUY
        elif action_u == "SELL":
            price = bid
            order_type = mt5.ORDER_TYPE_SELL
        else:
            raise ValueError("action must be BUY or SELL")

        request: Dict[str, Any] = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.symbol,
            "volume": float(lot_size),
            "type": order_type,
            "price": float(price),
            "slippage": int(self.slippage),
            "magic": int(self.magic_number),
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        if sl is not None:
            request["sl"] = float(sl)
        if tp is not None:
            request["tp"] = float(tp)

        result = mt5.order_send(request)
        return result


if __name__ == "__main__":
    # Smoke-test connection flow (won't run trading logic)
    trader = MT5LiveTrader(symbol="XAUUSD")
    ok = trader.connect()
    logger.info(f"MT5 connect ok={ok}")
    if ok:
        logger.info(trader.get_symbol_info())
        trader.disconnect()

