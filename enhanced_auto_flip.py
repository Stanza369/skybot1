import numpy as np
from typing import Dict, List, Tuple
from functools import lru_cache
import time

class AdvancedRiskManager:
    """Institutional risk management using Kelly Criterion and Dynamic Volatility."""
    def __init__(self, initial_balance: float = 10000):
        self.balance = initial_balance
        self.win_rate = 0.55  # Default historical win rate
        self.avg_win = 50.0
        self.avg_loss = 25.0

    def calculate_kelly_size(self, confidence: float) -> float:
        """Calculates optimal lot size using a fractional Kelly Criterion."""
        if self.avg_loss <= 0: return 0.01
        
        # b = odds (win amount / loss amount)
        b = self.avg_win / self.avg_loss
        p = self.win_rate * (0.5 + confidence) # Adjust p based on AI confidence
        q = 1 - p
        
        kelly_f = (p * b - q) / b if b > 0 else 0
        # Use 1/4 Kelly for institutional safety (aggressive growth but low ruin probability)
        safe_f = max(0.01, min(0.10, kelly_f * 0.25))
        
        return round(safe_f, 2)

class EnhancedFlipDetector:
    """Heuristic Engine to determine if a reversal is high-probability."""
    def __init__(self):
        self.weights = {
            'momentum': 0.30,
            'volume': 0.20,
            'liquidity': 0.20,
            'trend': 0.30
        }

    def get_flip_probability(self, indicators: Dict) -> Tuple[float, List[str]]:
        score = 0.0
        reasons = []

        # Momentum Check
        if abs(indicators.get('rsi', 50) - 50) > 20:
            score += self.weights['momentum']
            reasons.append("Extreme RSI Stretch")

        # Volume Check
        if indicators.get('volume_ratio', 1.0) > 1.8:
            score += self.weights['volume']
            reasons.append("Institutional Volume Spike")

        # Trend/Price Action Check
        if indicators.get('price_position', 0.5) > 0.9 or indicators.get('price_position', 0.5) < 0.1:
            score += self.weights['trend']
            reasons.append("Price at Range Extremes")

        return min(1.0, score), reasons

class MarketDataCache:
    """High-performance price caching to reduce API overhead."""
    @lru_cache(maxsize=128)
    def get_effective_price(self, symbol: str, ttl_bucket: int) -> float:
        """
        Returns a price cached for a specific time window.
        ttl_bucket = time.time() // 5 (5-second cache)
        """
        # In production, this would call MetaTrader5.symbol_info_tick
        return 2650.0 + np.random.randn()