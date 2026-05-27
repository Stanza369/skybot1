import time
import logging
import traceback
from functools import wraps

logger = logging.getLogger(__name__)

def resilient(func):
    """Decorator to catch exceptions and log full tracebacks without crashing the main loop."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Critical error in {func.__name__}: {str(e)}")
            logger.error(traceback.format_exc())
            return None
    return wrapper

class BotSupervisor:
    """Supervises the trading bot and handles auto-restarts on failure."""
    
    def __init__(self, bot_instance):
        self.bot = bot_instance
        self.max_retries = 5
        self.retry_delay = 15 # seconds

    def run_forever(self):
        logger.info("Supervisor: Starting bot health monitoring...")
        while True:
            try:
                # This assumes the bot has a non-blocking or managed loop
                self.bot.run()
            except KeyboardInterrupt:
                logger.info("Manual shutdown detected.")
                break
            except Exception as e:
                logger.error(f"Bot Supervisor detected crash: {e}. Restarting in {self.retry_delay}s...")
                time.sleep(self.retry_delay)
                # Re-initialize connection if necessary
                self.bot.initialize()