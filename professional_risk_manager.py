from __future__ import annotations

"""professional_risk_manager.py

Institutional-grade risk management (blueprint implementation).

This module is repo-rooted (not trading-dashboard/backend) because the
current bot code uses `risk_manager.py` at repo root.

Key idea:
- Provide a ProfessionalRiskManager with:
  - assess_trade_risk(signal, market_data, session)
  - update_after_trade(pnl)
  - get_risk_report()

It is designed to be usable by the existing RiskManager wrapper.
"""

import time
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd


class RiskMode(Enum):
    CONSERVATIVE = "conservative"   # 0.5% max risk
    NORMAL = "normal"               # 1% max risk
    AGGRESSIVE = "aggressive"       # 2% max risk
    PROTECT = "protect"             # 0.25% max risk


class MarketRegime(Enum):
    CALM = "calm"
    NORMAL = "normal"
    VOLATILE = "volatile"
    DANGEROUS = "dangerous"


@dataclass
class PositionSizer:
    account_balance: float = 10000.0

    def __post_init__(self) -> None:
        self.peak_balance = float(self.account_balance)
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.daily_pnl = 0.0
        self.today = datetime.now().date()

        self.base_risk_levels = {
            RiskMode.CONSERVATIVE: 0.5,
            RiskMode.NORMAL: 1.0,
            RiskMode.AGGRESSIVE: 2.0,
            RiskMode.PROTECT: 0.25,
        }

    def calculate_position_size(
        self,
        *,
        signal_confidence: float,
        stop_loss_pips: float,
        atr: float,
        volatility_ratio: float,
        risk_mode: RiskMode,
        session: str,
    ) -> Tuple[float, float]:
        """Return (lot_size, final_risk_percent)."""

        base_risk = self.base_risk_levels[risk_mode]

        confidence_mult = 0.5 + (float(signal_confidence) * 1.0)
        confidence_mult = min(1.5, max(0.5, confidence_mult))

        if volatility_ratio > 2.0:
            vol_mult = 0.3
        elif volatility_ratio > 1.5:
            vol_mult = 0.6
        elif volatility_ratio > 1.0:
            vol_mult = 0.8
        elif volatility_ratio < 0.5:
            vol_mult = 1.2
        else:
            vol_mult = 1.0

        streak_mult = self._get_streak_multiplier()
        session_mult = self._get_session_multiplier(session)
        drawdown_mult = self._get_drawdown_multiplier()

        final_risk_percent = (
            base_risk
            * confidence_mult
            * vol_mult
            * streak_mult
            * session_mult
            * drawdown_mult
        )

        final_risk_percent = max(0.25, min(5.0, final_risk_percent))

        risk_amount = float(self.account_balance) * (final_risk_percent / 100.0)

        pip_value = 0.10  # repo assumption for gold
        if stop_loss_pips <= 0:
            return 0.01, final_risk_percent

        position_size = risk_amount / (float(stop_loss_pips) * pip_value)

        position_size = round(float(position_size), 2)
        position_size = max(0.01, min(position_size, self._get_max_lot_size()))

        return float(position_size), float(final_risk_percent)

    def _get_streak_multiplier(self) -> float:
        if self.consecutive_losses >= 5:
            return 0.3
        if self.consecutive_losses >= 3:
            return 0.6
        if self.consecutive_losses >= 1:
            return 0.8
        if self.consecutive_wins >= 5:
            return 1.2
        if self.consecutive_wins >= 3:
            return 1.1
        return 1.0

    def _get_session_multiplier(self, session: str) -> float:
        multipliers = {
            "london": 1.2,
            "ny_am": 1.3,
            "ny_pm": 0.8,
            "asian": 0.5,
            "news": 0.3,
        }
        return float(multipliers.get(session, 1.0))

    def _get_drawdown_multiplier(self) -> float:
        if self.peak_balance <= 0:
            return 1.0

        drawdown = (self.peak_balance - self.account_balance) / self.peak_balance

        if drawdown > 0.20:
            return 0.2
        if drawdown > 0.15:
            return 0.4
        if drawdown > 0.10:
            return 0.6
        if drawdown > 0.05:
            return 0.8
        return 1.0

    def _get_max_lot_size(self) -> float:
        bal = float(self.account_balance)
        if bal < 100:
            return 0.02
        if bal < 500:
            return 0.10
        if bal < 2000:
            return 0.50
        if bal < 10000:
            return 1.00
        return 2.00

    def update_trade_result(self, pnl: float) -> None:
        pnl = float(pnl)
        self.account_balance += pnl
        self.daily_pnl += pnl

        self.peak_balance = max(self.peak_balance, self.account_balance)

        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

        current_date = datetime.now().date()
        if current_date != self.today:
            self.daily_pnl = 0
            self.today = current_date


