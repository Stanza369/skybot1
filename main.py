import os
import json
from fastapi import FastAPI, Depends, HTTPException, status, Query
from fastapi.middleware.cors import CORSMiddleware

from dotenv import load_dotenv

from auth import authenticate_user, create_access_token, get_current_user
from mt5_service import MT5Service
from schemas import (
    LoginRequest,
    RegisterRequest,
    MT5ConnectRequest,
    OrderRequest,
    ClosePositionRequest,
    ChatMessageRequest,
)


from user_store import UserStore

user_store = UserStore()


from config import Config
from broker_store import BrokerStore

load_dotenv()


app = FastAPI(title="Trading Dashboard API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

mt5_service = MT5Service()
config_obj = Config()
broker_store = BrokerStore()

# Production-grade execution stack (DB + risk + Telegram)
from production_db import ProductionDatabase
from institutional_risk import InstitutionalRiskManager
from telegram_alerts import TelegramAlertSystem
from production_execution import ProductionTradingBot

production_db = ProductionDatabase()
production_risk = InstitutionalRiskManager(initial_balance=10000.0)
production_telegram = TelegramAlertSystem()
production_bot = ProductionTradingBot(
    db=production_db,
    mt5_service=mt5_service,
    risk=production_risk,
    telegram=production_telegram,
)

@app.on_event("startup")
async def production_startup():
    # Best-effort DB connect; avoid blocking startup if DB is down.
    try:
        await production_bot.initialize()
    except Exception:
        pass







@app.get("/")
async def root():
    return {"message": "Trading Dashboard API", "status": "running"}


@app.post("/api/register")
async def register(request: RegisterRequest):
    # User is created as `pending` and can only log in after admin approval.
    res = user_store.create_user(username=request.username, email=request.email, password=request.password)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return {"success": True, "message": "Registration submitted. Awaiting admin approval."}


@app.post("/api/login")
async def login(request: LoginRequest):
    user = authenticate_user(request.username, request.password)

    if not user:

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = create_access_token({"sub": user["username"]})
    return {"access_token": token, "token_type": "bearer", "username": user["username"]}


@app.get("/api/me")
async def me(current_user=Depends(get_current_user)):
    return {"username": current_user["username"], "email": current_user["email"], "role": current_user["role"]}


@app.post("/api/mt5/connect")
async def mt5_connect(request: MT5ConnectRequest, current_user=Depends(get_current_user)):
    res = mt5_service.connect(login=request.login, password=request.password, server=request.server, symbol=request.symbol)
    return res


@app.post("/api/mt5/disconnect")
async def mt5_disconnect(current_user=Depends(get_current_user)):
    mt5_service.disconnect()
    return {"message": "Disconnected from MT5"}


@app.get("/api/broker/accounts")
async def broker_accounts(current_user=Depends(get_current_user)):
    username = current_user["username"]
    accounts = broker_store.list_accounts(username=username)
    return {"accounts": accounts}


@app.post("/api/broker/add")
async def broker_add(req: dict, current_user=Depends(get_current_user)):


    username = current_user["username"]

    result = broker_store.add_account(
        username=username,
        account_name=req.get("account_name"),
        account_type=req.get("account_type"),
        login=str(req.get("login")),
        password=req.get("password"),
        server=req.get("server"),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/api/broker/delete")
async def broker_delete(req: dict, current_user=Depends(get_current_user)):

    username = current_user["username"]
    result = broker_store.delete_account(
        username=username,
        account_name=req.get("account_name"),
    )
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@app.post("/api/broker/connect")
async def broker_connect(req: dict, current_user=Depends(get_current_user)):
    username = current_user["username"]
    account_name = req.get("account_name")

    got = broker_store.get_account_for_connect(username=username, account_name=account_name)
    if not got.get("success"):
        raise HTTPException(status_code=400, detail=got.get("error"))

    acc = got["account"]
    # symbol is already managed by frontend; default inside service
    res = mt5_service.connect(
        login=int(acc["login"]),
        password=acc["password"],
        server=acc["server"],
        symbol=req.get("symbol") or "XAUUSD",
    )
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res



@app.get("/api/mt5/account")
async def mt5_account(current_user=Depends(get_current_user)):
    info = mt5_service.account_info()
    if not info:
        raise HTTPException(status_code=400, detail="Not connected to MT5")
    return info


@app.get("/api/mt5/symbols")
async def mt5_symbols(current_user=Depends(get_current_user)):
    return {"symbols": mt5_service.get_symbols(limit=50)}


@app.get("/api/market/{symbol}")
async def market(
    symbol: str,
    timeframe: str = "M5",
    count: int = 100,
    current_user=Depends(get_current_user),
):
    data = mt5_service.market_ohlc(symbol=symbol, timeframe=timeframe, count=count)
    if "error" in data:
        raise HTTPException(status_code=400, detail=data["error"])
    return data



@app.post("/api/trade/order")
async def trade_order(request: OrderRequest, current_user=Depends(get_current_user)):
    # Route through production execution stack for risk + persistence + alerts.
    user_id = None
    try:
        # In this repo, current_user has username/email/role; user_id may not be available.
        # Persist as best-effort using a NULL user_id.
        user_id = current_user.get("id")  # type: ignore[attr-defined]
    except Exception:
        user_id = None

    signal = {
        "symbol": request.symbol,
        "action": request.action,
        "volume": request.volume,
        "stop_loss": request.stop_loss,
        "take_profit": request.take_profit,
        "confidence": 0.7,
        "volatility": 1.0,
        "strategy": "AI_Ensemble",
    }

    # If you want the backend to size dynamically, pass volume as None/omit it.
    res = await production_bot.execute_trade(signal=signal, user_id=user_id)
    if not res.get("success"):
        raise HTTPException(status_code=400, detail=res.get("error"))
    return res



@app.get("/api/trade/positions")
async def positions(current_user=Depends(get_current_user)):
    return {"positions": mt5_service.positions()}


@app.post("/api/trade/close")
async def close(req: ClosePositionRequest, current_user=Depends(get_current_user)):
    # Persist/close via production execution stack
    res = await production_bot.close_trade(ticket=req.ticket, user_id=None)
    return res




@app.get("/api/trade/history")
async def history(current_user=Depends(get_current_user)):
    return {"history": mt5_service.order_history(limit=200)}


# ==========================
# REAL AI SIGNAL ENDPOINT
# ==========================
from ai_signal import compute_votes
from pydantic import BaseModel

class AISignalRequest(BaseModel):
    candles: list = []

@app.post("/api/ai/signal")
async def ai_signal(
    symbol: str,
    timeframe: str = "M5",
    req: AISignalRequest = None,
    current_user=Depends(get_current_user),
):
    # req.candles is expected to be sent by the frontend.
    candles = (req.candles if req else [])

    # If frontend didn’t send candles, fetch from MT5.
    if not candles:
        market = mt5_service.market_ohlc(symbol=symbol, timeframe=timeframe, count=200)
        if isinstance(market, dict) and market.get('data'):
            candles = market['data']

    df = pd.DataFrame(candles)
    if df.empty:
        return {"vote": "HOLD", "conf": 0.5, "meta": "No candles"}

    sig = compute_votes(df)
    # Normalize votes to what the frontend expects: array of objects with keys vote/conf/meta
    # (frontend uses renderAiCard and expects {vote,conf,meta} per card)
    votes = sig.get('votes') or []
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "vote": sig.get('vote'),
        "conf": sig.get('conf'),
        "meta": sig.get('meta'),
        "votes": [v for v in votes],
    }


from chat_learning_system import chat_engine, on_trade_complete


from stream_manager import stream_manager
from ws_market_streamer import WsMarketStreamer
from ws_news_streamer import WsNewsStreamer


ws_streamer = WsMarketStreamer(mt5_service=mt5_service, stream_manager=stream_manager)
ws_streamer.start()

news_streamer = WsNewsStreamer(interval_seconds=30, fetch_limit=25)

@app.on_event("startup")
async def start_news_streamer():
    import asyncio
    asyncio.create_task(news_streamer.broadcast_loop())


@app.websocket("/api/ws/news")
async def ws_news(websocket):
    await websocket.accept()
    await news_streamer.register_client(websocket)
    try:
        while True:
            # Keep connection alive; inbound messages are ignored except ping.
            msg = await websocket.receive_text()
            if msg.strip().lower() == "ping":
                await websocket.send_text('{"type":"pong"}')
    except Exception:
        pass
    finally:
        await news_streamer.unregister_client(websocket)


@app.websocket("/api/ws/market")
async def ws_market(websocket):

    # Accept query params: symbol, timeframe
    await websocket.accept()
    params = dict(websocket.query_params)
    symbol = params.get("symbol", "XAUUSD")
    timeframe = params.get("timeframe", "M5")

    await stream_manager.register(websocket, symbol=symbol, timeframe=timeframe)
    try:
        # Keep-alive loop; we ignore inbound messages for now.
        while True:
            msg = await websocket.receive_text()
            # If client sends "ping" respond "pong".
            if msg.strip().lower() == "ping":
                await websocket.send_text('{"type":"pong"}')
    except Exception:
        pass
    finally:
        await stream_manager.unregister(websocket, symbol=symbol, timeframe=timeframe)


@app.get("/api/learning/stats")
async def learning_stats(current_user=Depends(get_current_user)):
    return chat_engine.stats()



@app.post("/api/chat")
async def chat_endpoint(req: ChatMessageRequest, current_user=Depends(get_current_user)):
    user_id = str(current_user.get("username") or current_user.get("email") or "anonymous")
    context = dict(req.context or {})
    context["user_id"] = user_id

    return await chat_engine.process_message(user_id=user_id, message=req.message, context=context)


@app.get("/api/notifications/history")
async def notification_history(
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user)
):

    """Retrieve history of notifications from the log file."""
    history = []
    log_file = config_obj.NOTIFICATION_LOG
    if not os.path.exists(log_file):
        return {"history": []}

    try:
        with open(log_file, "r") as f:
            lines = f.readlines()
            for line in lines[-limit:]:
                history.append(json.loads(line.strip()))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read notification logs: {e}")
    
    return {"history": history[::-1]}
