# auto_flip_bot.py - Professional Auto Flip Trading System
import MetaTrader5 as mt5
import time
import json
import os
from datetime import datetime
import numpy as np
from collections import deque

# ============================================
# CONFIGURATION
# ============================================

class FlipConfig:
    # Flip Rules
    MIN_CONFIDENCE_TO_FLIP = 75      # Minimum 75% confidence to flip
    COOLDOWN_SECONDS = 30            # Wait 30 seconds after flip
    MAX_FLIPS_PER_HOUR = 3           # Max 3 flips per hour
    MIN_PROFIT_TO_FLIP = -15         # Flip if loss > $15
    MAX_SPREAD_PIPS = 25             # Don't flip if spread too high
    
    # Risk Management
    RISK_PERCENT = 2.0               # 2% risk per trade
    MAX_DAILY_FLIPS = 10             # Max flips per day
    STOP_LOSS_PIPS = 15              # 15 pips stop loss
    TAKE_PROFIT_PIPS = 30            # 30 pips take profit
    
    # Flip Confirmation Rules
    REQUIRE_LIQUIDITY_SWEEP = True   # Require liquidity sweep
    REQUIRE_VOLUME_SPIKE = True      # Require volume confirmation
    REQUIRE_TREND_ALIGNMENT = True   # Require trend alignment

# ============================================
# MT5 CONNECTION MANAGER
# ============================================

class MT5Manager:
    def __init__(self):
        self.connected = False
        self.account_info = None
        self.config_file = "broker_config.json"
        
    def load_or_setup_credentials(self):
        """Load saved credentials or ask for new ones"""
        if os.path.exists(self.config_file):
            with open(self.config_file, 'r') as f:
                config = json.load(f)
            print(f"Found saved account: {config['login']}")
            use_saved = input("Use saved credentials? (y/n): ").lower()
            if use_saved == 'y':
                return config['login'], config['password'], config['server']
        
        login = int(input("MT5 Login: "))
        password = input("MT5 Password: ")
        server = input("MT5 Server (e.g., ICMarkets-Demo): ")
        
        # Save credentials
        with open(self.config_file, 'w') as f:
            json.dump({"login": login, "password": password, "server": server}, f)
        
        return login, password, server
    
    def connect(self):
        """Connect to MT5"""
        login, password, server = self.load_or_setup_credentials()
        
        try:
            if not mt5.initialize():
                print(f"MT5 init failed: {mt5.last_error()}")
                return False
            
            if not mt5.login(login, password=password, server=server):
                print(f"Login failed: {mt5.last_error()}")
                return False
            
            self.connected = True
            self.account_info = mt5.account_info()
            
            print(f"\n✅ Connected to MT5")
            print(f"   Account: {self.account_info.login}")
            print(f"   Balance: ${self.account_info.balance:.2f}")
            print(f"   Equity: ${self.account_info.equity:.2f}")
            return True
            
        except Exception as e:
            print(f"Connection error: {e}")
            return False
    
    def disconnect(self):
        if self.connected:
            mt5.shutdown()
            self.connected = False
    
    def get_balance(self):
        if self.connected:
            info = mt5.account_info()
            return info.balance if info else 0
        return 0
    
    def get_positions(self):
        if not self.connected:
            return []
        positions = mt5.positions_get()
        return positions if positions else []
    
    def close_position(self, position):
        """Close a specific position"""
        if position.type == 0:  # BUY
            order_type = mt5.ORDER_TYPE_SELL
            price = mt5.symbol_info_tick(position.symbol).bid
        else:  # SELL
            order_type = mt5.ORDER_TYPE_BUY
            price = mt5.symbol_info_tick(position.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": position.symbol,
            "volume": position.volume,
            "type": order_type,
            "position": position.ticket,
            "price": price,
            "deviation": 20,
            "magic": 123456,
            "comment": "Auto Flip",
        }
        
        return mt5.order_send(request)
    
    def open_position(self, symbol, action, volume, sl=None, tp=None):
        """Open new position"""
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            return None
        
        if action.upper() == "BUY":
            order_type = mt5.ORDER_TYPE_BUY
            price = tick.ask
        else:
            order_type = mt5.ORDER_TYPE_SELL
            price = tick.bid
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 123456,
            "comment": "AI Auto Flip",
        }
        
        return mt5.order_send(request)

# ============================================
# AI FLIP DETECTION ENGINE
# ============================================

