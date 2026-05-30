# auto_flip_simple.py - Simple working auto flip bot
import time
import random
from datetime import datetime

# ============================================
# CONFIGURATION
# ============================================

class Config:
    MIN_CONFIDENCE = 70
    COOLDOWN_SECONDS = 30
    MAX_FLIPS_PER_HOUR = 3
    RISK_PERCENT = 2.0
    STOP_LOSS_PIPS = 15
    TAKE_PROFIT_PIPS = 30

# ============================================
# SIMULATED PRICE (For testing - will be replaced by MT5)
# ============================================

class PriceSimulator:
    def __init__(self):
        self.price = 2650.00
        self.trend = 0
        
    def get_price(self):
        # Simulate realistic gold movement
        self.trend += (random.random() - 0.5) * 0.3
        self.trend = max(-1.5, min(1.5, self.trend))
        self.price += self.trend + (random.random() - 0.5) * 0.5
        self.price = max(2600, min(2750, self.price))
        return round(self.price, 2)

# ============================================
# FLIP DETECTION
# ============================================

class FlipDetector:
    def __init__(self):
        self.price_history = []
        self.last_flip_time = 0
        self.flips_today = 0
        self.today = datetime.now().date()
        
    def analyze(self, current_price, current_position):
        """Check if market conditions indicate a flip"""
        self.price_history.append(current_price)
        if len(self.price_history) > 20:
            self.price_history.pop(0)
        
        if len(self.price_history) < 10:
            return False, None
        
        # Check cooldown
        if time.time() - self.last_flip_time < Config.COOLDOWN_SECONDS:
            return False, "Cooldown active"
        
        # Check daily limit
        current_date = datetime.now().date()
        if current_date != self.today:
            self.flips_today = 0
            self.today = current_date
        
        if self.flips_today >= 10:
            return False, "Daily flip limit reached"
        
        # Calculate momentum
        price_change = ((self.price_history[-1] - self.price_history[-5]) / self.price_history[-5]) * 100
        
        # Determine if we should flip
        if current_position == "BUY" and price_change < -0.1:
            confidence = min(85, 65 + abs(price_change) * 10)
            return True, {
                "action": "SELL",
                "confidence": confidence,
                "reason": f"Bearish reversal {price_change:.2f}%"
            }
        elif current_position == "SELL" and price_change > 0.1:
            confidence = min(85, 65 + price_change * 10)
            return True, {
                "action": "BUY",
                "confidence": confidence,
                "reason": f"Bullish reversal {price_change:.2f}%"
            }
        
        return False, None
    
    def record_flip(self):
        self.flips_today += 1
        self.last_flip_time = time.time()

# ============================================
# ACCOUNT MANAGER
# ============================================

class AccountManager:
    def __init__(self):
        self.balance = 10000.0
        self.position = None
        self.daily_pnl = 0
        self.trades = 0
        
    def open_position(self, action, price, confidence):
        """Open new position"""
        # Calculate lot size based on risk
        risk_amount = self.balance * (Config.RISK_PERCENT / 100)
        stop_pips = Config.STOP_LOSS_PIPS
        pip_value = 0.10
        lot = risk_amount / (stop_pips * pip_value)
        lot = max(0.01, min(0.10, round(lot, 2)))
        
        # Calculate SL and TP
        if action == "BUY":
            sl = price - Config.STOP_LOSS_PIPS / 10000
            tp = price + Config.TAKE_PROFIT_PIPS / 10000
        else:
            sl = price + Config.STOP_LOSS_PIPS / 10000
            tp = price - Config.TAKE_PROFIT_PIPS / 10000
        
        self.position = {
            "action": action,
            "entry": price,
            "volume": lot,
            "sl": sl,
            "tp": tp,
            "confidence": confidence,
            "open_time": time.time()
        }
        
        print(f"\n{'='*50}")
        print(f"🚀 POSITION OPENED: {action}")
        print(f"   Entry: ${price:.2f}")
        print(f"   Volume: {lot} lots")
        print(f"   SL: ${sl:.2f} | TP: ${tp:.2f}")
        print(f"   Confidence: {confidence:.0f}%")
        print(f"{'='*50}\n")
        
        return self.position
    
    def close_position(self, current_price):
        """Close current position and calculate P&L"""
        if not self.position:
            return None
        
        pos = self.position
        if pos["action"] == "BUY":
            pnl = (current_price - pos["entry"]) * pos["volume"] * 100
        else:
            pnl = (pos["entry"] - current_price) * pos["volume"] * 100
        
        self.balance += pnl
        self.daily_pnl += pnl
        self.trades += 1
        
        print(f"\n📊 POSITION CLOSED")
        print(f"   P&L: ${pnl:+.2f}")
        print(f"   New Balance: ${self.balance:.2f}")
        print(f"   Daily P&L: ${self.daily_pnl:+.2f}\n")
        
        position = self.position
        self.position = None
        return pnl, position
    
    def flip_position(self, current_price, new_action, confidence):
        """Flip: Close current, open opposite"""
        # Close current
        pnl, old_position = self.close_position(current_price)
        
        # Open opposite
        self.open_position(new_action, current_price, confidence)
        
        return pnl

