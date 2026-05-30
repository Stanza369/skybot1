# core/error_recovery.py
import time
import traceback
import signal
import sys
from functools import wraps
from typing import Callable
from core.logger import logger

class BotSupervisor:
    """Monitors and restarts the bot on failures"""
    
    def __init__(self):
        self.attempts = 0
        self.max_attempts = 5
        self.is_running = True
        self.setup_signal_handlers()
    
    def setup_signal_handlers(self):
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down...")
        self.is_running = False
        sys.exit(0)
    
    def run_with_recovery(self, bot_function: Callable, *args, **kwargs):
        """Run bot with automatic recovery on crashes"""
        while self.is_running:
            try:
                self.attempts = 0
                bot_function(*args, **kwargs)
                
            except KeyboardInterrupt:
                logger.info("Bot stopped by user")
                break
                
            except Exception as e:
                self.attempts += 1
                logger.critical(f"Bot crashed: {e}")
                logger.critical(traceback.format_exc())
                
                if self.attempts >= self.max_attempts:
                    logger.critical(f"Max attempts ({self.max_attempts}) reached. Giving up.")
                    break
                
                wait_time = 10 * self.attempts
                logger.info(f"Restarting in {wait_time} seconds... (Attempt {self.attempts}/{self.max_attempts})")
                time.sleep(wait_time)

def resilient(max_retries: int = 3, delay: int = 5):
    """Decorator for resilient function calls"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {func.__name__}: {e}")
                    if attempt == max_retries - 1:
                        raise
                    time.sleep(delay)
            return None
        return wrapper
    return decorator

class CircuitBreaker:
    """Circuit breaker pattern to prevent cascading failures"""
    
    def __init__(self, failure_threshold=5, timeout=60):
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.failures = 0
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED, OPEN, HALF_OPEN
    
    def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.timeout:
                self.state = "HALF_OPEN"
            else:
                raise Exception("Circuit breaker is OPEN")
        
        try:
            result = func(*args, **kwargs)
            if self.state == "HALF_OPEN":
                self.state = "CLOSED"
                self.failures = 0
            return result
            
        except Exception as e:
            self.failures += 1
            self.last_failure_time = time.time()
            
            if self.failures >= self.failure_threshold:
                self.state = "OPEN"
                logger.warning(f"Circuit breaker OPEN for {func.__name__}")
            raise e