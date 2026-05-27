# main_fixed.py - Complete working version
import time
import logging
from datetime import datetime
import yfinance as yf
import pytz
import os
import asyncio
from backend.notification_manager import notification_manager

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ICTTradingBot:
    def __init__(self):
        self.symbol = "GC=F"  # Gold futures
        self.balance = 5.0
        self.risk_percent = 2.0  # ← CORRECT: 2% risk
        self.position = None
        self.trade_count = 0
        self.winning_trades = 0
        
        logger.info("=" * 50)
        logger.info("🤖 ICT Bot Started")
        logger.info(f"Balance: ${self.balance}")
        logger.info(f"Risk per trade: {self.risk_percent}%")
        logger.info("Killzones: London(3-5am), NY AM(9:30-11:30am), NY PM(2-4pm EST)")
        logger.info("=" * 50)
    
    def get_market_data(self):
        """Fetch current market data"""
        try:
            ticker = yf.Ticker(self.symbol)
            df = ticker.history(period="1d", interval="5m")
            if df.empty:
                return None
            df.columns = [col.lower() for col in df.columns]
            return df
        except Exception as e:
            logger.error(f"Data error: {e}")
            return None
    
    def get_est_time(self):
        """Get current EST time"""
        est = pytz.timezone('US/Eastern')
        now_est = datetime.now(est)
        return now_est.hour + now_est.minute / 60
    
    def is_killzone_active(self, current_hour):
        """Check if current time is within ICT killzones"""
        if 3 <= current_hour <= 5:
            return True, "London"
        if 9.5 <= current_hour <= 11.5:
            return True, "NY AM"
        if 14 <= current_hour <= 16:
            return True, "NY PM"
        return False, None
    
    def get_signal(self, data):
        """Generate trading signal based on ICT logic"""
        if data is None or len(data) < 5:
            return None
        
        last = data.iloc[-1]
        prev = data.iloc[-2]
        
        # Bullish signal
        if (last['close'] > last['open'] and 
            last['close'] > prev['close'] and
            last['low'] > prev['low']):
            return {
                'action': 'BUY',
                'entry': last['close'],
                'sl': last['low'] - 0.0010,
                'tp': last['close'] + 0.0020
            }
        
        # Bearish signal
        elif (last['close'] < last['open'] and 
              last['close'] < prev['close'] and
              last['high'] < prev['high']):
            return {
                'action': 'SELL',
                'entry': last['close'],
                'sl': last['high'] + 0.0010,
                'tp': last['close'] - 0.0020
            }
        
        return None
    
    def calculate_lot_size(self):
        """Calculate position size based on risk management"""
        risk_amount = self.balance * (self.risk_percent / 100)
        lot_size = risk_amount / (10 * 0.10)  # 10 pip stop loss
        
        # Safety caps
        if self.balance < 25:
            lot_size = min(lot_size, 0.02)
        elif self.balance < 100:
            lot_size = min(lot_size, 0.05)
        else:
            lot_size = min(lot_size, 0.10)
        
        lot_size = max(0.01, round(lot_size, 2))
        
        actual_risk = lot_size * 10 * 0.10
        logger.info(f"📊 Position: {lot_size} lots, Risk: ${actual_risk:.2f} ({self.risk_percent:.1f}% of ${self.balance:.2f})")
        
        return lot_size
    
    def execute_trade(self, signal, lot_size):
        """Execute a trade"""
        if self.position is not None:
            return False
        
        logger.info("=" * 40)
        logger.info(f"🚀 {signal['action']} SIGNAL")
        logger.info(f"Entry: {signal['entry']:.5f}")
        logger.info(f"Stop Loss: {signal['sl']:.5f}")
        logger.info(f"Take Profit: {signal['tp']:.5f}")
        logger.info(f"Lot Size: {lot_size}")
        logger.info("=" * 40)
        
        self.position = {
            'type': signal['action'],
            'entry': signal['entry'],
            'sl': signal['sl'],
            'tp': signal['tp'],
            'lot_size': lot_size,
            'open_time': time.time()
        }
        # Send notification about opened trade (best-effort)
        try:
            user_id = int(os.getenv('ADMIN_USER_ID', '1'))
            notify_data = {
                'symbol': self.symbol,
                'action': signal['action'],
                'volume': lot_size,
                'entry_price': signal['entry'],
                'stop_loss': signal['sl'],
                'take_profit': signal['tp'],
                'risk_amount': round(lot_size * 10 * 0.10, 2),
                'strategy': 'ICT'
            }
            asyncio.run(notification_manager.send_notification(user_id, 'trade', notify_data))
        except Exception:
            logger.exception('Failed to send trade open notification')

        return True
    
    def check_position(self, current_price):
        """Check if position hit SL or TP"""
        if self.position is None:
            return None
        
        pos = self.position
        action = pos['type']
        entry = pos['entry']
        sl = pos['sl']
        tp = pos['tp']
        lot = pos['lot_size']
        
        if action == 'BUY':
            if current_price <= sl:
                pips = (sl - entry) * 10000
                pnl = pips * lot * 0.10
                result = 'LOSS'
            elif current_price >= tp:
                pips = (tp - entry) * 10000
                pnl = pips * lot * 0.10
                result = 'PROFIT'
            else:
                return None
        else:  # SELL
            if current_price >= sl:
                pips = (entry - sl) * 10000
                pnl = pips * lot * 0.10
                result = 'LOSS'
            elif current_price <= tp:
                pips = (entry - tp) * 10000
                pnl = pips * lot * 0.10
                result = 'PROFIT'
            else:
                return None
        
        # Update account
        self.balance += pnl
        self.trade_count += 1
        if pnl > 0:
            self.winning_trades += 1
        
        win_rate = (self.winning_trades / self.trade_count * 100) if self.trade_count > 0 else 0
        
        logger.info(f"{'✅' if pnl > 0 else '❌'} {result}: ${pnl:.2f}")
        logger.info(f"New balance: ${self.balance:.2f}")
        logger.info(f"Win rate: {win_rate:.1f}% ({self.winning_trades}/{self.trade_count})")
        
        self.position = None
        # Send trade close notification (best-effort)
        try:
            user_id = int(os.getenv('ADMIN_USER_ID', '1'))
            notify_close = {
                'result': result,
                'profit': pnl,
                'new_balance': self.balance,
                'pips': pips,
                'duration': time.time() - pos.get('open_time', time.time()),
                'win_rate': win_rate
            }
            asyncio.run(notification_manager.send_notification(user_id, 'trade_close', notify_close))
        except Exception:
            logger.exception('Failed to send trade close notification')

        return {'result': result, 'pnl': pnl}
    
    def run(self):
        """Main bot loop"""
        logger.info("Bot is now ACTIVE and scanning for signals...")
        
        while True:
            try:
                current_hour = self.get_est_time()
                is_killzone, zone_name = self.is_killzone_active(current_hour)
                
                # Show killzone status
                if is_killzone and self.position is None:
                    logger.info(f"⏰ {zone_name} Killzone ACTIVE ({current_hour:.1f} EST)")
                    
                    data = self.get_market_data()
                    if data is not None:
                        signal = self.get_signal(data)
                        if signal:
                            lot_size = self.calculate_lot_size()
                            self.execute_trade(signal, lot_size)
                
                # Check existing position
                if self.position:
                    data = self.get_market_data()
                    if data is not None:
                        current_price = data.iloc[-1]['close']
                        self.check_position(current_price)
                
                # Status update
                status = f"💰 Balance: ${self.balance:.2f}"
                if self.position:
                    status += f" | In {self.position['type']} trade"
                if is_killzone:
                    status += f" | {zone_name} ACTIVE"
                
                logger.info(status)
                time.sleep(60)
                
            except KeyboardInterrupt:
                logger.info("\n🛑 Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error: {e}")
                time.sleep(60)

if __name__ == "__main__":
    print("\n" + "=" * 50)
    print("🤖 ICT TRADING BOT")
    print("=" * 50)
    print("Starting bot with $5 account, 2% risk per trade")
    print("Press Ctrl+C to stop")
    print("=" * 50 + "\n")
    
    bot = ICTTradingBot()
    bot.run()