from typing import Dict, Any, Tuple
import re


class NewsImpactAI:
    """Rule-based news impact analyzer for XAUUSD.

    Output schema used by WebSocket + frontend:
      - gold_bias: BULLISH | BEARISH | NEUTRAL | VOLATILE
      - impact_level: HIGH | MEDIUM | LOW
      - impact_score: float 0..1
      - confidence: float 0..1
      - avoid_trading: bool
      - suggested_action: BUY | SELL | AVOID | MONITOR
    """

    high_impact_keywords = [
        "non-farm",
        "nfp",
        "cpi",
        "ppi",
        "fomc",
        "federal open",
        "interest rate",
        "interest rates",
        "rates",
        "gdp",
        "retail sales",
        "unemployment",
        "employment",
    ]

    def analyze(self, event: Dict[str, Any]) -> Dict[str, Any]:
        currency = str(event.get("currency") or "").upper()
        title = str(event.get("event") or "")
        impact_num = int(event.get("impact") or 0)

        impact_level = self._impact_level(impact_num)
        base_score = self._impact_score_from_level(impact_level)

        # Currency relevance for gold: USD has direct dollar effect.
        currency_multiplier = 1.0 if currency == "USD" else (0.65 if currency else 0.4)

        # Keyword importance multiplier.
        kw_boost = 1.0
        title_l = title.lower()
        is_high_keyword = any(k in title_l for k in self.high_impact_keywords)
        if is_high_keyword:
            kw_boost = 1.25

        impact_score = min(1.0, base_score * currency_multiplier * kw_boost)

        # Determine directional bias using actual vs forecast.
        # Generic numeric compare (best-effort). If cannot parse, fall back to volatility.
        actual_num = self._parse_numeric(event.get("actual"))
        forecast_num = self._parse_numeric(event.get("forecast"))

        gold_bias = "NEUTRAL"
        confidence = 0.5
        suggested_action = "MONITOR"
        avoid_trading = False

        if is_high_keyword and impact_level == "HIGH":
            # Big events: we strongly recommend avoiding new scalps near time.
            avoid_trading = True
            gold_bias = "VOLATILE"
            confidence = 0.75
            suggested_action = "AVOID"
        else:
            if currency == "USD":
                # Softer USD data tends to be bullish for gold.
                # Here: if actual < forecast => weaker USD-like reading => bullish gold.
                if actual_num is not None and forecast_num is not None:
                    if actual_num < forecast_num:
                        gold_bias = "BULLISH"
                        confidence = 0.7
                        suggested_action = "BUY"
                    elif actual_num > forecast_num:
                        gold_bias = "BEARISH"
                        confidence = 0.7
                        suggested_action = "SELL"
                    else:
                        gold_bias = "NEUTRAL"
                        confidence = 0.55
                        suggested_action = "MONITOR"

                # CPI/PPI often have special behavior; if keyword present, treat stronger inflation
                # as potentially hawkish (stronger USD) => bearish gold.
                if any(k in title_l for k in ["cpi", "ppi", "inflation"]):
                    if actual_num is not None and forecast_num is not None:
                        if actual_num > forecast_num:
                            gold_bias = "BEARISH"
                            confidence = max(confidence, 0.72)
                            suggested_action = "SELL"
                        elif actual_num < forecast_num:
                            gold_bias = "BULLISH"
                            confidence = max(confidence, 0.72)
                            suggested_action = "BUY"

                # Employment: weaker jobs => bullish gold (typically USD weaker).
                if any(k in title_l for k in ["non-farm", "nfp", "unemployment", "jobs", "employment"]):
                    if actual_num is not None and forecast_num is not None:
                        if actual_num < forecast_num:
                            gold_bias = "BULLISH"
                            confidence = max(confidence, 0.72)
                            suggested_action = "BUY"
                        elif actual_num > forecast_num:
                            gold_bias = "BEARISH"
                            confidence = max(confidence, 0.72)
                            suggested_action = "SELL"

        return {
            "event": title,
            "currency": currency,
            "impact_level": impact_level,
            "impact_score": impact_score,
            "confidence": confidence,
            "gold_bias": gold_bias,
            "actual": event.get("actual", ""),
            "forecast": event.get("forecast", ""),
            "previous": event.get("previous", ""),
            "time": event.get("time", ""),
            "date": event.get("date", ""),
            "avoid_trading": avoid_trading,
            "suggested_action": suggested_action,
            "timestamp": event.get("timestamp"),
            "reason": self._reason_string(title, actual_num, forecast_num, is_high_keyword, currency),
        }

    def _impact_level(self, impact_num: int) -> str:
        if impact_num >= 3:
            return "HIGH"
        if impact_num >= 2:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _impact_score_from_level(level: str) -> float:
        return {"HIGH": 0.95, "MEDIUM": 0.55, "LOW": 0.25}.get(level, 0.25)

    @staticmethod
    def _parse_numeric(val) -> Any:
        if val is None:
            return None
        s = str(val).strip()
        if not s:
            return None

        # remove commas and percent
        s = s.replace(",", "")
        s = s.replace("%", "")

        # Handle K/M suffixes (approx)
        m = re.match(r"^(-?\d+(?:\.\d+)?)([KMB])$", s, re.IGNORECASE)
        if m:
            num = float(m.group(1))
            suf = m.group(2).upper()
            mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(suf, 1)
            return num * mult

        try:
            return float(s)
        except Exception:
            return None

    @staticmethod
    def _reason_string(title: str, actual_num, forecast_num, is_high_keyword: bool, currency: str) -> str:
        title_l = title.lower()
        if is_high_keyword:
            return f"High-impact event detected ({title})" + (" for USD" if currency == "USD" else "")

        if actual_num is not None and forecast_num is not None:
            if any(k in title_l for k in ["cpi", "ppi", "inflation"]):
                return f"Inflation-style compare: actual {actual_num} vs forecast {forecast_num}"
            if any(k in title_l for k in ["non-farm", "nfp", "unemployment", "jobs", "employment"]):
                return f"Jobs-style compare: actual {actual_num} vs forecast {forecast_num}"
            return f"Actual vs forecast compare: {actual_num} vs {forecast_num}"

        return "Rule-based compare unavailable (missing/invalid actual/forecast numbers)"

