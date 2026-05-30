# automated_bot.py - Fully Automated Trading Bot
"""
COMPLETELY AUTOMATED TRADING BOT
- Runs 24/7
- Automatic trade execution based on AI signals
- Risk management
- Position tracking
- No manual intervention needed
"""

import asyncio
import json
import time
import random
from datetime import datetime
import yfinance as yf
import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import websockets
import threading

# ============================================
# CONFIGURATION
# ============================================

class Config:
    # Trading Parameters
    SYMBOL = "XAUUSD"
    INITIAL_BALANCE = 10000.0
    MAX_RISK_PER_TRADE = 0.02  # 2% risk per trade
    MAX_DAILY_LOSS = 500.0  # Stop trading after $500 loss
    MAX_DAILY_TRADES = 20
    MIN_CONFIDENCE = 65  # Minimum 65% confidence to trade
    
    # Automated Trading
    AUTO_TRADE = True
    AUTO_CLOSE_POSITIONS = True
    SCAN_INTERVAL_SECONDS = 5  # Check every 5 seconds
    
    # Risk Management
    STOP_LOSS_PIPS = 15
    TAKE_PROFIT_PIPS = 30
    TRAILING_STOP = True
    TRAILING_DISTANCE = 10

# ============================================
# TRADING STATE
# ============================================

class TradingState:
    """Tracks all trading state"""
    def __init__(self):
        self.balance = Config.INITIAL_BALANCE
        self.positions = []
        self.daily_pnl = 0
        self.daily_trades = 0
        self.consecutive_losses = 0
        self.consecutive_wins = 0
        self.today = datetime.now().date()
        self.is_trading = True
        
    def can_trade(self) -> tuple:
        """Check if bot can trade"""
        current_date = datetime.now().date()
        if current_date != self.today:
            self.daily_pnl = 0
            self.daily_trades = 0
            self.today = current_date
        
        if self.daily_pnl < -Config.MAX_DAILY_LOSS:
            return False, f"Daily loss limit reached: ${abs(self.daily_pnl):.2f}"
        
        if self.daily_trades >= Config.MAX_DAILY_TRADES:
            return False, f"Daily trade limit reached: {self.daily_trades}"
        
        if self.consecutive_losses >= 3:
            return False, "3 consecutive losses - stopping"
        
        return True, "OK"
    
    def update_trade(self, pnl: float):
        """Update state after trade"""
        self.balance += pnl
        self.daily_pnl += pnl
        self.daily_trades += 1
        
        if pnl > 0:
            self.consecutive_wins += 1
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            self.consecutive_wins = 0

# ============================================
# AI SIGNAL GENERATOR
# ============================================

class AISignalGenerator:
    """Generates trading signals automatically"""
    
    def __init__(self):
        self.last_signal = None
        self.signal_history = []
        
    def calculate_indicators(self, df: pd.DataFrame) -> Dict:
        """Calculate technical indicators"""
        if len(df) < 50:
            return {}
        
        # RSI
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # MACD
        exp1 = df['Close'].ewm(span=12).mean()
        exp2 = df['Close'].ewm(span=26).mean()
        macd = exp1 - exp2
        macd_signal = macd.ewm(span=9).mean()
        
        # Moving averages
        sma_20 = df['Close'].rolling(20).mean()
        sma_50 = df['Close'].rolling(50).mean()
        
        # Bollinger Bands
        std = df['Close'].rolling(20).std()
        bb_upper = sma_20 + 2 * std
        bb_lower = sma_20 - 2 * std
        
        # Volume
        volume_ratio = df['Volume'].iloc[-1] / df['Volume'].rolling(20).mean().iloc[-1]
        
        return {
            'rsi': rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50,
            'macd': macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else 0,
            'macd_signal': macd_signal.iloc[-1] if not pd.isna(macd_signal.iloc[-1]) else 0,
            'sma_20': sma_20.iloc[-1],
            'sma_50': sma_50.iloc[-1],
            'bb_upper': bb_upper.iloc[-1],
            'bb_lower': bb_lower.iloc[-1],
            'volume_ratio': volume_ratio.iloc[-1] if not pd.isna(volume_ratio.iloc[-1]) else 1,
            'current_price': df['Close'].iloc[-1]
        }
    
    def generate_signal(self, indicators: Dict) -> Dict:
        """Generate trading signal from indicators"""
        
        if not indicators:
            return {'action': 'HOLD', 'confidence': 0, 'reason': 'Insufficient data'}
        
        price = indicators['current_price']
        rsi = indicators['rsi']
        macd = indicators['macd']
        macd_signal = indicators['macd_signal']
        price_vs_sma20 = price / indicators['sma_20']
        
        # Buy signals
        buy_score = 0
        sell_score = 0
        
        # RSI signal
        if rsi < 30:
            buy_score += 30
        elif rsi > 70:
            sell_score += 30
        
        # MACD signal
        if macd > macd_signal:
            buy_score += 25
        elif macd < macd_signal:
            sell_score += 25
        
        # Price vs moving averages
        if price_vs_sma20 > 1.01:
            buy_score += 20
        elif price_vs_sma20 < 0.99:
            sell_score += 20
        
        # Volume confirmation
        if indicators['volume_ratio'] > 1.5:
            if buy_score > sell_score:
                buy_score += 15
            else:
                sell_score += 15
        
        # Determine action
        if buy_score > sell_score and buy_score > 50:
            confidence = min(85, buy_score)
            return {
                'action': 'BUY',
                'confidence': confidence,
                'reason': f'RSI:{rsi:.0f} MACD_bullish Volume:{indicators["volume_ratio"]:.1f}x',
                'entry': price,
                'stop_loss': price - (Config.STOP_LOSS_PIPS / 10000),
                'take_profit': price + (Config.TAKE_PROFIT_PIPS / 10000)
            }
        elif sell_score > buy_score and sell_score > 50:
            confidence = min(85, sell_score)
            return {
                'action': 'SELL',
                'confidence': confidence,
                'reason': f'RSI:{rsi:.0f} MACD_bearish Volume:{indicators["volume_ratio"]:.1f}x',
                'entry': price,
                'stop_loss': price + (Config.STOP_LOSS_PIPS / 10000),
                'take_profit': price - (Config.TAKE_PROFIT_PIPS / 10000)
            }
        
        return {'action': 'HOLD', 'confidence': 0, 'reason': 'No clear signal'}

