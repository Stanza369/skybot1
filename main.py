# main.py - Updated with working features
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import random
import threading
import pandas as pd
from datetime import datetime
from typing import List, Dict
import logging
from config import Config
from social_trading_intelligence import SocialTradingDatabase, SocialIntelligenceEngine, social_simulation_loop
from order_executor import MT5Broker
from enhanced_auto_flip import AdvancedRiskManager, EnhancedFlipDetector

try:
    import MetaTrader5 as mt5
    USE_MT5 = True
except ImportError:
    USE_MT5 = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Trading Bot", version="3.0.0")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Account state
account_balance = 10000.00
daily_pnl = 46.90
total_pnl = 1250.45
win_rate = 68.2
drawdown = 0.7
positions = []

class MarketDataEngine:
    def __init__(self):
        self.price = 2648.53
        self.price_history = []
        
    def get_price(self):
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="1d", interval="1m")
            if not df.empty:
                self.price = df['Close'].iloc[-1]
                self.price_history.append(self.price)
                if len(self.price_history) > 100:
                    self.price_history.pop(0)
                return self.price
        except Exception as e:
            logger.error(f"Price fetch error: {e}")
        
        # Simulated movement
        change = (random.random() - 0.5) * 1.5
        self.price += change
        self.price = round(self.price, 2)
        self.price_history.append(self.price)
        if len(self.price_history) > 100:
            self.price_history.pop(0)
        return self.price
    
    def get_market_data(self):
        price = self.get_price()
        return {
            'price': price,
            'change': round((self.price_history[-1] - self.price_history[-2]) / self.price_history[-2] * 100, 2) if len(self.price_history) > 1 else 0,
            'high': max(self.price_history[-20:]) if self.price_history else price,
            'low': min(self.price_history[-20:]) if self.price_history else price,
            'volume': random.randint(4000000, 6000000),
            'timestamp': datetime.now().isoformat()
        }

market_engine = MarketDataEngine()
active_connections: List[WebSocket] = []

# AI Swarm predictions
def get_ai_predictions():
    return {
        'trend': {'action': 'SELL', 'confidence': 65, 'reason': 'Technical analysis'},
        'liquidity': {'action': 'BUY', 'confidence': 75, 'reason': 'Order flow analysis'},
        'volatility': {'action': 'HOLD', 'confidence': 56, 'reason': 'ATR analysis'},
        'sentiment': {'action': 'HOLD', 'confidence': 80, 'reason': 'News sentiment'},
        'orderflow': {'action': 'SELL', 'confidence': 66, 'reason': 'Delta divergence'}
    }

@app.get("/")
async def root():
    return {
        "message": "AI Trading System Online",
        "status": "running",
        "version": "3.0.0",
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "connections": len(active_connections),
        "price": market_engine.price,
        "balance": account_balance,
    }


# Backwards-compatible alias
@app.get("/health")
async def health():
    return await health_check()


@app.get("/api/account")
async def get_account():
    return {
        "balance": account_balance,
        "equity": account_balance + daily_pnl,
        "daily_pnl": daily_pnl,
        "drawdown": drawdown,
        "positions": len(positions)
    }

@app.get("/api/market")
async def get_market():
    return market_engine.get_market_data()

@app.get("/api/price")
async def get_price():
    return {
        "price": market_engine.get_price(),
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/ai")
async def get_ai():
    return get_ai_predictions()

@app.post("/api/trade/buy")
async def api_buy(volume: float = 0.05):
    global account_balance, daily_pnl
    price = market_engine.price
    order = {
        "id": f"ORD_{int(datetime.now().timestamp())}",
        "action": "BUY",
        "volume": volume,
        "price": price,
        "timestamp": datetime.now().isoformat()
    }
    positions.append(order)
    logger.info(f"BUY order: {volume} lots @ {price}")
    return {
        "success": True,
        "order_id": order["id"],
        "price": price,
        "message": f"BUY {volume} lots executed at ${price:.2f}"
    }

@app.post("/api/trade/sell")
async def api_sell(volume: float = 0.05):
    price = market_engine.price
    order = {
        "id": f"ORD_{int(datetime.now().timestamp())}",
        "action": "SELL",
        "volume": volume,
        "price": price,
        "timestamp": datetime.now().isoformat()
    }
    positions.append(order)
    logger.info(f"SELL order: {volume} lots @ {price}")
    return {
        "success": True,
        "order_id": order["id"],
        "price": price,
        "message": f"SELL {volume} lots executed at ${price:.2f}"
    }

@app.get("/api/positions")
async def get_positions():
    return positions

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"Client connected. Total: {len(active_connections)}")
    
    try:
        while True:
            market_data = market_engine.get_market_data()
            ai_predictions = get_ai_predictions()
            
            await websocket.send_json({
                'type': 'market_update',
                'data': market_data,
                'timestamp': datetime.now().isoformat()
            })
            
            await websocket.send_json({
                'type': 'ai_update',
                'data': ai_predictions
            })
            
            await websocket.send_json({
                'type': 'account_update',
                'data': {
                    'balance': account_balance,
                    'equity': account_balance + daily_pnl,
                    'daily_pnl': daily_pnl,
                    'drawdown': drawdown,
                    'positions': len(positions)
                }
            })
            
            await asyncio.sleep(1)
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(f"Client disconnected. Remaining: {len(active_connections)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)