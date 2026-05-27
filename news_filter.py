import logging
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class NewsEvent:
    currency: str
    impact: str  # HIGH / MEDIUM / LOW
    event: str
    time: datetime  # timezone-aware


class NewsFilter:
    """News blackout filter for trading.

    Provider-less baseline:
    - Uses an internal demo event list so the integration path works immediately.

    Later you can replace `fetch_events()` with:
    - ForexFactory scraping
    - EconomicCalendarParser
    - Any paid API
    - MT5 calendar integration
    """

    def __init__(
        self,
        *,
        mode: str = "OFF",
        currency: str = "USD",
        blackout_before_minutes: int = 30,
        blackout_after_minutes: int = 30,
        fail_closed: bool = True,
        demo_events_enabled: bool = True,
        cache_ttl_seconds: int = 300,
    ):
        self.mode = (mode or "OFF").upper()
        self.currency = (currency or "USD").upper()
        self.blackout_before_minutes = int(blackout_before_minutes)
        self.blackout_after_minutes = int(blackout_after_minutes)
        self.fail_closed = bool(fail_closed)
        self.demo_events_enabled = bool(demo_events_enabled)
        self.cache_ttl_seconds = int(cache_ttl_seconds)

        self._cached_events: List[NewsEvent] = []
        self._cached_at: Optional[datetime] = None

    @staticmethod
    def _utcnow() -> datetime:
        return datetime.now(timezone.utc)

    def _should_protect(self) -> bool:
        return self.mode in {"PROTECT_HIGH", "PROTECT"}

    def _fetch_events(self) -> List[NewsEvent]:
        # Provider-less demo events: creates a HIGH USD event within the next hour.
        # This lets you verify bot skips entries during blackout windows.
        if not self.demo_events_enabled:
            return []

        now = self._utcnow()
        demo_time = now + timedelta(minutes=45)
        return [
            NewsEvent(
                currency=self.currency,
                impact="HIGH",
                event="DEMO_HIGH_IMPACT_EVENT",
                time=demo_time,
            )
        ]

    def _get_cached_events(self) -> List[NewsEvent]:
        now = self._utcnow()
        if self._cached_at is None:
            self._cached_events = self._fetch_events()
            self._cached_at = now
            return self._cached_events

        age = (now - self._cached_at).total_seconds()
        if age >= self.cache_ttl_seconds:
            self._cached_events = self._fetch_events()
            self._cached_at = now
        return self._cached_events

    def should_block_trade(self, *, now: Optional[datetime] = None) -> (bool, Optional[NewsEvent]):
        """Return (block, next_event_in_blackout_or_none)."""
        if not self._should_protect():
            return False, None

        if now is None:
            now = self._utcnow()
        elif now.tzinfo is None:
            # assume local time -> convert to UTC naive handling fallback
            now = now.replace(tzinfo=timezone.utc)

        try:
            events = self._get_cached_events()
        except Exception as e:
            logger.exception("News fetch failed: %s", e)
            if self.fail_closed:
                return True, None
            return False, None

        high_events = [
            ev
            for ev in events
            if ev.currency.upper() == self.currency.upper() and ev.impact.upper() == "HIGH"
        ]

        for ev in sorted(high_events, key=lambda x: x.time):
            window_start = ev.time - timedelta(minutes=self.blackout_before_minutes)
            window_end = ev.time + timedelta(minutes=self.blackout_after_minutes)
            if window_start <= now <= window_end:
                return True, ev

        return False, None


def build_news_filter_from_env() -> NewsFilter:
    # helper to keep main.py clean
    def getenv_int(name: str, default: int) -> int:
        try:
            return int(os.getenv(name, str(default)))
        except Exception:
            return default

    def getenv_bool(name: str, default: bool) -> bool:
        val = os.getenv(name)
        if val is None:
            return default
        return val.strip().lower() in {"1", "true", "yes", "y", "on"}

    return NewsFilter(
        mode=os.getenv("NEWS_MODE", "OFF"),
        currency=os.getenv("NEWS_CURRENCY", "USD"),
        blackout_before_minutes=getenv_int("NEWS_BLACKOUT_BEFORE_MINUTES", 30),
        blackout_after_minutes=getenv_int("NEWS_BLACKOUT_AFTER_MINUTES", 30),
        fail_closed=getenv_bool("NEWS_FAIL_CLOSED", True),
        demo_events_enabled=os.getenv("NEWS_DEMO_EVENTS", "true").strip().lower() in {"1","true","yes","y","on"},
        cache_ttl_seconds=getenv_int("NEWS_FETCH_INTERVAL_SECONDS", 300),
    )

