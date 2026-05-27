# ict_strategy.py
import pandas as pd
import numpy as np

class ICTStrategy:
    def __init__(self, data):
        """
        Initialize ICT Strategy with market data
        data: pandas DataFrame with OHLC data
        """
        self.data = data
        
    def analyze(self, current_hour):
        """
        Analyze market and return trading signal
        current_hour: current EST hour (for killzone checking)
        """
        if self.data is None or len(self.data) < 20:
            return None
        
        # Get last few candles
        last_candle = self.data.iloc[-1]
        prev_candle = self.data.iloc[-2]
        
        # Simple ICT-inspired logic
        # Look for price rejection and momentum
        
        # Calculate candle body
        last_body = abs(last_candle['close'] - last_candle['open'])
        prev_body = abs(prev_candle['close'] - prev_candle['open'])
        
        # Check for bullish signal (higher low + bullish close)
        if (last_candle['close'] > last_candle['open'] and 
            last_candle['close'] > prev_candle['close'] and
            last_candle['low'] > prev_candle['low']):
            
            return {
                'action': 'BUY',
                'entry': last_candle['close'],
                'sl': last_candle['low'] - (last_candle['high'] - last_candle['low']) * 0.5,
                'tp': last_candle['close'] + (last_candle['high'] - last_candle['low']) * 2,
                'confidence': 0.7
            }
        
        # Check for bearish signal (lower high + bearish close)
        elif (last_candle['close'] < last_candle['open'] and 
              last_candle['close'] < prev_candle['close'] and
              last_candle['high'] < prev_candle['high']):
            
            return {
                'action': 'SELL',
                'entry': last_candle['close'],
                'sl': last_candle['high'] + (last_candle['high'] - last_candle['low']) * 0.5,
                'tp': last_candle['close'] - (last_candle['high'] - last_candle['low']) * 2,
                'confidence': 0.7
            }
        
        # No clear signal
        return None
    
    def find_swing_highs(self, period=5):
        """Find swing highs for liquidity detection"""
        highs = self.data['high'].values
        swing_highs = []
        
        for i in range(period, len(highs) - period):
            if highs[i] == max(highs[i-period:i+period+1]):
                swing_highs.append(highs[i])
        
        return swing_highs
    
    def find_swing_lows(self, period=5):
        """Find swing lows for liquidity detection"""
        lows = self.data['low'].values
        swing_lows = []
        
        for i in range(period, len(lows) - period):
            if lows[i] == min(lows[i-period:i+period+1]):
                swing_lows.append(lows[i])
        
        return swing_lows