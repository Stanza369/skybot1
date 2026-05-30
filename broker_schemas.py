from pydantic import BaseModel
from typing import Literal, Optional


class BrokerAddRequest(BaseModel):
    account_name: str
    account_type: Literal["demo", "funded"]
    login: int
    password: str
    server: str


class BrokerDeleteRequest(BaseModel):
    account_name: str


class BrokerConnectRequest(BaseModel):
    account_name: str
    symbol: Optional[str] = "XAUUSD"

