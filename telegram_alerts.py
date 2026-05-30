from __future__ import annotations

import os
from typing import Any, Dict, Optional


class TelegramAlertSystem:
    """Instant trade notifications via Telegram (best-effort)."""

    def __init__(self, *, bot_token: Optional[str] = None, chat_id: Optional[str] = None) -> None:
        self.bot_token = bot_token or os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")
        self.enabled = bool(self.bot_token and self.chat_id)

    async def send_alert(self, message: str, trade_data: Optional[Dict[str, Any]] = None) -> None:
        if not self.enabled:
            return

        import aiohttp

        if trade_data:
            formatted = (
                "\n".join(
                    [
                        "🚨 *TRADE ALERT*",
                        f"*Action:* {trade_data.get('action', 'N/A')}",
                        f"*Symbol:* {trade_data.get('symbol', 'XAUUSD')}",
                        f"*Volume:* {trade_data.get('volume', 0)} lots",
                        f"*Entry:* ${float(trade_data.get('entry_price') or 0):.2f}",
                        f"*SL:* ${float(trade_data.get('stop_loss') or 0):.2f}",
                        f"*TP:* ${float(trade_data.get('take_profit') or 0):.2f}",
                        f"*Confidence:* {float(trade_data.get('confidence') or 0):.0%}",
                        message,
                    ]
                )
            )
        else:
            formatted = message

        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": formatted,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True,
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    # Ignore non-200 to keep trading loop robust.
                    await resp.text()
        except Exception:
            # Best-effort only.
            return

    async def send_trade_alert(self, trade: Dict[str, Any]) -> None:
        await self.send_alert("✅ *TRADE EXECUTED*", trade_data=trade)

    async def send_error_alert(self, error: str) -> None:
        await self.send_alert(f"⚠️ *SYSTEM ERROR*\n\n{error}")

