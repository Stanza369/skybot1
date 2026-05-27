# backtester_advanced.py

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf


@dataclass
class BacktestTrade:
    entry_time: Any
    exit_time: Any
    type: str
    entry: float
    exit: float
    pnl: float
    result: str
    reason: str


class AdvancedBacktester:
    """Advanced backtesting module for the ICT-like signal pipeline.

    This backtester is intentionally lightweight:
    - downloads historical OHLCV with yfinance
    - scans historical candles using repo ICT modules + simple killzone gating
    - simulates trades with SL/TP and fixed pip-to-PnL approximation (same as repo demo)

    Notes:
    - This is not an execution-grade backtester (no tick data / spread / slippage model).
    """

    def __init__(self, *, initial_balance: float = 5.0, risk_percent: float = 2.0):
        self.initial_balance = float(initial_balance)
        self.risk_percent = float(risk_percent)

        self.balance = float(initial_balance)
        self.trades: List[BacktestTrade] = []
        self.equity_curve: List[Tuple[Any, float]] = []

    def download_historical_data(
        self,
        *,
        symbol: str = "GC=F",
        period: str = "6mo",
        interval: str = "5m",
    ) -> Optional[pd.DataFrame]:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)

        if df is None or df.empty:
            return None

        df.columns = [str(col).lower() for col in df.columns]
        df.index = pd.to_datetime(df.index)
        return df

    @staticmethod
    def _is_killzone(timestamp: pd.Timestamp) -> Tuple[bool, Optional[str]]:
        est_hour = timestamp.hour + timestamp.minute / 60
        if 3 <= est_hour <= 5:
            return True, "London"
        if 9.5 <= est_hour <= 11.5:
            return True, "NY AM"
        if 14 <= est_hour <= 16:
            return True, "NY PM"
        return False, None

    # --- ICT detectors (local, heuristic) ---
    @staticmethod
    def _find_nearest_swing_high_low(df: pd.DataFrame, index: int, *, period: int = 5) -> Tuple[Optional[float], Optional[float]]:
        if index < period * 2 + 1 or index >= len(df) - period - 1:
            return None, None

        highs = df["high"].values.astype(float)
        lows = df["low"].values.astype(float)

        swing_highs: List[float] = []
        swing_lows: List[float] = []

        for i in range(period, len(df) - period):
            if i < index - period * 3 or i >= index:
                continue
            if highs[i] == highs[i - period : i + period + 1].max():
                swing_highs.append(float(highs[i]))
            if lows[i] == lows[i - period : i + period + 1].min():
                swing_lows.append(float(lows[i]))

        if not swing_highs or not swing_lows:
            return None, None

        return max(swing_highs[-3:]), min(swing_lows[-3:])

    def _detect_liquidity_grab(self, df: pd.DataFrame, index: int) -> Optional[Dict[str, Any]]:
        if index < 2 or index >= len(df) - 1:
            return None

        recent_high, recent_low = self._find_nearest_swing_high_low(df, index, period=5)
        if recent_high is None or recent_low is None:
            return None

        cur = df.iloc[index]
        prev = df.iloc[index - 1]

        last_high = float(cur["high"])
        last_low = float(cur["low"])
        last_close = float(cur["close"])
        prev_close = float(prev["close"])

        if last_high > float(recent_high) and last_close < float(recent_high) and last_close < prev_close:
            return {"type": "SELL_SIDE_GRAB", "grabbed_level": float(recent_high), "strength": "HIGH"}

        if last_low < float(recent_low) and last_close > float(recent_low) and last_close > prev_close:
            return {"type": "BUY_SIDE_GRAB", "grabbed_level": float(recent_low), "strength": "HIGH"}

        return None

    def _find_order_block(self, df: pd.DataFrame, index: int) -> Optional[Dict[str, Any]]:
        if index < 2 or index >= len(df) - 2:
            return None

        # displacement candle at index+1, OB at index
        # Use average body as displacement baseline.
        bodies = (df["close"].astype(float) - df["open"].astype(float)).abs()
        lookback = bodies.iloc[max(0, index - 50) : index + 1]
        avg_body = float(lookback.mean()) if len(lookback) else 0.0
        if avg_body <= 0:
            return None

        current = df.iloc[index]
        next_candle = df.iloc[index + 1]

        next_body = float((next_candle["close"] - next_candle["open"]).__abs__())
        displacement_body_mult = 1.5
        if next_body <= avg_body * displacement_body_mult:
            return None

        if float(next_candle["close"]) > float(next_candle["open"]):
            return {
                "type": "BULLISH",
                "high": float(current["high"]),
                "low": float(current["low"]),
                "entry": float(current["low"]),
                "stop": float(current["low"]) - (float(current["high"]) - float(current["low"])),
                "strength": "HIGH",
            }

        return {
            "type": "BEARISH",
            "high": float(current["high"]),
            "low": float(current["low"]),
            "entry": float(current["high"]),
            "stop": float(current["high"]) + (float(current["high"]) - float(current["low"])),
            "strength": "HIGH",
        }

    def _find_fvg(self, df: pd.DataFrame, index: int) -> Optional[Dict[str, Any]]:
        if index < 2:
            return None

        c1 = df.iloc[index - 2]
        c3 = df.iloc[index]

        if float(c3["low"]) > float(c1["high"]):
            return {"type": "BULLISH", "top": float(c3["low"]), "bottom": float(c1["high"])}
        if float(c3["high"]) < float(c1["low"]):
            return {"type": "BEARISH", "top": float(c1["low"]), "bottom": float(c3["high"])}
        return None

    def _get_signal(self, df: pd.DataFrame, index: int) -> Optional[Dict[str, Any]]:
        if index < 20:
            return None

        timestamp = df.index[index]
        ok, _zone = self._is_killzone(timestamp)
        if not ok:
            return None

        cur_price = float(df.iloc[index]["close"])

        liq = self._detect_liquidity_grab(df, index)
        if liq:
            if liq["type"] == "BUY_SIDE_GRAB":
                return {"action": "BUY", "entry": cur_price, "sl": cur_price - 0.0010, "tp": cur_price + 0.0020}
            return {"action": "SELL", "entry": cur_price, "sl": cur_price + 0.0010, "tp": cur_price - 0.0020}

        ob = self._find_order_block(df, index)
        if ob:
            if ob["type"] == "BULLISH":
                return {"action": "BUY", "entry": cur_price, "sl": ob["stop"], "tp": cur_price + 0.0020}
            return {"action": "SELL", "entry": cur_price, "sl": ob["stop"], "tp": cur_price - 0.0020}

        fvg = self._find_fvg(df, index)
        if fvg:
            if fvg["type"] == "BULLISH" and cur_price <= float(fvg["bottom"]) * 1.001:
                return {"action": "BUY", "entry": float(fvg["bottom"]), "sl": float(fvg["bottom"]) - 0.0010, "tp": float(fvg["top"]) + 0.0010}
            if fvg["type"] == "BEARISH" and cur_price >= float(fvg["top"]) * 0.999:
                return {"action": "SELL", "entry": float(fvg["top"]), "sl": float(fvg["top"]) + 0.0010, "tp": float(fvg["bottom"]) - 0.0010}

        # fallback basic momentum
        cur = df.iloc[index]
        prev = df.iloc[index - 1]
        if float(cur["close"]) > float(prev["close"]) and float(cur["close"]) > float(cur["open"]):
            return {"action": "BUY", "entry": cur_price, "sl": cur_price - 0.0010, "tp": cur_price + 0.0020}
        if float(cur["close"]) < float(prev["close"]) and float(cur["close"]) < float(cur["open"]):
            return {"action": "SELL", "entry": cur_price, "sl": cur_price + 0.0010, "tp": cur_price - 0.0020}

        return None

    def calculate_position_size(self, entry: float, stop_loss: float) -> float:
        stop_pips = abs(float(entry) - float(stop_loss)) * 10000
        if stop_pips <= 0:
            return 0.01

        risk_amount = self.balance * (self.risk_percent / 100.0)
        lot_size = risk_amount / (stop_pips * 0.10)

        if self.balance < 25:
            lot_size = min(lot_size, 0.02)
        elif self.balance < 100:
            lot_size = min(lot_size, 0.05)
        else:
            lot_size = min(lot_size, 0.10)

        return float(max(0.01, round(lot_size, 2)))

    def backtest(self, df: pd.DataFrame, *, commission: float = 0.0) -> Dict[str, Any]:
        self.balance = float(self.initial_balance)
        self.trades = []
        self.equity_curve = [(df.index[0], self.balance)]

        position: Optional[Dict[str, Any]] = None
        entry_time = None

        for i in range(len(df)):
            current_price = float(df.iloc[i]["close"])

            if position is not None:
                action = position["type"]
                if action == "BUY":
                    if current_price <= position["sl"]:
                        pips = (position["sl"] - position["entry"]) * 10000
                        pnl = pips * position["lot"] * 0.10 - commission
                        self.balance += pnl
                        self.trades.append(
                            BacktestTrade(entry_time, df.index[i], action, position["entry"], position["sl"], pnl, "LOSS", "Stop Loss")
                        )
                        position = None
                    elif current_price >= position["tp"]:
                        pips = (position["tp"] - position["entry"]) * 10000
                        pnl = pips * position["lot"] * 0.10 - commission
                        self.balance += pnl
                        self.trades.append(
                            BacktestTrade(entry_time, df.index[i], action, position["entry"], position["tp"], pnl, "PROFIT", "Take Profit")
                        )
                        position = None
                else:
                    if current_price >= position["sl"]:
                        pips = (position["entry"] - position["sl"]) * 10000
                        pnl = pips * position["lot"] * 0.10 - commission
                        self.balance += pnl
                        self.trades.append(
                            BacktestTrade(entry_time, df.index[i], action, position["entry"], position["sl"], pnl, "LOSS", "Stop Loss")
                        )
                        position = None
                    elif current_price <= position["tp"]:
                        pips = (position["entry"] - position["tp"]) * 10000
                        pnl = pips * position["lot"] * 0.10 - commission
                        self.balance += pnl
                        self.trades.append(
                            BacktestTrade(entry_time, df.index[i], action, position["entry"], position["tp"], pnl, "PROFIT", "Take Profit")
                        )
                        position = None

            if position is None:
                signal = self._get_signal(df, i)
                if signal:
                    lot = self.calculate_position_size(signal["entry"], signal["sl"])
                    position = {
                        "type": signal["action"],
                        "entry": float(signal["entry"]),
                        "sl": float(signal["sl"]),
                        "tp": float(signal["tp"]),
                        "lot": lot,
                    }
                    entry_time = df.index[i]

            # equity curve sampling: every 1 hour if 5m candles
            if i % 12 == 0 and i < len(df) - 1:
                self.equity_curve.append((df.index[i], self.balance))

        return self.calculate_statistics()

    def calculate_statistics(self) -> Dict[str, Any]:
        if not self.trades:
            return {"error": "No trades executed"}

        total_trades = len(self.trades)
        win_trades = [t for t in self.trades if t.result == "PROFIT"]
        loss_trades = [t for t in self.trades if t.result == "LOSS"]

        win_rate = (len(win_trades) / total_trades) * 100 if total_trades else 0
        net_profit = sum(t.pnl for t in self.trades)
        profit_factor = (
            abs(sum(t.pnl for t in win_trades) / sum(t.pnl for t in loss_trades))
            if sum(t.pnl for t in loss_trades) != 0
            else 0
        )

        equity_vals = [v for _, v in self.equity_curve]
        peak = equity_vals[0] if equity_vals else self.initial_balance
        max_drawdown = 0.0
        for v in equity_vals:
            peak = max(peak, v)
            dd = (peak - v) / peak * 100 if peak else 0
            max_drawdown = max(max_drawdown, dd)

        roi = ((self.balance - self.initial_balance) / self.initial_balance) * 100 if self.initial_balance else 0

        return {
            "initial_balance": self.initial_balance,
            "final_balance": self.balance,
            "total_return": roi,
            "net_profit": net_profit,
            "total_trades": total_trades,
            "winning_trades": len(win_trades),
            "losing_trades": len(loss_trades),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "max_drawdown": max_drawdown,
            "expectancy": net_profit / total_trades if total_trades else 0,
        }

    def save_results(self, stats: Dict[str, Any], *, filename: str = "backtest_results.json") -> None:
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, default=str)


def run_backtest() -> None:
    symbol = input("Symbol (default GC=F): ").strip() or "GC=F"
    period = input("Period (1mo, 3mo, 6mo, 1y, default 3mo): ").strip() or "3mo"
    balance = float(input("Initial balance (default 5): ").strip() or "5")
    risk = float(input("Risk percent (default 2): ").strip() or "2")

    backtester = AdvancedBacktester(initial_balance=balance, risk_percent=risk)
    data = backtester.download_historical_data(symbol=symbol, period=period, interval="5m")
    if data is None:
        print("No data downloaded.")
        return

    stats = backtester.backtest(data)
    print(json.dumps(stats, indent=2, default=str))

    save_choice = input("Save results to file? (y/n): ").strip().lower()
    if save_choice == "y":
        backtester.save_results(stats)
        print("Saved to backtest_results.json")


if __name__ == "__main__":
    run_backtest()

