import time
from dataclasses import dataclass
from typing import Optional

from .confluence_engine_fixed import ConfluenceDashboardEngine



@dataclass
class Prediction:
    side: Optional[str]
    confidence: float
    ts: float
    reasons: str = ""


class AIPredictor:

    """Adapter so existing `main.py`-style code can call `.predict()`.

    This bot now uses the rule-based confluence engine, but keeps the same interface.
    """

    def __init__(self, symbol: str = "XAUUSD"):
        self.engine = ConfluenceDashboardEngine(symbol)

    def predict(self, min_confidence: float = 0.70) -> Prediction:
        sig = self.engine.evaluate(min_confidence=min_confidence)
        return Prediction(side=sig.side, confidence=sig.confidence, ts=sig.ts, reasons=sig.reasons)
