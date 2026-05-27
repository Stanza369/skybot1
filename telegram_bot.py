import logging
import asyncio
from datetime import datetime
from typing import Dict

from telegram import Bot

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class TelegramNotifier:
    def __init__(self, token: str, chat_id: str):
        self.bot = Bot(token=token)
        self.chat_id = chat_id

    async def send_message(self, message: str):
        try:
            await self.bot.send_message(chat_id=self.chat_id, text=message, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Telegram send failed: {e}")

    def send_signal(self, signal: Dict):
        emoji = "🟢" if signal["signal"] == "BUY" else ("🔴" if signal["signal"] == "SELL" else "⚪")

        message = (
            f"{emoji} <b>XAUUSD SCALPING SIGNAL</b> {emoji}\n\n"
            f"<b>Signal:</b> {signal['signal']}\n"
            f"<b>Confidence:</b> {signal['ai_prediction'].get('confidence', 0)*100:.0f}%\n"
            f"<b>Probability:</b> {signal['ai_prediction'].get('probability', 0)*100:.0f}%\n\n"
            f"<b>Entry:</b> {signal['entry']:.2f}\n"
            f"<b>Stop Loss:</b> {signal['stop_loss']:.2f}\n"
            f"<b>Take Profit:</b> {signal['take_profit']:.2f}\n\n"
            f"<b>Momentum Burst:</b> {'✅' if signal['momentum_burst'] else '❌'}\n"
            f"<b>Volume Spike:</b> {'✅' if signal['volume_spike'] else '❌'}\n"
            f"<b>Liquidity Sweep:</b> {'⚠️' if signal['liquidity_sweep'] else '✅'}\n"
            f"<b>Inst. Flow:</b> {signal['institutional_flow']:.2f}\n\n"
            f"<b>Time:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )

        asyncio.run(self.send_message(message))

    def send_performance_report(self, stats: Dict):
        message = (
            "📊 <b>TRADING PERFORMANCE REPORT</b> 📊\n\n"
            f"<b>Period:</b> {stats.get('period', 'Daily')}\n"
            f"<b>Total Trades:</b> {stats.get('total_trades', 0)}\n"
            f"<b>Win Rate:</b> {stats.get('win_rate', 0):.1%}\n"
            f"<b>Profit Factor:</b> {stats.get('profit_factor', 0):.2f}\n"
            f"<b>Net Profit:</b> ${stats.get('net_profit', 0):.2f}\n"
            f"<b>Max Drawdown:</b> {stats.get('max_drawdown', 0):.1%}\n"
            f"<b>Sharpe Ratio:</b> {stats.get('sharpe_ratio', 0):.2f}\n"
            f"<b>Best Trade:</b> ${stats.get('best_trade', 0):.2f}\n"
            f"<b>Worst Trade:</b> ${stats.get('worst_trade', 0):.2f}"
        )
        asyncio.run(self.send_message(message))

