import json
import logging
import smtplib
from datetime import datetime
from email.mime.text import MIMEText
from typing import Dict, Any

from config import Config
from telegram_bot import TelegramNotifier

logger = logging.getLogger(__name__)

class NotificationService:
    """Unified notification service handling Email, SMS, and Telegram."""

    def __init__(self):
        self.config = Config()
        self.telegram = TelegramNotifier(self.config.TELEGRAM_TOKEN, self.config.TELEGRAM_CHAT_ID)
        
        self.twilio_client = None
        if self.config.SMS_ENABLED:
            try:
                from twilio.rest import Client
                self.twilio_client = Client(self.config.TWILIO_SID, self.config.TWILIO_TOKEN)
            except ImportError:
                logger.error("Twilio package not found. Run: pip install twilio")

    def _log_notification(self, channel: str, message: str, data: Dict[str, Any] = None):
        """Log notification to a JSONL file for dashboard history."""
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "channel": channel,
            "message": message,
            "data": data or {}
        }
        try:
            with open(self.config.NOTIFICATION_LOG, "a") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")

    def send_email(self, subject: str, body: str):
        if not self.config.EMAIL_ENABLED:
            return

        msg = MIMEText(body)
        msg['Subject'] = subject
        msg['From'] = self.config.SMTP_USER
        msg['To'] = self.config.EMAIL_RECEIVER

        try:
            with smtplib.SMTP(self.config.SMTP_SERVER, self.config.SMTP_PORT) as server:
                server.starttls()
                server.login(self.config.SMTP_USER, self.config.SMTP_PASS)
                server.send_message(msg)
            self._log_notification("Email", body, {"subject": subject})
            logger.info("Email notification sent.")
        except Exception as e:
            logger.error(f"Email send failed: {e}")

    def send_sms(self, message: str):
        if not self.config.SMS_ENABLED or not self.twilio_client:
            return

        try:
            self.twilio_client.messages.create(
                body=message,
                from_=self.config.TWILIO_FROM,
                to=self.config.SMS_RECEIVER
            )
            self._log_notification("SMS", message)
            logger.info("SMS notification sent.")
        except Exception as e:
            logger.error(f"SMS send failed: {e}")

    def notify_signal(self, signal: Dict[str, Any]):
        """Broadcast trade signal across enabled channels."""
        emoji = "🟢" if signal["signal"] == "BUY" else "🔴"
        summary = f"{emoji} {signal['signal']} XAUUSD @ {signal['entry']:.2f}"
        detailed_body = (
            f"Signal: {signal['signal']}\n"
            f"Entry: {signal['entry']:.2f}\n"
            f"SL: {signal['stop_loss']:.2f}\n"
            f"TP: {signal['take_profit']:.2f}"
        )

        if self.config.TELEGRAM_ENABLED:
            self.telegram.send_signal(signal)
            self._log_notification("Telegram", summary, signal)

        if self.config.EMAIL_ENABLED:
            self.send_email(f"Trading Signal: {signal['signal']}", detailed_body)

        if self.config.SMS_ENABLED:
            self.send_sms(summary)

    def notify_alert(self, title: str, message: str):
        """General purpose alerts (e.g. system errors, performance milestones)."""
        if self.config.TELEGRAM_ENABLED:
            import asyncio
            asyncio.run(self.telegram.send_message(f"<b>{title}</b>\n{message}"))
            self._log_notification("Telegram", f"{title}: {message}")
        
        self.send_email(title, message)
        self.send_sms(f"{title}: {message}")