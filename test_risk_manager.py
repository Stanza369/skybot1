import os
import sys
import pytest

# Ensure repo root is on sys.path for local test runs
ROOT = os.path.dirname(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from risk_manager import RiskManager



class DummyConfig:
    MAX_RISK_PER_TRADE = 0.02
    MAX_DAILY_RISK = 0.06
    MIN_LOT_SIZE = 0.0001
    MAX_LOT_SIZE = 0.1


def test_reset_daily():
    rm = RiskManager(DummyConfig)
    rm.daily_loss = 10
    rm.daily_trades = 5
    rm.consecutive_losses = 2

    rm.reset_daily()

    assert rm.daily_loss == 0
    assert rm.daily_trades == 0
    assert rm.consecutive_losses == 0


def test_daily_loss_guard_blocks_when_limit_reached():
    rm = RiskManager(DummyConfig)
    # limit = balance * MAX_DAILY_RISK
    balance = 10000
    limit = balance * DummyConfig.MAX_DAILY_RISK

    rm.daily_loss = limit
    allowed = rm.check_daily_limit(balance)

    assert allowed is False


def test_validate_trade_neutral_disallows():
    rm = RiskManager(DummyConfig)
    rm.daily_loss = 0

    signal = {
        "signal": "NEUTRAL",
        "entry": 1.0,
        "stop_loss": 0.95,
        "take_profit": 1.1,
        "ai_prediction": {"confidence": 0.9},
    }

    res = rm.validate_trade(signal, balance=10000)
    assert res["allowed"] is False

