"""
I-Trade Configuration
"""

import os


class Config:
    # Paper trading
    INITIAL_BALANCE = float(os.getenv("INITIAL_BALANCE", "1000"))
    
    # Hyperliquid API (public, no auth needed for market data)
    HL_API_URL = os.getenv("HL_API_URL", "https://api.hyperliquid.xyz")
    HL_INFO_URL = os.getenv("HL_INFO_URL", "https://api.hyperliquid.xyz/info")
    
    # Smart money tracking
    ARKHAM_API_KEY = os.getenv("ARKHAM_API_KEY", "")
    
    # Telegram alerts (optional)
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
    
    # Server
    HOST = os.getenv("ITRADE_HOST", "0.0.0.0")
    PORT = int(os.getenv("ITRADE_PORT", "8888"))
    
    # Risk management
    MAX_DAILY_LOSS = float(os.getenv("MAX_DAILY_LOSS", "50"))
    MAX_DRAWDOWN = float(os.getenv("MAX_DRAWDOWN", "150"))
    MAX_OPEN_POSITIONS = int(os.getenv("MAX_OPEN_POSITIONS", "5"))
    MIN_CASH_RATIO = float(os.getenv("MIN_CASH_RATIO", "0.30"))