# ============================================
# POSITION MANAGER
# ============================================

class PositionManager:
    """Manages open positions and exits"""
    
    def __init__(self, state: TradingState):
        self.state = state
        self.open_positions = []
        
    def open_position(self, signal: Dict) -> Dict:
        """Open a new position"""
        
        # Calculate position size based on risk
        risk_amount = self.state.balance * Config.MAX_RISK_PER_TRADE
        stop_pips = abs(signal['entry'] - signal['stop_loss']) * 10000
        pip_value = 0.10  # $0.10 per pip per 0.01 lot
        
        position_size = risk_amount / (stop_pips * pip_value)
        position_size = max(0.01, min(0.10, round(position_size, 2)))
        
        position = {
            'id': f"POS_{int(time.time())}_{random.randint(1000,9999)}",
            'action': signal['action'],
            'entry': signal['entry'],
            'volume': position_size,
            'stop_loss': signal['stop_loss'],
            'take_profit': signal['take_profit'],
            'open_time': time.time(),
            'confidence': signal['confidence']
        }
        
        self.open_positions.append(position)
        return position
    
    def check_positions(self, current_price: float) -> List[Dict]:
        """Check all positions for exits"""
        closed_positions = []
        
        for pos in self.open_positions[:]:
            if pos['action'] == 'BUY':
                if current_price <= pos['stop_loss']:
                    pnl = (pos['stop_loss'] - pos['entry']) * pos['volume'] * 100
                    closed_positions.append({
                        'position': pos,
                        'pnl': pnl,
                        'reason': 'STOP LOSS'
                    })
                    self.open_positions.remove(pos)
                elif current_price >= pos['take_profit']:
                    pnl = (pos['take_profit'] - pos['entry']) * pos['volume'] * 100
                    closed_positions.append({
                        'position': pos,
                        'pnl': pnl,
                        'reason': 'TAKE PROFIT'
                    })
                    self.open_positions.remove(pos)
            else:  # SELL
                if current_price >= pos['stop_loss']:
                    pnl = (pos['entry'] - pos['stop_loss']) * pos['volume'] * 100
                    closed_positions.append({
                        'position': pos,
                        'pnl': pnl,
                        'reason': 'STOP LOSS'
                    })
                    self.open_positions.remove(pos)
                elif current_price <= pos['take_profit']:
                    pnl = (pos['entry'] - pos['take_profit']) * pos['volume'] * 100
                    closed_positions.append({
                        'position': pos,
                        'pnl': pnl,
                        'reason': 'TAKE PROFIT'
                    })
                    self.open_positions.remove(pos)
        
        return closed_positions

# ============================================
# AUTOMATED TRADING BOT
# ============================================

