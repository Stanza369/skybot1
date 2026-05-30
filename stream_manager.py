from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StreamKey:
    symbol: str
    timeframe: str


class StreamManager:
    """In-memory websocket pub/sub.

    Keeps track of connected websocket clients per (symbol,timeframe).
    """

    def __init__(self) -> None:
        self._clients: Dict[StreamKey, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def register(self, websocket: WebSocket, *, symbol: str, timeframe: str) -> None:
        key = StreamKey(symbol=symbol, timeframe=timeframe)
        async with self._lock:
            self._clients.setdefault(key, set()).add(websocket)

    async def unregister(self, websocket: WebSocket, *, symbol: str, timeframe: str) -> None:
        key = StreamKey(symbol=symbol, timeframe=timeframe)
        async with self._lock:
            conns = self._clients.get(key)
            if not conns:
                return
            conns.discard(websocket)
            if not conns:
                self._clients.pop(key, None)

    async def broadcast(self, payload: Dict[str, Any], *, symbol: str, timeframe: str) -> None:
        key = StreamKey(symbol=symbol, timeframe=timeframe)
        msg = json.dumps(payload, separators=(",", ":"))

        async with self._lock:
            conns = list(self._clients.get(key, set()))

        if not conns:
            return

        stale: Set[WebSocket] = set()
        for ws in conns:
            try:
                await ws.send_text(msg)
            except Exception:
                stale.add(ws)

        if stale:
            async with self._lock:
                conns_set = self._clients.get(key)
                if conns_set:
                    conns_set.difference_update(stale)


stream_manager = StreamManager()

