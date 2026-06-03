"""
backtester.py - Backtesting framework for AI models
"""
import argparse
import json
import numpy as np
import pandas as pd
import torch
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, initial_balance=10000):
        self.initial_balance = initial_balance
        self.equity = initial_balance
        self.trades = []

    def execute_backtest(self, df, predictions):
        open_trade = None
        for idx, pred in enumerate(predictions):
            if idx >= len(df):
                break
            price = df.iloc[idx]['close']
            signal = pred['direction']
            confidence = pred.get('confidence', 50)

            if confidence < 55:
                continue

            if open_trade and open_trade['signal'] != signal:
                pnl = (price - open_trade['price']) * (1 if open_trade['signal'] == 'BUY' else -1)
                self.equity += pnl * 100
                self.trades.append({'pnl': pnl})
                open_trade = None

            if not open_trade and signal in ['BUY', 'SELL']:
                open_trade = {'signal': signal, 'price': price}

        metrics = self._calculate_metrics()
        return metrics

    def _calculate_metrics(self):
        if not self.trades:
            return {'total_trades': 0, 'return': 0}
        
        pnls = [t['pnl'] for t in self.trades]
        return {
            'total_trades': len(self.trades),
            'return': float(self.equity - self.initial_balance),
            'win_rate': len([p for p in pnls if p > 0]) / len(pnls) * 100
        }

def main():
    logger.info("Backtesting framework ready")

if __name__ == '__main__':
    main()
