# config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # Database
    DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://trader:secure_password@localhost:5432/trading_db")
    
    # MT5
    MT5_LOGIN = int(os.getenv("MT5_LOGIN", 0))
    MT5_PASSWORD = os.getenv("MT5_PASSWORD", "")
    MT5_SERVER = os.getenv("MT5_SERVER", "ICMarkets-Demo")
    
    # Alerts
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    SENTRY_DSN = os.getenv("SENTRY_DSN", "")
    
    # Trading Parameters
    INITIAL_BALANCE = 10000.0
    RISK_PERCENT = 1.0
    MAX_DAILY_LOSS = 5.0
    MAX_DRAWDOWN = 20.0
    
    # API
    JWT_SECRET = os.getenv("JWT_SECRET", "your-secret-key")
    JWT_EXPIRY_HOURS = 24
    
    # Admin
    ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

settings = Settings()