class AutomatedTradingBot:
    """Fully automated trading bot"""
    
    def __init__(self):
        self.state = TradingState()
        self.ai = AISignalGenerator()
        self.position_manager = PositionManager(self.state)
        self.running = True
        
    def get_live_data(self) -> Optional[pd.DataFrame]:
        """Fetch live market data"""
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="1d", interval="1m")
            if df.empty:
                return None
            return df
        except Exception as e:
            print(f"Data error: {e}")
            return None
    
    def get_current_price(self) -> float:
        """Get current price"""
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="5m", interval="1m")
            if not df.empty:
                return df['Close'].iloc[-1]
        except:
            pass
        return 2650.00
    
    async def execute_trade(self, signal: Dict):
        """Execute trade automatically"""
        
        # Open position
        position = self.position_manager.open_position(signal)
        
        print(f"\n{'='*60}")
        print(f"🤖 AUTOMATED TRADE EXECUTED")
        print(f"{'='*60}")
        print(f"Action: {position['action']}")
        print(f"Volume: {position['volume']} lots")
        print(f"Entry: ${position['entry']:.2f}")
        print(f"Stop Loss: ${position['stop_loss']:.2f}")
        print(f"Take Profit: ${position['take_profit']:.2f}")
        print(f"Confidence: {position['confidence']:.0%}")
        print(f"Reason: {signal['reason']}")
        print(f"{'='*60}\n")
    
    async def run(self):
        """Main automated trading loop"""
        
        print("""
        ╔══════════════════════════════════════════════════════════════╗
        ║                                                              ║
        ║     🤖 FULLY AUTOMATED TRADING BOT                          ║
        ║                                                              ║
        ║     Mode: AUTOMATIC - No manual intervention needed         ║
        ║     Status: RUNNING 24/7                                    ║
        ║                                                              ║
        ║     Settings:                                               ║
        ║     • Max Risk/Trade: {:.1f}%                                ║
        ║     • Daily Loss Limit: ${:.0f}                              ║
        ║     • Min Confidence: {}%                                   ║
        ║     • Stop Loss: {} pips                                    ║
        ║     • Take Profit: {} pips                                  ║
        ║                                                              ║
        ╚══════════════════════════════════════════════════════════════╝
        """.format(
            Config.MAX_RISK_PER_TRADE * 100,
            Config.MAX_DAILY_LOSS,
            Config.MIN_CONFIDENCE,
            Config.STOP_LOSS_PIPS,
            Config.TAKE_PROFIT_PIPS
        ))
        
        print("🟢 Bot is LIVE and trading automatically...")
        print("Press Ctrl+C to stop\n")
        
        while self.running:
            try:
                # Check if we can trade
                can_trade, reason = self.state.can_trade()
                if not can_trade:
                    print(f"⚠️ Trading paused: {reason}")
                    await asyncio.sleep(30)
                    continue
                
                # Get market data
                df = self.get_live_data()
                if df is None:
                    await asyncio.sleep(5)
                    continue
                
                # Generate signal
                indicators = self.ai.calculate_indicators(df)
                signal = self.ai.generate_signal(indicators)
                
                # Check for open positions
                current_price = self.get_current_price()
                closed = self.position_manager.check_positions(current_price)
                
                # Update state for closed positions
                for close in closed:
                    self.state.update_trade(close['pnl'])
                    print(f"📊 Position closed: {close['reason']} | P&L: ${close['pnl']:.2f}")
                    print(f"   New Balance: ${self.state.balance:.2f}")
                
                # Execute new trade if signal is strong
                if (signal['action'] != 'HOLD' and 
                    signal['confidence'] >= Config.MIN_CONFIDENCE and
                    len(self.position_manager.open_positions) == 0):
                    
                    await self.execute_trade(signal)
                
                # Display status
                print(f"\r[{datetime.now().strftime('%H:%M:%S')}] "
                      f"Price: ${current_price:.2f} | "
                      f"Signal: {signal['action']} ({signal['confidence']:.0%}) | "
                      f"Balance: ${self.state.balance:.2f} | "
                      f"Daily: ${self.state.daily_pnl:+.2f} | "
                      f"Open: {len(self.position_manager.open_positions)}", end="")
                
                await asyncio.sleep(Config.SCAN_INTERVAL_SECONDS)
                
            except KeyboardInterrupt:
                print("\n\n🛑 Bot stopped by user")
                self.print_summary()
                break
            except Exception as e:
                print(f"\n❌ Error: {e}")
                await asyncio.sleep(10)
    
    def print_summary(self):
        """Print trading summary"""
        print("\n" + "="*60)
        print("📊 TRADING SUMMARY")
        print("="*60)
        print(f"Final Balance: ${self.state.balance:.2f}")
        print(f"Total Trades: {self.state.daily_trades}")
        print(f"Total P&L: ${self.state.daily_pnl:+.2f}")
        print(f"Consecutive Wins: {self.state.consecutive_wins}")
        print(f"Consecutive Losses: {self.state.consecutive_losses}")
        print("="*60)

async def main():
    bot = AutomatedTradingBot()
    await bot.run()

if __name__ == "__main__":
    asyncio.run(main())