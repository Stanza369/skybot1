# main.py - Production Trading Bot
import asyncio
import signal
import sys
from datetime import datetime
from config.settings import settings
from brokers.mt5_connector import MT5Connector
from core.logger import logger
from core.error_recovery import BotSupervisor, resilient
from core.analytics import PerformanceAnalytics
from ict_strategy import ICTStrategy
from professional_risk_manager import ProfessionalRiskManager

class ProductionTradingBot:
    """Complete production-ready trading bot"""
    
    def __init__(self):
        self.is_running = True
        self.mt5 = None
        self.strategy = None
        self.risk_manager = None
        self.analytics = PerformanceAnalytics()
        self.supervisor = BotSupervisor()
        
    def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Production Trading Bot...")
        
        # Initialize MT5
        self.mt5 = MT5Connector(
            login=settings.MT5_LOGIN,
            password=settings.MT5_PASSWORD,
            server=settings.MT5_SERVER
        )
        
        if not self.mt5.connect():
            logger.critical("Failed to connect to MT5")
            return False
        
        # Initialize strategy
        # Note: Adapted to your existing ICTStrategy class
        self.strategy = ICTStrategy(None)
        
        # Initialize risk manager
        account_info = self.mt5.get_account_info()
        if account_info:
            self.risk_manager = ProfessionalRiskManager(account_info['balance'])
        
        logger.info("✅ Bot initialized successfully")
        return True
    
    @resilient(max_retries=3, delay=5)
    async def execute_trade(self, signal: dict):
        """Execute trade with error handling"""
        
        # Check risk limits (assuming assess_trade_risk API)
        risk_eval = self.risk_manager.assess_trade_risk(signal, None, "london")
        if not risk_eval.get('can_trade'):
            logger.warning(f"Risk check failed: {risk_eval.get('reason')}")
            return
        
        lot_size = risk_eval.get('position_size', 0.01)
        
        # Place order
        result = self.mt5.place_order(
            symbol=settings.SYMBOL,
            action=signal['action'],
            volume=lot_size,
            stop_loss=signal.get('sl'),
            take_profit=signal.get('tp')
        )
        
        if result['success']:
            logger.info(f"TRADE EXECUTED: {signal['action']} {lot_size}")

    async def run(self):
        """Main bot loop"""
        if not self.initialize():
            return
        
        logger.info("🚀 Bot is now LIVE - Trading real money")
        
        while self.is_running:
            try:
                # Get market data
                data = self.mt5.get_market_data(settings.SYMBOL, "M5", 100)
                
                if data is not None:
                    self.strategy.data = data
                    # Check for trading signal
                    signal = self.strategy.analyze(3.0) # Dummy hour
                    
                    if signal:
                        await self.execute_trade(signal)
                
                await asyncio.sleep(5)
                
            except KeyboardInterrupt:
                break
            except Exception as e:
                logger.error(f"Main loop error: {e}")
                await asyncio.sleep(30)

def main():
    bot = ProductionTradingBot()
    bot.supervisor.run_with_recovery(asyncio.run, bot.run())

if __name__ == "__main__":
    main()
    def run(self):
        """Main bot loop"""
        logger.info("=" * 50)
        logger.info("🤖 ICT Trading Bot Started")
        logger.info(f"Symbol: {self.symbol}")
        logger.info(f"Risk: {self.risk_percent}% per trade")
        logger.info("Killzones: London(3-5am), NY AM(9:30-11:30am), NY PM(2-4pm)")
        logger.info("=" * 50)
        
        while True:
            try:
                # Get current time
                current_hour = self.get_est_time()
                
                # Fetch market data
                data = self.get_market_data()
                if data is None or len(data) < 20:
                    time.sleep(60)
                    continue
                
                # Initialize strategy with data
                self.ict_strategy = ICTStrategy(data)
                
                # Check for trading signal
                is_killzone = self.is_killzone_active(current_hour)
                
                if is_killzone and self.position is None:
                    signal = self.ict_strategy.analyze(current_hour)
                    
                    if signal:
                        self.execute_trade(signal)
                
                # Check existing position
                current_price = data.iloc[-1]['close']
                result = self.check_position(current_price)
                
                if result:
                    # Update balance
                    self.balance += result['pnl']
                    logger.info(f"New balance: ${self.balance:.2f}")
                    # notify trade close
                    try:
                        user_id = int(os.getenv('ADMIN_USER_ID', '1'))
                        notify_close = {
                            'result': result.get('result'),
                            'profit': result.get('pnl'),
                            'new_balance': self.balance
                        }
                        asyncio.run(notification_manager.send_notification(user_id, 'trade_close', notify_close))
                    except Exception:
                        logger.exception('Failed to send trade close notification')
                
                # Status update
                logger.debug(f"{datetime.now().strftime('%H:%M:%S')} - Scanning...")
                
                time.sleep(60)
                
            except KeyboardInterrupt:
                logger.info("\n🛑 Bot stopped by user")
                break
            except Exception as e:
                logger.error(f"Error in main loop: {e}")
                time.sleep(60)
    
    def is_killzone_active(self, current_hour):
        """Check if current time is within ICT killzones"""
        # London: 3-5am EST
        if 3 <= current_hour <= 5:
            return True
        # NY AM: 9:30-11:30am EST
        if 9.5 <= current_hour <= 11.5:
            return True
        # NY PM: 2-4pm EST
        if 14 <= current_hour <= 16:
            return True
        return False

if __name__ == "__main__":
    bot = ICTTradingBot()
    supervisor = BotSupervisor(bot)
    supervisor.run_forever()
