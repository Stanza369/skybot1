# risk_manager.py

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Any, Tuple, Optional


class RiskManager:
    """Compatibility RiskManager used by unit tests.

    The repo previously used AdvancedRiskManager. Tests expect:
    - class RiskManager
    - methods: reset_daily(), check_daily_limit(balance), validate_trade(signal, balance=...)

    This class implements those APIs while keeping behavior simple and deterministic.
    """

    def __init__(self, config):
        self.config = config

        # Daily state
        self.daily_loss = 0.0
        self.daily_trades = 0
        self.consecutive_losses = 0

    def reset_daily(self) -> None:
        self.daily_loss = 0.0
        self.daily_trades = 0
        self.consecutive_losses = 0

    def check_daily_limit(self, balance: float) -> bool:
        # Daily loss guard: absolute loss cap based on balance.
        limit = float(balance) * float(getattr(self.config, "MAX_DAILY_RISK", 0.0))
        return float(self.daily_loss) < limit

    def validate_trade(self, signal: Dict[str, Any], *, balance: float) -> Dict[str, Any]:
        # Disallow NEUTRAL signals
        if signal.get("signal") == "NEUTRAL":
            return {"allowed": False, "reason": "Signal is NEUTRAL", "lots": 0.0, "hard_stop": False}

        # Daily limit guard
        if not self.check_daily_limit(balance):
            return {
                "allowed": False,
                "reason": "Daily loss limit reached",
                "lots": 0.0,
                "hard_stop": True,
            }

        # Optional advanced sizing via blueprint risk manager (if available)
        lots = 0.01
        hard_stop = False
        risk_eval: Dict[str, Any] = {}

        if getattr(self, "_prof", None) is not None:
            try:
                # Blueprint requires: signal, market_data(df), session
                # Backtester/live currently call this without market_data, so we use
                # a minimal DataFrame-like fallback through None.
                # The blueprint handles missing spread/ATR gracefully.
                risk_eval = self._prof.assess_trade_risk(
                    signal=signal,
                    market_data=None,
                    session="london",
                )

                if not risk_eval.get("can_trade", False):
                    hard_stop = bool(risk_eval.get("hard_stop", False))
                    return {
                        "allowed": False,
                        "reason": risk_eval.get("reason", "Risk assessment failed"),
                        "lots": 0.0,
                        "hard_stop": hard_stop,
                    }

                lots = float(risk_eval.get("position_size", lots))
                hard_stop = False
            except Exception:
                # Fall back to deterministic behavior
                lots = 0.01

        return {"allowed": True, "reason": "OK", "lots": lots, "hard_stop": hard_stop}



# Keep the older API name used by main.py / other scripts.
class AdvancedRiskManager(RiskManager):
    """Repo-compatible AdvancedRiskManager.

    This class keeps the existing API used by tests and bot logic:
    - validate_trade(signal, balance=...)
    - reset_daily(), check_daily_limit(balance)
    - record_trade(pnl)

    It is now backed by the blueprint implementation in
    `professional_risk_manager.py` for risk assessment when possible.
    """

    def __init__(self, initial_balance: float = 5):
        # Create a lightweight config-like object for RiskManager.
        class _Cfg:
            MAX_DAILY_RISK = 0.06
            MAX_RISK_PER_TRADE = 0.02
            MIN_LOT_SIZE = 0.0001
            MAX_LOT_SIZE = 0.1

        super().__init__(_Cfg())

        # Blueprint manager
        try:
            from professional_risk_manager import ProfessionalRiskManager

            self._prof = ProfessionalRiskManager(initial_balance=float(initial_balance))
        except Exception:
            self._prof = None

        self.balance = float(initial_balance)
        self.peak = float(initial_balance)
        self.daily_pnl = 0.0
        self.trade_count = 0
        self.winning_trades = 0


    def can_trade(self) -> Tuple[bool, str]:
        drawdown = (self.peak - self.balance) / self.peak if self.peak > 0 else 0
        if drawdown > 0.20:
            return False, "Max drawdown reached"
        if self.balance < 3:
            return False, "Balance too low"
        return True, "OK"

    def record_trade(self, pnl: float) -> float:
        self.balance += float(pnl)
        self.peak = max(self.peak, self.balance)
        self.trade_count += 1
        if pnl > 0:
            self.winning_trades += 1
        # Track daily_loss as an absolute loss amount when pnl negative.
        if pnl < 0:
            self.daily_loss += abs(float(pnl))
        return self.balance

    def get_win_rate(self) -> float:
        if self.trade_count == 0:
            return 0.0
        return (self.winning_trades / self.trade_count) * 100

