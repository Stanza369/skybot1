import json
import time
import random
import threading
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
import os

@dataclass
class Trader:
    id: str
    name: str
    country: str
    experience: str
    followers: int
    win_rate: float
    total_trades: int
    avg_roi: float
    preferred_symbols: List[str]
    risk_level: str
    is_active: bool = True

@dataclass
class Trade:
    trader_id: str
    symbol: str
    action: str
    entry_price: float
    volume: float
    timestamp: float

class SocialTradingDatabase:
    def __init__(self):
        self.lock = threading.Lock()
        self.traders: Dict[str, Trader] = {}
        self.trades: List[Trade] = []
        self._init_demo_traders()

    def _init_demo_traders(self):
        self.traders = {
            "T1": Trader("T1", "GoldMaster", "UK", "professional", 15420, 68.5, 2847, 12.3, ["XAUUSD"], "medium"),
            "T2": Trader("T2", "ScalperPro", "US", "professional", 8920, 72.1, 15234, 8.7, ["XAUUSD", "BTCUSD"], "high"),
            "T3": Trader("T3", "SwingKing", "AU", "intermediate", 3420, 58.3, 892, 15.2, ["XAUUSD"], "low")
        }

    def record_trade(self, trader_id: str, symbol: str, action: str, price: float, volume: float):
        with self.lock:
            new_trade = Trade(trader_id, symbol, action, price, volume, time.time())
            self.trades.append(new_trade)
            if len(self.trades) > 1000:
                self.trades.pop(0)

    def get_top_traders(self) -> List[Dict]:
        return [asdict(t) for t in self.traders.values()]

    def get_recent_trades(self, limit=10) -> List[Dict]:
        with self.lock:
            return [{"trader": self.traders.get(t.trader_id, "Unknown").name, 
                     "symbol": t.symbol, "action": t.action, 
                     "time": datetime.fromtimestamp(t.timestamp).strftime("%H:%M")} 
                    for t in self.trades[-limit:]]

class SocialIntelligenceEngine:
    def __init__(self, db: SocialTradingDatabase):
        self.db = db

    def get_social_bias(self, symbol: str = "XAUUSD") -> Dict:
        with self.db.lock:
            symbol_trades = [t for t in self.db.trades if t.symbol == symbol]
            
        if not symbol_trades:
            # Simulated market sentiment if no real data
            buy_ratio = random.uniform(40, 75)
            total = 124
        else:
            buys = len([t for t in symbol_trades if t.action == "BUY"])
            total = len(symbol_trades)
            buy_ratio = (buys / total) * 100

        weighted_buy = 0
        weighted_sell = 0
        for tid, trader in self.db.traders.items():
            # Heuristic: top traders bias the "Smart Money" flow
            weight = trader.win_rate / 100
            if buy_ratio > 50:
                weighted_buy += weight
            else:
                weighted_sell += weight

        return {
            "buy_ratio": buy_ratio,
            "sell_ratio": 100 - buy_ratio,
            "consensus": "BUY" if buy_ratio > 55 else ("SELL" if buy_ratio < 45 else "HOLD"),
            "confidence": min(95, 50 + abs(50 - buy_ratio) * 2),
            "total_traders": total
        }

def social_simulation_loop(db: SocialTradingDatabase):
    """Simulates other traders around the world taking positions."""
    symbols = ["XAUUSD", "EURUSD", "BTCUSD"]
    actions = ["BUY", "SELL"]
    while True:
        trader_id = random.choice(list(db.traders.keys()))
        symbol = random.choice(symbols)
        action = random.choice(actions)
        db.record_trade(trader_id, symbol, action, 2650.0, 0.1)
        time.sleep(random.uniform(5, 15))