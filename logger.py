# core/logger.py
import logging
import logging.handlers
import sys
from datetime import datetime
from pathlib import Path

class TradingLogger:
    """Professional logging system with rotation and alerts"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._setup_logger()
        return cls._instance
    
    def _setup_logger(self):
        self.logger = logging.getLogger("TradingBot")
        self.logger.setLevel(logging.DEBUG)
        
        # Create logs directory
        Path("logs").mkdir(exist_ok=True)
        
        # Format
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s'
        )
        
        # File handler (rotating)
        file_handler = logging.handlers.RotatingFileHandler(
            'logs/trading_bot.log', 
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.DEBUG)
        
        # Error file handler
        error_handler = logging.handlers.RotatingFileHandler(
            'logs/errors.log',
            maxBytes=5242880,  # 5MB
            backupCount=5
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)
        
        # Console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.INFO)
        
        self.logger.addHandler(file_handler)
        self.logger.addHandler(error_handler)
        self.logger.addHandler(console_handler)
    
    def info(self, message, **kwargs):
        self.logger.info(message, extra=kwargs)
    
    def warning(self, message, **kwargs):
        self.logger.warning(message, extra=kwargs)
    
    def error(self, message, **kwargs):
        self.logger.error(message, extra=kwargs)
    
    def critical(self, message, **kwargs):
        self.logger.critical(message, extra=kwargs)

# Global logger instance
logger = TradingLogger()