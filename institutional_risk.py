from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Tuple


@dataclass
class RiskDecision:
    allowed: bool
    reason: str


class InstitutionalRiskManager:
    """Institutional-grade risk controls (daily loss, drawdown, trade limits, streak caps)."""

    def __init__(self, *, initial_balance: float = 10000.0) -> None:
        self.initial_balance = float(initial_balance)
        self.current_balance = float(initial_balance)
        self.peak_balance = float(initial_balance)

        self.daily_pnl = 0.0
        self.daily_trades = 0

        self.consecutive_losses = 0
        self.consecutive_wins = 0

        self.today = datetime.now().date()

        # Risk limits (USD)
        self.MAX_DAILY_LOSS = 500.0
        self.MAX_DRAWDOWN = 0.15
        self.MAX_CONSECUTIVE_LOSSES = 3
        self.MAX_DAILY_TRADES = 20

        # Base risk sizing
        self.BASE_RISK_PERCENT = 0.01  # 1%

    def _reset_if_new_day(self) -> None:
        current_date = datetime.now().date()
        if current_date != self.today:
            self.daily_pnl = 0.0
            self.daily_trades = 0
            self.today = current_date

    def can_trade(self) -> Tuple[bool, str]:
        self._reset_if_new_day()

        if self.daily_pnl < -self.MAX_DAILY_LOSS:
            return False, f"Daily loss limit reached: ${abs(self.daily_pnl):.2f}"

        if self.daily_trades >= self.MAX_DAILY_TRADES:
            return False, f"Daily trade limit reached: {self.daily_trades}"

        drawdown = (self.peak_balance - self.current_balance) / max(1e-9, self.peak_balance)
        if drawdown >= self.MAX_DRAWDOWN:
            return False, f"Max drawdown reached: {drawdown:.1%}"

        if self.consecutive_losses >= self.MAX_CONSECUTIVE_LOSSES:
            return False, f"Consecutive losses: {self.consecutive_losses}"

        return True, "OK"

    def calculate_position_size(self, *, confidence: float, volatility: float) -> float:
        """Return lots based on confidence+volatility+drawdown+streak."""

        confidence = float(confidence or 0.0)
        volatility = float(volatility or 1.0)

        base_risk = self.current_balance * self.BASE_RISK_PERCENT

        # confidence multiplier: 0.5x..1.5x if confidence in 0..1-ish
        confidence_mult = 0.5 + confidence
        confidence_mult = max(0.3, min(1.5, confidence_mult))

        # volatility multiplier (proxy regimes)
        if volatility > 2.0:
            vol_mult = 0.3
        elif volatility > 1.5:
            vol_mult = 0.6
        elif volatility > 1.0:
            vol_mult = 0.8
        else:
            vol_mult = 1.0

        # drawdown adjustment
        drawdown = (self.peak_balance - self.current_balance) / max(1e-9, self.peak_balance)
        dd_mult = max(0.3, 1.0 - drawdown)

        # streak adjustment
        if self.consecutive_losses >= 3:
            streak_mult = 0.3
        elif self.consecutive_losses >= 1:
            streak_mult = 0.7
        else:
            streak_mult = 1.0

        risk_amount = base_risk * confidence_mult * vol_mult * dd_mult * streak_mult

        # Convert risk to lots (repo uses a Gold-ish heuristic: stop_pips=20, $0.10 per 0.01 lot)
        stop_pips = 20
        dollars_per_lot_per_stop = stop_pips * 0.10 / 0.01
        # risk_amount $ => lots
        lot_size = (risk_amount / max(1e-9, dollars_per_lot_per_stop))

        # Account-based caps
        if self.current_balance < 1000:
            cap = 0.05
        elif self.current_balance < 5000:
            cap = 0.10
        elif self.current_balance < 20000:
            cap = 0.25
        else:
            cap = 0.50

        lot_size = min(lot_size, cap)
        return max(0.01, round(lot_size, 2))

    def update_trade(self, pnl: float) -> None:
        self._reset_if_new_day()

        pnl = float(pnl or 0.0)
        self.current_balance += pnl
        self.daily_pnl += pnl
        self.daily_trades += 1

        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance

