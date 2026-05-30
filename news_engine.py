import requests
from bs4 import BeautifulSoup
from datetime import datetime
from typing import Dict, List, Optional
import re


class ForexFactoryEconomicCalendar:
    """Fetches and parses the ForexFactory economic calendar HTML.

    Note: ForexFactory markup may change. This parser is defensive and returns
    only best-effort extracted rows.
    """

    URL = "https://www.forexfactory.com/calendar"

    def __init__(self, timeout_seconds: int = 15):
        self.timeout_seconds = timeout_seconds

        # Gold reacts mostly to USD; we also include common macro currencies
        # to give context to the dashboard.
        self.relevant_currencies = {"USD", "EUR", "GBP", "JPY", "CNY"}

    def fetch_events(self, limit: int = 25) -> List[Dict]:
        events: List[Dict] = []

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            )
        }

        resp = requests.get(self.URL, headers=headers, timeout=self.timeout_seconds)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")

        # ForexFactory uses `tr.calendar__row` for each event.
        rows = soup.select("tr.calendar__row")
        for row in rows[: max(0, limit)]:
            try:
                currency = self._txt(row.select_one(".calendar__currency"))
                if not currency:
                    continue

                currency = currency.strip().upper()
                if currency not in self.relevant_currencies:
                    continue

                time_txt = self._txt(row.select_one(".calendar__time"))
                date_txt = self._txt(row.select_one(".calendar__date"))

                # The impact icon group is represented with `.calendar__impact`.
                impact_el = row.select_one(".calendar__impact")
                impact = self._impact_value(impact_el)

                title_el = row.select_one(".calendar__event-title") or row.select_one(
                    ".calendar__event"
                )
                title = self._txt(title_el)

                actual = self._txt(row.select_one(".calendar__actual"))
                forecast = self._txt(row.select_one(".calendar__forecast"))
                previous = self._txt(row.select_one(".calendar__previous"))

                if not title:
                    continue

                events.append(
                    {
                        "currency": currency,
                        "impact": impact,  # 0..3-ish (best effort)
                        "event": title,
                        "actual": actual,
                        "forecast": forecast,
                        "previous": previous,
                        "date": date_txt,
                        "time": time_txt,
                        "timestamp": datetime.now().isoformat(),
                    }
                )
            except Exception:
                continue

        return events

    @staticmethod
    def _txt(el) -> str:
        if not el:
            return ""
        return el.get_text(strip=True)

    @staticmethod
    def _impact_value(impact_el) -> int:
        """Best-effort numeric impact from icon count."""
        if not impact_el:
            return 0

        # Sometimes icons are <i> tags.
        i_tags = impact_el.find_all("i")
        if i_tags:
            return min(3, max(0, len(i_tags)))

        # Fallback: count visually by number of filled stars-ish.
        text = impact_el.get_text(" ", strip=True)
        m = re.search(r"(\d+)", text)
        if m:
            try:
                return min(3, int(m.group(1)))
            except Exception:
                pass
        return 0