class FlipDetectionEngine:
    def __init__(self):
        self.price_history = deque(maxlen=100)
        self.volume_history = deque(maxlen=50)
        self.liquidity_levels = []
        self.last_flip_time = 0
        self.flips_this_hour = 0
        self.flips_today = 0
        
    def detect_liquidity_sweep(self, prices):
        """Detect if price swept a key level"""
        if len(prices) < 10:
            return False, None
        
        recent_high = max(list(prices)[-10:-1])
        recent_low = min(list(prices)[-10:-1])
        current = prices[-1]
        
        # Buy-side sweep (price above high, then drops)
        if current > recent_high:
            return True, "BUY_SIDE_SWEEP"
        
        # Sell-side sweep (price below low, then rises)
        if current < recent_low:
            return True, "SELL_SIDE_SWEEP"
        
        return False, None
    
    def detect_volume_spike(self, current_volume):
        """Detect abnormal volume spike"""
        if len(self.volume_history) < 10:
            self.volume_history.append(current_volume)
            return False
        
        avg_volume = sum(self.volume_history) / len(self.volume_history)
        self.volume_history.append(current_volume)
        
        if current_volume > avg_volume * 1.5:
            return True, current_volume / avg_volume
        
        return False, None
    
    def calculate_trend(self, prices):
        """Determine trend direction"""
        if len(prices) < 20:
            return "NEUTRAL", 0
        
        # Simple trend using moving averages
        short_ma = sum(list(prices)[-5:]) / 5
        long_ma = sum(list(prices)[-20:]) / 20
        
        if short_ma > long_ma * 1.001:
            return "BULLISH", abs((short_ma - long_ma) / long_ma * 100)
        elif short_ma < long_ma * 0.999:
            return "BEARISH", abs((short_ma - long_ma) / long_ma * 100)
        
        return "NEUTRAL", 0
    
    def should_flip(self, current_position, current_price, volume, spread):
        """Determine if we should flip"""
        
        # Add to history
        self.price_history.append(current_price)
        
        # Check cooldown
        if time.time() - self.last_flip_time < FlipConfig.COOLDOWN_SECONDS:
            return False, "Cooldown period active"
        
        # Check hourly limit
        current_hour = datetime.now().hour
        if self.flips_this_hour >= FlipConfig.MAX_FLIPS_PER_HOUR:
            return False, "Hourly flip limit reached"
        
        # Check daily limit
        if self.flips_today >= FlipConfig.MAX_DAILY_FLIPS:
            return False, "Daily flip limit reached"
        
        # Check spread
        if spread > FlipConfig.MAX_SPREAD_PIPS:
            return False, f"Spread too high: {spread} pips"
        
        # Detect liquidity sweep
        sweep_detected, sweep_type = self.detect_liquidity_sweep(self.price_history)
        
        # Detect volume spike
        volume_spike, spike_ratio = self.detect_volume_spike(volume)
        
        # Calculate trend
        trend, trend_strength = self.calculate_trend(self.price_history)
        
        # Calculate flip score
        flip_score = 0
        flip_reasons = []
        
        # Factor 1: Liquidity sweep (30 points)
        if sweep_detected and FlipConfig.REQUIRE_LIQUIDITY_SWEEP:
            flip_score += 30
            flip_reasons.append(f"Liquidity sweep: {sweep_type}")
        
        # Factor 2: Volume spike (25 points)
        if volume_spike and FlipConfig.REQUIRE_VOLUME_SPIKE:
            flip_score += 25
            flip_reasons.append(f"Volume spike: {spike_ratio:.1f}x")
        
        # Factor 3: Trend alignment (25 points)
        if FlipConfig.REQUIRE_TREND_ALIGNMENT:
            if current_position == "BUY" and trend == "BEARISH":
                flip_score += 25
                flip_reasons.append(f"Trend reversal: {trend} ({trend_strength:.1f}%)")
            elif current_position == "SELL" and trend == "BULLISH":
                flip_score += 25
                flip_reasons.append(f"Trend reversal: {trend} ({trend_strength:.1f}%)")
        
        # Factor 4: Profit/Loss trigger
        # (Would need position P&L from MT5)
        
        # Decision
        if flip_score >= FlipConfig.MIN_CONFIDENCE_TO_FLIP:
            new_action = "SELL" if current_position == "BUY" else "BUY"
            return True, {
                "action": new_action,
                "score": flip_score,
                "reasons": flip_reasons,
                "sweep": sweep_type,
                "trend": trend
            }
        
        return False, f"Flip score too low: {flip_score}/{FlipConfig.MIN_CONFIDENCE_TO_FLIP}"

# ============================================
# RISK MANAGER
# ============================================

class FlipRiskManager:
    def __init__(self, initial_balance):
        self.balance = initial_balance
        self.flips_today = 0
        self.last_flip_date = datetime.now().date()
        
    def calculate_flip_lot(self, entry, stop_loss):
        """Calculate lot size for flipped position"""
        stop_pips = abs(entry - stop_loss) * 10000
        risk_amount = self.balance * (FlipConfig.RISK_PERCENT / 100)
        pip_value = 0.10
        lot = risk_amount / (stop_pips * pip_value)
        
        # Cap based on balance
        if self.balance < 500:
            lot = min(lot, 0.05)
        elif self.balance < 2000:
            lot = min(lot, 0.10)
        else:
            lot = min(lot, 0.25)
        
        return max(0.01, round(lot, 2))
    
    def can_flip(self):
        """Check if we can flip"""
        current_date = datetime.now().date()
        if current_date != self.last_flip_date:
            self.flips_today = 0
            self.last_flip_date = current_date
        
        if self.flips_today >= FlipConfig.MAX_DAILY_FLIPS:
            return False, "Daily flip limit reached"
        
        return True, "OK"
    
    def record_flip(self):
        self.flips_today += 1

