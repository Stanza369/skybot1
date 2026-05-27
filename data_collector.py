import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
from typing import Dict

from config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class MT5DataCollector:
    def __init__(self, config: Config):
        self.config = config
        self.connected = False

    def connect(self) -> bool:
        if not mt5.initialize():
            logger.error("MT5 initialization failed")
            return False

        if self.config.MT5_LOGIN:
            authorized = mt5.login(
                self.config.MT5_LOGIN,
                password=self.config.MT5_PASSWORD,
                server=self.config.MT5_SERVER,
            )
            if not authorized:
                logger.error("MT5 login failed")
                return False

        self.connected = True
        logger.info("Connected to MT5")
        return True

    def disconnect(self):
        mt5.shutdown()
        self.connected = False

    def get_rates(self, timeframe: int, count: int = 1000) -> pd.DataFrame:
        rates = mt5.copy_rates_from_pos(self.config.SYMBOL, timeframe, 0, count)
        if rates is None:
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        return df

    def get_historical_data(self, days_back: int = 365 * 5) -> pd.DataFrame:
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days_back)

        rates = mt5.copy_rates_range(
            self.config.SYMBOL,
            mt5.TIMEFRAME_M1,
            start_date,
            end_date,
        )
        if rates is None:
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df["time"] = pd.to_datetime(df["time"], unit="s")
        df.set_index("time", inplace=True)
        logger.info(f"Retrieved {len(df)} M1 candles over {days_back} days")
        return df

    def get_live_price(self) -> Dict:
        tick = mt5.symbol_info_tick(self.config.SYMBOL)
        if tick is None:
            return {}
        return {
            "bid": tick.bid,
            "ask": tick.ask,
            "spread": tick.ask - tick.bid,
            "volume": tick.volume,
            "time": tick.time,
        }

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        # Local imports to reduce cold-start overhead
        from ta.momentum import RSIIndicator
        from ta.trend import MACD, EMAIndicator
        from ta.volatility import AverageTrueRange

        if df.empty:
            return df

        df = df.copy()

        df["returns"] = df["close"].pct_change()
        df["log_returns"] = np.log(df["close"] / df["close"].shift(1))

        # Volume features
        df["volume_ratio"] = df["tick_volume"] / df["tick_volume"].rolling(20).mean()
        df["volume_trend"] = df["tick_volume"].rolling(5).mean() / df["tick_volume"].rolling(20).mean()

        # Momentum
        df["momentum"] = df["close"] - df["close"].shift(5)
        df["velocity"] = df["momentum"].diff()
        df["acceleration"] = df["velocity"].diff()

        # Price features
        df["high_low_ratio"] = (df["high"] - df["low"]) / df["close"]
        df["close_open_ratio"] = (df["close"] - df["open"]) / df["open"]

        # EMAs
        df["ema_9"] = EMAIndicator(df["close"], window=9).ema_indicator()
        df["ema_21"] = EMAIndicator(df["close"], window=21).ema_indicator()
        df["ema_50"] = EMAIndicator(df["close"], window=50).ema_indicator()
        df["ema_200"] = EMAIndicator(df["close"], window=200).ema_indicator()

        # VWAP approximation
        v = df["tick_volume"].replace(0, np.nan)
        df["vwap"] = ((v * df["close"]).cumsum() / v.cumsum()).fillna(method="bfill")
        df["distance_to_vwap"] = (df["close"] - df["vwap"]) / df["vwap"]

        # RSI
        df["rsi"] = RSIIndicator(df["close"], window=14).rsi()

        # MACD
        macd = MACD(df["close"])
        df["macd_line"] = macd.macd()
        df["macd_signal"] = macd.macd_signal()
        df["macd_diff"] = macd.macd_diff()

        # ATR
        atr = AverageTrueRange(df["high"], df["low"], df["close"], window=14)
        df["atr"] = atr.average_true_range()
        df["atr_surge"] = df["atr"] / df["atr"].rolling(20).mean()

        # Volatility
        df["volatility"] = df["returns"].rolling(20).std()
        df["volatility_spike"] = df["volatility"] / df["volatility"].rolling(50).mean()

        # Candle patterns
        df["body"] = (df["close"] - df["open"]).abs()
        df["upper_wick"] = df["high"] - df[["close", "open"]].max(axis=1)
        df["lower_wick"] = df[["close", "open"]].min(axis=1) - df["low"]
        df["doji"] = (
            df["body"] < df["high_low_ratio"].rolling(50).mean() * 0.1
        ).astype(int)

        # Session indicators
        df["hour"] = df.index.hour
        df["is_london"] = ((df["hour"] >= 8) & (df["hour"] < 17)).astype(int)
        df["is_newyork"] = ((df["hour"] >= 13) & (df["hour"] < 22)).astype(int)
        df["overlap"] = ((df["hour"] >= 13) & (df["hour"] < 17)).astype(int)

        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.bfill().fillna(0)

        return df

