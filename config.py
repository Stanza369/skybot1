# config.py - Exact version for your main.py
import os
from pathlib import Path

class Config:
    """Configuration class for ICT Trading Bot"""
    
    # Trading parameters
    SYMBOL = 'XAUUSD'
    TIMEFRAME = '5m'
    MAX_RISK_PER_TRADE = 2.0  # This is what your main.py expects!
    INITIAL_BALANCE = 5.0
    MAX_DAILY_LOSS = 5.0
    MAX_DRAWDOWN = 20.0
    
    # ICT Strategy parameters
    ORDER_BLOCK_LOOKBACK = 50
    FVG_TOLERANCE = 0.0001
    MINIMUM_DISPLACEMENT_RATIO = 1.5
    
    # Killzone times (EST)
    KILLZONE_LONDON_START = 3
    KILLZONE_LONDON_END = 5
    KILLZONE_NY_AM_START = 9.5
    KILLZONE_NY_AM_END = 11.5
    KILLZONE_NY_PM_START = 14
    KILLZONE_NY_PM_END = 16
    
    # Telegram settings
    TELEGRAM_ENABLED = False
    TELEGRAM_TOKEN = 'YOUR_BOT_TOKEN_HERE'
    TELEGRAM_CHAT_ID = 'YOUR_CHAT_ID_HERE'
    
    # News settings
    NEWS_ENABLED = False
    AVOID_HIGH_IMPACT_NEWS = True
    NEWS_AVOID_MINUTES = 30
    
    # Email settings (Gmail: smtp.gmail.com, Outlook: smtp.office365.com)
    EMAIL_ENABLED = False
    SMTP_SERVER = "smtp.gmail.com"
    SMTP_PORT = 587
    SMTP_USER = os.getenv("SMTP_USER", "")
    SMTP_PASS = os.getenv("SMTP_PASS", "")  # Use an App Password
    EMAIL_RECEIVER = os.getenv("EMAIL_RECEIVER", "")

    # SMS settings (Twilio)
    SMS_ENABLED = False
    TWILIO_SID = os.getenv("TWILIO_SID", "")
    TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "")
    TWILIO_FROM = os.getenv("TWILIO_FROM", "")
    SMS_RECEIVER = os.getenv("SMS_RECEIVER", "")

    # File paths
    BASE_DIR = Path(__file__).resolve().parent
    LOGS_DIR = BASE_DIR / 'logs'
    DATA_DIR = BASE_DIR / 'data'
    
    # Create directories if they don't exist
    LOGS_DIR.mkdir(exist_ok=True)
    DATA_DIR.mkdir(exist_ok=True)
    
    LOG_FILE = LOGS_DIR / 'trading_bot.log'
    TRADE_LOG = LOGS_DIR / 'trades.csv'
    NOTIFICATION_LOG = LOGS_DIR / 'notifications.jsonl'


# Also provide dictionary versions for compatibility with other modules
TRADING_CONFIG = {
    'symbol': Config.SYMBOL,
    'timeframe': '5m',
    'risk_percent': Config.MAX_RISK_PER_TRADE,
    'max_daily_loss': Config.MAX_DAILY_LOSS,
    'max_drawdown': Config.MAX_DRAWDOWN,
}

TELEGRAM_CONFIG = {
    'enabled': Config.TELEGRAM_ENABLED,
    'bot_token': Config.TELEGRAM_TOKEN,
    'chat_id': Config.TELEGRAM_CHAT_ID,
}

NEWS_CONFIG = {
    'enabled': Config.NEWS_ENABLED,
    'avoid_high_impact': Config.AVOID_HIGH_IMPACT_NEWS,
    'avoid_minutes_before': Config.NEWS_AVOID_MINUTES,
    'avoid_minutes_after': Config.NEWS_AVOID_MINUTES,
}