# ============================================
# MAIN AUTO FLIP BOT
# ============================================

class AutoFlipBot:
    def __init__(self):
        self.price_sim = PriceSimulator()
        self.flip_detector = FlipDetector()
        self.account = AccountManager()
        
    def run(self):
        print("""
        ╔══════════════════════════════════════════════════════════════╗
        ║                                                              ║
        ║     🔥 AUTO FLIP TRADING BOT - DEMO MODE                    ║
        ║                                                              ║
        ║     Automatically flips positions when market reverses      ║
        ║                                                              ║
        ║     Rules:                                                  ║
        ║     • Min Confidence: {}%                                   ║
        ║     • Cooldown: {} seconds                                  ║
        ║     • Max Flips/Hour: {}                                    ║
        ║     • Risk per trade: {}%                                   ║
        ║                                                              ║
        ╚══════════════════════════════════════════════════════════════╝
        """.format(
            Config.MIN_CONFIDENCE,
            Config.COOLDOWN_SECONDS,
            Config.MAX_FLIPS_PER_HOUR,
            Config.RISK_PERCENT
        ))
        
        print("🟢 Bot is RUNNING in DEMO mode...")
        print("Press Ctrl+C to stop\n")
        
        try:
            while True:
                # Get current price
                current_price = self.price_sim.get_price()
                
                # If no position, open one (start with BUY)
                if self.account.position is None:
                    self.account.open_position("BUY", current_price, 75)
                
                # Check if we should flip
                should_flip, flip_info = self.flip_detector.analyze(
                    current_price,
                    self.account.position["action"]
                )
                
                if should_flip and flip_info["confidence"] >= Config.MIN_CONFIDENCE:
                    print(f"\n{'='*50}")
                    print(f"🔄 AUTO FLIP TRIGGERED!")
                    print(f"   Current: {self.account.position['action']}")
                    print(f"   New: {flip_info['action']}")
                    print(f"   Confidence: {flip_info['confidence']:.0f}%")
                    print(f"   Reason: {flip_info['reason']}")
                    print(f"{'='*50}")
                    
                    # Execute flip
                    pnl = self.account.flip_position(
                        current_price,
                        flip_info['action'],
                        flip_info['confidence']
                    )
                    
                    # Record flip
                    self.flip_detector.record_flip()
                
                # Display status
                position_status = f"{self.account.position['action']}" if self.account.position else "None"
                print(f"\r💰 Balance: ${self.account.balance:.2f} | "
                      f"Price: ${current_price:.2f} | "
                      f"Position: {position_status} | "
                      f"Flips Today: {self.flip_detector.flips_today} | "
                      f"Scanning...", end="")
                
                time.sleep(2)
                
        except KeyboardInterrupt:
            print("\n\n🛑 Bot stopped")
            print(f"\n📊 FINAL SUMMARY")
            print(f"   Balance: ${self.account.balance:.2f}")
            print(f"   Total P&L: ${self.account.daily_pnl:+.2f}")
            print(f"   Total Flips: {self.flip_detector.flips_today}")

# ============================================
# RUN
# ============================================

if __name__ == "__main__":
    bot = AutoFlipBot()
    bot.run()