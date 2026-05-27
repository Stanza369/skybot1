import MetaTrader5 as mt5
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class ProductionMT5Connector:
    """Handles real-money execution and data retrieval via MetaTrader 5."""
    
    def __init__(self, login: int, password: str, server: str):
        self.login_id = login
        self.password = password
        self.server = server
        self.connected = False

    def connect(self) -> bool:
        if not mt5.initialize():
            logger.error(f"MT5 initialize() failed, error code: {mt5.last_error()}")
            return False
        
        authorized = mt5.login(self.login_id, password=self.password, server=self.server)
        if authorized:
            logger.info(f"Connected to MT5 Account: {self.login_id}")
            self.connected = True
        else:
            logger.error(f"Failed to connect to MT5: {mt5.last_error()}")
        return authorized

    def get_market_data(self, symbol: str, timeframe: int, count: int = 100):
        """Fetch real-time OHLCV data directly from the broker."""
        import pandas as pd
        rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, count)
        if rates is None:
            logger.error(f"Failed to copy rates for {symbol}: {mt5.last_error()}")
            return None
        
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        df.set_index('time', inplace=True)
        return df

    def place_order(self, symbol: str, action: str, volume: float, sl: float, tp: float, magic: int = 123456):
        """Executes a real market order."""
        if not self.connected:
            if not self.connect(): return None

        order_type = mt5.ORDER_TYPE_BUY if action.upper() == "BUY" else mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(symbol).ask if action.upper() == "BUY" else mt5.symbol_info_tick(symbol).bid

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": float(volume),
            "type": order_type,
            "price": float(price),
            "sl": float(sl),
            "tp": float(tp),
            "deviation": 20,
            "magic": magic,
            "comment": "ICT Production Bot",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"Order failed: {result.comment} (code: {result.retcode})")
            return None
        
        logger.info(f"Order executed successfully: {action} {volume} lots at {price}")
        return result

    def get_account_balance(self) -> float:
        acc = mt5.account_info()
        return float(acc.balance) if acc else 0.0

    def shutdown(self):
        mt5.shutdown()