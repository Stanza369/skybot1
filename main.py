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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="AI Trading System", version="3.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        logger.info("Client connected. Total: %s", len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        logger.info("Client disconnected. Remaining: %s", len(self.active_connections))

    async def broadcast(self, message: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)


manager = ConnectionManager()


class MarketDataEngine:
    def __init__(self):
        self.current_price = 2650.00
        self.price_history: List[float] = []

    def get_live_price(self) -> float:
        """Fetch live price from Yahoo Finance. Falls back to simulated prices."""
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
            logger.error("Price fetch error: %s", e)

        # Fallback to simulated
        change = (np.random.random() - 0.5) * 1.5
        self.current_price += float(change)
        self.current_price = round(self.current_price, 2)
        self.price_history.append(self.current_price)
        if len(self.price_history) > 100:
            self.price_history.pop(0)
        return self.current_price

    def get_market_data(self) -> dict:
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
            "volume": int(np.random.randint(1_000_000, 5_000_000)),
            "spread": float(round(np.random.uniform(10, 25), 1)),
        }


market_engine = MarketDataEngine()


async def market_broadcaster():
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
            logger.error("Broadcaster error: %s", e)
            await asyncio.sleep(5)


async def ai_broadcaster():
    # Placeholder AI broadcaster; replace with real signals later.
    while True:
        try:
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
            logger.error("AI broadcaster error: %s", e)
            await asyncio.sleep(5)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


@app.get("/")
async def root():
    return {
        "message": "AI Trading System Online",
        "status": "running",
        "version": "3.0.0",
        "timestamp": datetime.now().isoformat(),
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
    logger.info("BUY order: %s lots", volume)
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
    logger.info("SELL order: %s lots", volume)
    return {
        "success": True,
        "order_id": f"ORD_{datetime.now().strftime('%Y%m%d%H%M%S')}",
        "price": market_engine.current_price,
        "message": f"SELL {volume} lots executed at ${market_engine.current_price:.2f}",
    }


@app.get("/dashboard")
async def serve_dashboard():
    # Use file path relative to repo root
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dashboard_path = os.path.join(base_dir, "dashboard.html")
    with open(dashboard_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())


@app.on_event("startup")
async def startup_event():
    logger.info("Starting AI Trading System...")
    # Start broadcasters for live UI
    asyncio.create_task(market_broadcaster())
    asyncio.create_task(ai_broadcaster())
    logger.info("System online!")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

