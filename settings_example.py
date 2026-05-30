# config/settings_example.py
"""
Copy this file to settings.py and add your own API keys
Never commit settings.py to GitHub!
"""

import os
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).resolve().parent.parent

# Trading parameters
TRADING_CONFIG = {
    'symbol': 'XAUUSD',  # ← QUOTES around string!
    'timeframe': '5m',   # ← QUOTES!
    'risk_percent': 2.0,  # Never change this - 2% is optimal!
    'max_daily_loss': 5.0,  # percent
    'max_drawdown': 20.0,   # percent
}

# ICT Strategy parameters
ICT_CONFIG = {
    'killzones': {
        'london': {'start': 3, 'end': 5},      # 3am-5am EST
        'ny_am': {'start': 9.5, 'end': 11.5},  # 9:30am-11:30am EST
        'ny_pm': {'start': 14, 'end': 16}      # 2pm-4pm EST
    },
    'order_block_lookback': 50,
    'fvg_tolerance': 0.0001,
    'minimum_displacement_ratio': 1.5,
}

# Telegram configuration (REQUIRED)
TELEGRAM_CONFIG = {
    'bot_token': 'YOUR_BOT_TOKEN_HERE',  # ← QUOTES! Get from @BotFather
    'chat_id': 'YOUR_CHAT_ID_HERE',      # ← QUOTES! Your Telegram chat ID
    'enabled': True,  # ← Capital T, not 'true'!
}

# MT5 Configuration (for live trading)
MT5_CONFIG = {
    'account': 0,           # Your MT5 account number
    'password': '',         # Your MT5 password (empty string)
    'server': 'ICMarkets-Demo',  # ← QUOTES around server name
    'enabled': False,       # Set to True when ready
}

# News configuration
NEWS_CONFIG = {
    'enabled': True,  # ← Capital T!
    'avoid_high_impact': True,  # ← Capital T!
    'avoid_minutes_before': 30,
    'avoid_minutes_after': 30,
    'high_impact_currencies': ['USD', 'EUR', 'GBP', 'JPY'],  # ← All need quotes!
}

# Logging configuration
LOGGING_CONFIG = {
    'level': 'INFO',  # DEBUG, INFO, WARNING, ERROR
    'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    'file': str(BASE_DIR / 'logs' / 'trading_bot.log'),
    'console': True,
}

# Performance tracking
TRACKING_CONFIG = {
    'save_trades': True,
    'save_daily_stats': True,
    'track_win_rate': True,
    'track_drawdown': True,
}
