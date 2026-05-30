from typing import Optional
from pydantic import BaseModel


class LoginRequest(BaseModel):
    username: str
    password: str


class RegisterRequest(BaseModel):
    username: str
    password: str
    email: str


class MT5ConnectRequest(BaseModel):
    login: int
    password: str
    server: str
    symbol: str = "XAUUSD"


class OrderRequest(BaseModel):
    symbol: str
    action: str  # BUY or SELL
    volume: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class ClosePositionRequest(BaseModel):
    ticket: int


class ChatMessageRequest(BaseModel):
    message: str
    context: dict = {}


