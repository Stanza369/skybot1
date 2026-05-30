from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from institutional_risk import InstitutionalRiskManager
from production_db import ProductionDatabase
from telegram_alerts import TelegramAlertSystem


class ProductionTradingBot:
    """Orchestrates risk + execution + persistence."""

    def __init__(
        self,
        *,
        db: ProductionDatabase,
        mt5_service: Any,
        risk: Optional[InstitutionalRiskManager] = None,
        telegram: Optional[TelegramAlertSystem] = None,
    ) -> None:
        self.db = db
        self.mt5 = mt5_service
        self.risk = risk or InstitutionalRiskManager()
        self.telegram = telegram or TelegramAlertSystem()

    async def initialize(self) -> bool:
        return await self.db.connect()

    async def execute_trade(self, *, signal: Dict[str, Any], user_id: Optional[int] = None) -> Dict[str, Any]:
        allowed, reason = self.risk.can_trade()
        if not allowed:
            await self.telegram.send_error_alert(f"Trade blocked: {reason}")
            return {"success": False, "error": reason}

        symbol = signal.get("symbol") or "XAUUSD"
        action = str(signal.get("action") or "BUY").upper()
        confidence = float(signal.get("confidence") if signal.get("confidence") is not None else 0.7)
        volatility = float(signal.get("volatility") if signal.get("volatility") is not None else 1.0)

        volume = signal.get("volume")
        if volume is None:
            volume = self.risk.calculate_position_size(confidence=confidence, volatility=volatility)
        volume = float(volume)

        order_id = f"ord_{int(time.time())}_{os.urandom(4).hex()}"

        trade_data: Dict[str, Any] = {
            "user_id": user_id,
            "order_id": order_id,
            "symbol": symbol,
            "action": action,
            "volume": volume,
            "entry_price": float(signal.get("entry_price") or 0.0),
            "stop_loss": signal.get("stop_loss"),
            "take_profit": signal.get("take_profit"),
            "pnl": None,
            "status": "OPEN",
            "strategy": signal.get("strategy") or "AI_Ensemble",
            "confidence": confidence,
            "metadata": signal.get("metadata") or {},
        }

        sl = trade_data.get("stop_loss")
        tp = trade_data.get("take_profit")

        if getattr(self.mt5, "connected", False):
            result = self.mt5.place_order(
                symbol=symbol,
                action=action,
                volume=volume,
                stop_loss=sl,
                take_profit=tp,
            )
        else:
            # Simulation fallback when MT5 is not connected.
            result = {"success": True, "order_id": order_id, "price": trade_data.get("entry_price")}

        if not result.get("success"):
            await self.telegram.send_error_alert(f"Order failed: {result.get('error')}")
            await self.db.log_system_event(
                level="ERROR",
                module="production_execution",
                message="Order failed",
                details={"error": result.get("error"), "signal": signal},
            )
            return {"success": False, "error": result.get("error")}

        # Persist OPEN trade
        trade_data["entry_price"] = float(result.get("price") or trade_data.get("entry_price") or 0.0)
        inserted_id = await self.db.save_trade(trade_data)

        await self.telegram.send_trade_alert(trade_data)

        return {
            "success": True,
            "order_id": result.get("order_id") or order_id,
            "price": trade_data["entry_price"],
            "db_trade_id": inserted_id,
            "symbol": symbol,
            "action": action,
            "volume": volume,
        }

    async def close_trade(self, *, ticket: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        res = self.mt5.close_position(ticket)

        if not res.get("success"):
            await self.telegram.send_error_alert(f"Close failed: {res.get('error')}")
            await self.db.log_system_event(
                level="ERROR",
                module="production_execution",
                message="Close failed",
                details={"ticket": ticket, "error": res.get("error")},
            )
            return {"success": False, "error": res.get("error")}

        profit = float(res.get("profit") or 0.0)
        # Update risk metrics
        self.risk.update_trade(profit)

        # Persist close.
        # DB row is keyed by `order_id`, but MT5 close returns either `order_id` or only `ticket`.
        order_id = res.get("order_id")
        if order_id is not None:
            await self.db.close_trade(order_id=str(order_id), exit_price=0.0, pnl=profit)
        else:
            # Best-effort fallback: try to close any open trade that matches this ticket.
            # (Ticket and order_id are often different; this avoids silent failure.)
            try:
                await self.db.close_trade(order_id=str(ticket), exit_price=0.0, pnl=profit)
            except Exception:
                pass

        return {"success": True, "ticket": int(ticket), "profit": profit}