# ============================================
# MAIN AUTO FLIP BOT
# ============================================

class AutoFlipBot:
    def __init__(self):
        self.mt5 = MT5Manager()
        self.flip_detector = FlipDetectionEngine()
        self.risk_manager = None
        self.running = False
        
    def run(self):
        print("""
        ╔══════════════════════════════════════════════════════════════╗
        ║                                                              ║
        ║     🔥 AUTO FLIP TRADING BOT - PROFESSIONAL EDITION         ║
        ║                                                              ║
        ║     Automatically detects reversals and flips positions     ║
        ║                                                              ║
        ║     Flip Rules:                                             ║
        ║     • Min Confidence: {}%                                   ║
        ║     • Cooldown: {} seconds                                  ║
        ║     • Max Flips/Hour: {}                                    ║
        ║     • Max Daily Flips: {}                                   ║
        ║                                                              ║
        ║     Confirmation Rules:                                     ║
        ║     • Liquidity Sweep Required: {}                          ║
        ║     • Volume Spike Required: {}                             ║
        ║     • Trend Alignment Required: {}                          ║
        ║                                                              ║
        ╚══════════════════════════════════════════════════════════════╝
        """.format(
            FlipConfig.MIN_CONFIDENCE_TO_FLIP,
            FlipConfig.COOLDOWN_SECONDS,
            FlipConfig.MAX_FLIPS_PER_HOUR,
            FlipConfig.MAX_DAILY_FLIPS,
            FlipConfig.REQUIRE_LIQUIDITY_SWEEP,
            FlipConfig.REQUIRE_VOLUME_SPIKE,
            FlipConfig.REQUIRE_TREND_ALIGNMENT
        ))
        
        # Connect to MT5
        if not self.mt5.connect():
            print("❌ Failed to connect to MT5")
            return
        
        # Initialize risk manager
        self.risk_manager = FlipRiskManager(self.mt5.get_balance())
        self.running = True
        
        print("\n🟢 Auto Flip Bot is RUNNING...")
        print("🔍 Monitoring for reversal signals\n")
        
        try:
            while self.running:
                # Get current positions
                positions = self.mt5.get_positions()
                
                if len(positions) > 0:
                    position = positions[0]
                    current_action = "BUY" if position.type == 0 else "SELL"
                    
                    # Get market data
                    tick = mt5.symbol_info_tick("XAUUSD")
                    if tick:
                        current_price = tick.bid if position.type == 0 else tick.ask
                        spread = (tick.ask - tick.bid) * 10000
                        
                        # Check if we should flip
                        should_flip, result = self.flip_detector.should_flip(
                            current_action,
                            current_price,
                            tick.volume or 1000,
                            spread
                        )
                        
                        if should_flip:
                            # Close current position
                            print(f"\n{'='*60}")
                            print(f"🔄 AUTO FLIP TRIGGERED!")
                            print(f"{'='*60}")
                            print(f"Current Position: {current_action}")
                            print(f"Current Price: ${current_price:.2f}")
                            print(f"Flip Score: {result['score']}")
                            print(f"Reasons: {', '.join(result['reasons'])}")
                            
                            # Close position
                            close_result = self.mt5.close_position(position)
                            if close_result.retcode == mt5.TRADE_RETCODE_DONE:
                                print(f"✅ Position closed")
                                
                                # Open new position in opposite direction
                                new_action = result['action']
                                sl = current_price - FlipConfig.STOP_LOSS_PIPS/10000 if new_action == "BUY" else current_price + FlipConfig.STOP_LOSS_PIPS/10000
                                tp = current_price + FlipConfig.TAKE_PROFIT_PIPS/10000 if new_action == "BUY" else current_price - FlipConfig.TAKE_PROFIT_PIPS/10000
                                
                                lot = self.risk_manager.calculate_flip_lot(current_price, sl)
                                
                                open_result = self.mt5.open_position(
                                    symbol="XAUUSD",
                                    action=new_action,
                                    volume=lot,
                                    sl=sl,
                                    tp=tp
                                )
                                
                                if open_result and open_result.retcode == mt5.TRADE_RETCODE_DONE:
                                    print(f"✅ Flipped to {new_action}")
                                    print(f"   New Entry: ${current_price:.2f}")
                                    print(f"   Volume: {lot} lots")
                                    print(f"   Stop Loss: ${sl:.2f}")
                                    print(f"   Take Profit: ${tp:.2f}")
                                    
                                    # Update flip tracking
                                    self.flip_detector.last_flip_time = time.time()
                                    self.flip_detector.flips_this_hour += 1
                                    self.risk_manager.record_flip()
                                else:
                                    print(f"❌ Failed to open new position")
                            else:
                                print(f"❌ Failed to close position")
                            
                            print(f"{'='*60}\n")
                
                # Display status
                balance = self.mt5.get_balance()
                positions = len(self.mt5.get_positions())
                print(f"\r💰 Balance: ${balance:.2f} | Positions: {positions} | Flips Today: {self.risk_manager.flips_today} | Monitoring...", end="")
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Bot stopped")
        finally:
            self.mt5.disconnect()

# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    bot = AutoFlipBot()
    bot.run()