class VolatilityManager:
    def __init__(self) -> None:
        self.regime = MarketRegime.NORMAL

    def analyze_market(self, data: pd.DataFrame) -> Dict[str, float | str]:
        if data is None or len(data) < 20:
            return {
                "regime": MarketRegime.NORMAL,
                "volatility_ratio": 1.0,
                "current_atr": 0.0,
                "avg_atr": 0.0,
                "risk_multiplier": 1.0,
            }

        high = data["high"]
        low = data["low"]
        close = data["close"]

        high_low = high - low
        high_close = (high - close.shift()).abs()
        low_close = (low - close.shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        current_atr = float(tr.rolling(14).mean().iloc[-1])
        atr_20 = tr.rolling(20).mean()
        avg_atr = float(atr_20.mean())

        volatility_ratio = current_atr / avg_atr if avg_atr > 0 else 1.0

        if volatility_ratio > 2.5:
            regime = MarketRegime.DANGEROUS
        elif volatility_ratio > 1.8:
            regime = MarketRegime.VOLATILE
        elif volatility_ratio > 0.8:
            regime = MarketRegime.NORMAL
        else:
            regime = MarketRegime.CALM

        # Spread-based downgrade if available
        if "spread" in data.columns:
            current_spread = float(data["spread"].iloc[-1])
            avg_spread = float(data["spread"].rolling(50).mean().iloc[-1])
            spread_ratio = current_spread / avg_spread if avg_spread > 0 else 1.0
            if spread_ratio > 2.0:
                regime = MarketRegime.DANGEROUS

        self.regime = regime
        return {
            "regime": regime,
            "volatility_ratio": float(volatility_ratio),
            "current_atr": float(current_atr),
            "avg_atr": float(avg_atr),
            "risk_multiplier": self._get_risk_multiplier(regime),
        }

    def _get_risk_multiplier(self, regime: MarketRegime) -> float:
        multipliers = {
            MarketRegime.CALM: 1.2,
            MarketRegime.NORMAL: 1.0,
            MarketRegime.VOLATILE: 0.6,
            MarketRegime.DANGEROUS: 0.2,
        }
        return float(multipliers.get(regime, 1.0))


class DrawdownProtector:
    def __init__(self, max_daily_loss: float = 5.0, max_drawdown: float = 20.0):
        self.max_daily_loss_percent = float(max_daily_loss)
        self.max_drawdown_percent = float(max_drawdown)
        self.initial_balance = 0.0
        self.peak_balance = 0.0
        self.daily_start_balance = 0.0
        self.today = datetime.now().date()

    def update(self, current_balance: float) -> None:
        if self.initial_balance == 0:
            self.initial_balance = float(current_balance)
            self.peak_balance = float(current_balance)
            self.daily_start_balance = float(current_balance)

        self.peak_balance = max(self.peak_balance, float(current_balance))

        current_date = datetime.now().date()
        if current_date != self.today:
            self.daily_start_balance = float(current_balance)
            self.today = current_date

    def check_limits(self, current_balance: float) -> Tuple[bool, str]:
        current_balance = float(current_balance)

        if self.daily_start_balance <= 0 or self.peak_balance <= 0:
            return True, "OK"

        daily_loss = self.daily_start_balance - current_balance
        daily_loss_percent = (daily_loss / self.daily_start_balance) * 100.0

        if daily_loss_percent >= self.max_daily_loss_percent:
            return False, f"Daily loss limit reached: {daily_loss_percent:.1f}% > {self.max_daily_loss_percent}%"

        drawdown = self.peak_balance - current_balance
        drawdown_percent = (drawdown / self.peak_balance) * 100.0

        if drawdown_percent >= self.max_drawdown_percent:
            return False, f"Max drawdown reached: {drawdown_percent:.1f}% > {self.max_drawdown_percent}%"

        return True, "OK"


class SpreadProtector:
    def __init__(self, max_spread_pips: float = 50, max_slippage_pips: float = 5):
        self.max_spread_pips = float(max_spread_pips)
        self.max_slippage_pips = float(max_slippage_pips)

    def is_spread_ok(self, current_spread: float) -> Tuple[bool, str]:
        current_spread = float(current_spread)
        if current_spread > self.max_spread_pips:
            return False, f"Spread too high: {current_spread:.1f} pips > {self.max_spread_pips}"
        return True, "OK"


class ConfidenceRiskAdapter:
    def __init__(self):
        self.confidence_tiers = {
            "very_low": (0.0, 0.55, 0.25),
            "low": (0.55, 0.65, 0.5),
            "medium": (0.65, 0.75, 0.8),
            "high": (0.75, 0.85, 1.0),
            "very_high": (0.85, 1.0, 1.3),
        }

    def get_risk_multiplier(self, confidence: float) -> float:
        c = float(confidence)
        for _name, (min_conf, max_conf, mult) in self.confidence_tiers.items():
            if min_conf <= c < max_conf:
                return float(mult)
        return 0.5

    def should_trade(self, confidence: float) -> Tuple[bool, str]:
        if float(confidence) < 0.55:
            return False, f"Confidence too low: {float(confidence):.1%}"
        return True, "OK"


class ProfessionalRiskManager:
    """BluePrint ProfessionalRiskManager.

    This implementation is focused on:
    - risk gating (drawdown + confidence)
    - dynamic position sizing
    - volatility regime adjustments

    Correlation, slippage, etc. are omitted intentionally in this first repo
    integration step because the dashboard bot does not provide the required
    exposure tracking inputs yet.
    """

    def __init__(self, initial_balance: float = 10000.0):
        self.position_sizer = PositionSizer(float(initial_balance))
        self.volatility_manager = VolatilityManager()
        self.drawdown_protector = DrawdownProtector()
        self.spread_protector = SpreadProtector()
        self.confidence_adapter = ConfidenceRiskAdapter()

        self.current_mode = RiskMode.NORMAL

        self.current_balance = float(initial_balance)
        self.trade_history = []

        self.drawdown_protector.update(self.current_balance)

    def assess_trade_risk(self, signal: Dict, market_data: pd.DataFrame, session: str) -> Dict:
        can_trade, reason = self.drawdown_protector.check_limits(self.current_balance)
        if not can_trade:
            return {"can_trade": False, "reason": reason}

        volatility = self.volatility_manager.analyze_market(market_data)

        # --- Execution-quality / spreads (input-driven) ---
        # Default to a conservative spread if nothing is provided.
        current_spread = float(
            signal.get("spread_before", signal.get("spread", 20.0)) or 20.0
        )

        if isinstance(market_data, pd.DataFrame) and "spread" in market_data.columns and len(market_data) > 0:
            try:
                current_spread = float(market_data["spread"].iloc[-1])
            except Exception:
                pass

        spread_ok, spread_reason = self.spread_protector.is_spread_ok(current_spread)
        if not spread_ok:
            return {
                "can_trade": False,
                "reason": spread_reason,
                "execution_quality_ok": False,
                "spread_before": current_spread,
            }

        # Optional slippage gate if caller provides slippage in pips.
        # (Execution engine should calculate this at fill time.)
        slippage_pips = signal.get("slippage_pips", None)
        if slippage_pips is not None:
            try:
                slippage_pips_val = float(slippage_pips)
                if slippage_pips_val > self.spread_protector.max_slippage_pips:
                    return {
                        "can_trade": False,
                        "reason": f"Excessive slippage: {slippage_pips_val:.1f} pips > {self.spread_protector.max_slippage_pips}",
                        "execution_quality_ok": False,
                        "slippage_pips": slippage_pips_val,
                    }
            except Exception:
                # If slippage parse fails, do not block.
                pass

        confidence = float(signal.get("confidence", 0.7))
        confidence_ok, conf_reason = self.confidence_adapter.should_trade(confidence)
        if not confidence_ok:
            return {"can_trade": False, "reason": conf_reason}

        # sizing inputs
        stop_loss_pips = float(signal.get("stop_loss_pips", 20))
        atr = float(volatility.get("current_atr", 0.0) or 0.0)
        vol_ratio = float(volatility.get("volatility_ratio", 1.0) or 1.0)

        position_size, risk_percent = self.position_sizer.calculate_position_size(
            signal_confidence=confidence,
            stop_loss_pips=stop_loss_pips,
            atr=atr,
            volatility_ratio=vol_ratio,
            risk_mode=self.current_mode,
            session=session,
        )

        volatility_mult = float(volatility.get("risk_multiplier", 1.0) or 1.0)
        final_position_size = position_size * volatility_mult
        final_position_size = round(final_position_size, 2)
        final_position_size = max(0.01, min(final_position_size, self.position_sizer._get_max_lot_size()))

        confidence_mult = self.confidence_adapter.get_risk_multiplier(confidence)
        final_risk_percent = float(risk_percent) * float(confidence_mult)

        return {
            "can_trade": True,
            "reason": "Risk assessment passed",
            "execution_quality_ok": True,
            "spread_before": current_spread,
            "position_size": float(final_position_size),
            "risk_percent": float(final_risk_percent),
            "adjusted_confidence": float(min(1.0, confidence * confidence_mult)),
            "volatility_regime": str(volatility["regime"].value),
            "volatility_ratio": float(volatility["volatility_ratio"]),
        }


    def update_after_trade(self, pnl: float) -> None:
        self.position_sizer.update_trade_result(pnl)
        self.current_balance = float(self.position_sizer.account_balance)
        self.drawdown_protector.update(self.current_balance)

        self.trade_history.append({"timestamp": time.time(), "pnl": float(pnl), "balance": self.current_balance})

    def get_risk_report(self) -> Dict:
        peak = float(self.position_sizer.peak_balance)
        cur = float(self.current_balance)
        drawdown = (peak - cur) / peak if peak > 0 else 0.0
        return {
            "current_balance": cur,
            "peak_balance": peak,
            "drawdown": float(drawdown),
            "daily_pnl": float(self.position_sizer.daily_pnl),
            "consecutive_wins": int(self.position_sizer.consecutive_wins),
            "consecutive_losses": int(self.position_sizer.consecutive_losses),
            "risk_mode": self.current_mode.value,
            "volatility_regime": self.volatility_manager.regime.value,
        }

