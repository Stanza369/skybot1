import numpy as np
import pandas as pd
import logging
from typing import Dict, List
from predictors import MarkovForexPredictor, BayesianForexPredictor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Backtester:
    def __init__(self, config, strategy_engine, risk_manager):
        self.config = config
        self.strategy_engine = strategy_engine
        self.risk_manager = risk_manager

    def run(self, df: pd.DataFrame, initial_balance: float = 10000) -> Dict:
        balance = float(initial_balance)
        trades: List[Dict] = []
        equity_curve = [balance]

        # Walk-forward backtest using the repo StrategyEngine output.
        # This ensures the scalping layer (and existing ICT/AI confluence) impacts backtest trades.
        for i in range(200, len(df) - self.config.PREDICTION_HORIZON):
            window_df = df.iloc[: i + 1]

            latest = window_df.iloc[-1]
            # Backtester is dataframe-only; StrategyEngine expects a data_collector.
            # Use a lightweight shim that returns df unchanged.
            class _Shim:
                @staticmethod
                def compute_features(x):
                    return x

                @staticmethod
                def get_rates(_tf, _count):
                    return pd.DataFrame()

            signal = self.strategy_engine.generate_signal(window_df, data_collector=_Shim())
            if not signal or signal.get("signal") == "NEUTRAL":
                continue


            # Backtester expects fixed keys.
            signal.setdefault("signal", "NEUTRAL")
            signal.setdefault("entry", float(latest.get("close", 0.0)))
            signal.setdefault("stop_loss", float(signal.get("stop_loss", 0.0) or 0.0))
            signal.setdefault("take_profit", float(signal.get("take_profit", 0.0) or 0.0))

            validation = self.risk_manager.validate_trade(signal, balance)

            if validation.get("allowed"):
                lots = validation.get("lots", 0.01)
                trade_result = self._simulate_trade(window_df, signal, lots)
                balance += trade_result["profit"]
                trades.append(trade_result)
                # Update expects pnl float, not the full trade dict.
                self.risk_manager.update_trade_result(trade_result.get("profit", 0.0))


            equity_curve.append(balance)

            # daily reset
            if i > 0 and window_df.index[-1].day != df.index[i - 1].day:
                self.risk_manager.reset_daily()

        metrics = self._calculate_metrics(trades, equity_curve, initial_balance)
        return metrics

    def _simulate_trade(self, df: pd.DataFrame, signal: Dict, lots: float) -> Dict:
        entry_price = float(signal["entry"])
        stop_price = float(signal["stop_loss"])
        target_price = float(signal["take_profit"])

        exit_idx = None
        exit_price = None
        exit_reason = None

        for j in range(1, len(df)):
            future_candle = df.iloc[j]
            if signal["signal"] == "BUY":
                if float(future_candle["low"]) <= stop_price:
                    exit_price = stop_price
                    exit_reason = "STOP_LOSS"
                    exit_idx = j
                    break
                if float(future_candle["high"]) >= target_price:
                    exit_price = target_price
                    exit_reason = "TAKE_PROFIT"
                    exit_idx = j
                    break
            else:
                if float(future_candle["high"]) >= stop_price:
                    exit_price = stop_price
                    exit_reason = "STOP_LOSS"
                    exit_idx = j
                    break
                if float(future_candle["low"]) <= target_price:
                    exit_price = target_price
                    exit_reason = "TAKE_PROFIT"
                    exit_idx = j
                    break

        if exit_price is None:
            exit_price = float(df.iloc[-1]["close"])
            exit_reason = "END_OF_DATA"
            exit_idx = len(df) - 1

        if signal["signal"] == "BUY":
            pips = (exit_price - entry_price) * 100
        else:
            pips = (entry_price - exit_price) * 100

        profit = float(pips * lots * 0.01)

        return {
            "entry_time": df.index[0],
            "exit_time": df.index[exit_idx] if exit_idx is not None else df.index[-1],
            "entry_price": entry_price,
            "exit_price": exit_price,
            "pips": float(pips),
            "profit": profit,
            "exit_reason": exit_reason,
            "signal": signal["signal"],
        }

    def _calculate_metrics(self, trades: List[Dict], equity_curve: List[float], initial_balance: float) -> Dict:
        if not trades:
            return {"error": "No trades executed"}

        winning = [t for t in trades if t["profit"] > 0]
        losing = [t for t in trades if t["profit"] <= 0]

        total_profit = sum(t["profit"] for t in winning)
        total_loss = abs(sum(t["profit"] for t in losing))

        win_rate = len(winning) / len(trades)
        profit_factor = (total_profit / total_loss) if total_loss > 0 else float("inf")

        peak = max(equity_curve)
        drawdowns = [(peak - eq) / peak for eq in equity_curve if peak > 0]
        max_drawdown = max(drawdowns) if drawdowns else 0.0

        returns = np.diff(equity_curve) / np.array(equity_curve[:-1])
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0.0

        net_profit = equity_curve[-1] - initial_balance

        return {
            "total_trades": len(trades),
            "winning_trades": len(winning),
            "losing_trades": len(losing),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "net_profit": net_profit,
            "return_pct": (net_profit / initial_balance) * 100 if initial_balance else 0,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": float(sharpe),
            "best_trade": max((t["profit"] for t in trades), default=0),
            "worst_trade": min((t["profit"] for t in trades), default=0),
            "avg_win": total_profit / len(winning) if winning else 0,
            "avg_loss": total_loss / len(losing) if losing else 0,
        }

