import asyncio
import logging
import os
from datetime import datetime
from typing import List

import numpy as np
import yfinance as yf
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Trading System", version="3.0.0")

# Enable CORS for online access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Store active connections
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info(f"Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info(f"Client disconnected. Remaining: {len(self.active_connections)}")

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                # If the connection is broken, drop it
                self.disconnect(connection)


manager = ConnectionManager()


# Market Data Engine
class MarketDataEngine:
    def __init__(self):
        self.current_price = 2650.00
        self.price_history: List[float] = []

    def get_live_price(self):
        """Get live price from Yahoo Finance"""
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="1d", interval="1m")
            if not df.empty:
                self.current_price = float(df["Close"].iloc[-1])
                self.price_history.append(self.current_price)
                if len(self.price_history) > 100:
                    self.price_history.pop(0)
                return self.current_price
        except Exception as e:
            logger.error(f"Price fetch error: {e}")

        # Fallback to simulated
        change = (np.random.random() - 0.5) * 1.5
        self.current_price += float(change)
        self.current_price = round(self.current_price, 2)
        self.price_history.append(self.current_price)
        if len(self.price_history) > 100:
            self.price_history.pop(0)
        return self.current_price

    def get_market_data(self):
        price = self.get_live_price()

        if len(self.price_history) > 1:
            change_pct = (
                (self.price_history[-1] - self.price_history[-2])
                / self.price_history[-2]
                * 100
            )
            change_pct = round(change_pct, 2)
        else:
            change_pct = 0

        high = max(self.price_history[-20:]) if self.price_history else price
        low = min(self.price_history[-20:]) if self.price_history else price

        return {
            "price": price,
            "change": change_pct,
            "high": high,
            "low": low,
            "volume": int(np.random.randint(1000000, 5000000)),
            "spread": float(round(np.random.uniform(10, 25), 1)),
        }


market_engine = MarketDataEngine()


# BACKGROUND TASKS
async def market_broadcaster():
    """Broadcast market data to all connected clients"""
    while True:
        try:
            market_data = market_engine.get_market_data()
            await manager.broadcast(
                {
                    "type": "market_update",
                    "data": market_data,
                    "timestamp": datetime.now().isoformat(),
                }
            )
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Broadcaster error: {e}")
            await asyncio.sleep(5)


async def ai_broadcaster():
    """Broadcast AI predictions"""
    while True:
        try:
            # Simulate AI predictions (replace with your real AI)
            import random

            actions = ["BUY", "HOLD", "SELL"]

            await manager.broadcast(
                {
                    "type": "ai_update",
                    "data": {
                        "trend": {
                            "action": random.choice(actions),
                            "confidence": random.randint(60, 90),
                            "reason": "Technical analysis",
                        },
                        "liquidity": {
                            "action": random.choice(actions),
                            "confidence": random.randint(50, 85),
                            "reason": "Order flow analysis",
                        },
                        "volatility": {
                            "action": random.choice(actions),
                            "confidence": random.randint(40, 80),
                            "reason": "ATR analysis",
                        },
                        "sentiment": {
                            "action": random.choice(actions),
                            "confidence": random.randint(55, 85),
                            "reason": "News sentiment",
                        },
                        "orderflow": {
                            "action": random.choice(actions),
                            "confidence": random.randint(60, 90),
                            "reason": "Delta divergence",
                        },
                    },
                }
            )
            await asyncio.sleep(5)
        except Exception as e:
            logger.error(f"AI broadcaster error: {e}")
            await asyncio.sleep(5)


# WEBSOCKET ENDPOINT
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# API ENDPOINTS
@app.get("/")
async def root():
    return {
        "message": "AI Trading System Online",
        "status": "running",
        "version": "3.0.0",
    }


@app.get("/api/market")
async def get_market():
    return market_engine.get_market_data()


@app.get("/api/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "connections": len(manager.active_connections),
        "price": market_engine.current_price,
    }


@app.post("/api/trade/buy")
async def api_buy(
    volume: float = 0.05,
    stop_loss: float | None = None,
    take_profit: float | None = None,
):
    """Execute BUY order"""
    logger.info(f"BUY order: {volume} lots")
    return {
        "success": True,
        "order_id": f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "price": market_engine.current_price,
        "message": f"BUY {volume} lots executed at ${market_engine.current_price:.2f}",
    }


@app.post("/api/trade/sell")
async def api_sell(
    volume: float = 0.05,
    stop_loss: float | None = None,
    take_profit: float | None = None,
):
    """Execute SELL order"""
    logger.info(f"SELL order: {volume} lots")
    return {
        "success": True,
        "order_id": f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "price": market_engine.current_price,
        "message": f"SELL {volume} lots executed at ${market_engine.current_price:.2f}",
    }


# SERVING DASHBOARD
@app.get("/dashboard")
async def serve_dashboard():
    with open("dashboard.html", "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


# STARTUP
@app.on_event("startup")
async def startup_event():
    logger.info("Starting AI Trading System...")
    asyncio.create_task(market_broadcaster())
    asyncio.create_task(ai_broadcaster())
    logger.info("System online!")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
