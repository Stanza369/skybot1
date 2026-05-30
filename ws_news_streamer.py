import asyncio
import json
from datetime import datetime
from typing import Set, Any, Dict, List

from news_engine import ForexFactoryEconomicCalendar
from news_ai import NewsImpactAI


class WsNewsStreamer:
    """Broadcasts economic calendar intelligence over WebSocket."""

    def __init__(
        self,
        interval_seconds: int = 30,
        fetch_limit: int = 25,
        broadcast_host: str = "0.0.0.0",
        broadcast_port: int = 0,
        # broadcast_host/port are unused when attached to FastAPI; kept for extensibility.
        ):
        self.interval_seconds = interval_seconds
        self.fetch_limit = fetch_limit

        self.calendar = ForexFactoryEconomicCalendar()
        self.ai = NewsImpactAI()
        self.clients: Set[Any] = set()

        # To avoid spamming alerts with identical payloads.
        self.last_sent_fingerprints: List[str] = []
        self.fingerprint_max = 50

    async def broadcast_loop(self):
        while True:
            try:
                events = self.calendar.fetch_events(limit=self.fetch_limit)
                analyzed = [self.ai.analyze(ev) for ev in events]

                high_impact = [
                    e for e in analyzed if (e.get("impact_level") == "HIGH" or e.get("avoid_trading") is True)
                ]

                payload: Dict[str, Any] = {
                    "type": "economic_calendar",
                    "data": analyzed[:10],
                    "high_impact": high_impact[:5],
                    "timestamp": datetime.now().isoformat(),
                }

                # Simple dedupe fingerprint
                fp = json.dumps(payload.get("high_impact", []), sort_keys=True)[:1000]
                if fp in self.last_sent_fingerprints:
                    await asyncio.sleep(self.interval_seconds)
                    continue

                self.last_sent_fingerprints.append(fp)
                if len(self.last_sent_fingerprints) > self.fingerprint_max:
                    self.last_sent_fingerprints = self.last_sent_fingerprints[-self.fingerprint_max :]

                if self.clients:
                    message = json.dumps(payload)
                    await asyncio.gather(*[c.send_text(message) for c in self.clients], return_exceptions=True)

            except Exception:
                # Fail silent so market streaming is not affected.
                pass

            await asyncio.sleep(self.interval_seconds)

    async def register_client(self, websocket):
        self.clients.add(websocket)

    async def unregister_client(self, websocket):
        if websocket in self.clients:
            self.clients.remove(websocket)

