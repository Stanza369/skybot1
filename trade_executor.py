import json
import logging
import os
import time
from dataclasses import dataclass
from typing import Dict, Optional

import MetaTrader5 as mt5
import asyncio
import os
from backend.notification_manager import notification_manager

logger = logging.getLogger(__name__)


@dataclass
class TradeState:
    position_ticket: Optional[int] = None
    entry_price: Optional[float] = None
    side: Optional[str] = None
    opened_at: Optional[float] = None


class TradeExecutor:

    def __init__(self, config):


        self.config = config

        self.state_path = os.path.join(
            config.DATA_PATH,
            "state.json"
        )

        self.state = TradeState()

        self.symbol = config.SYMBOL

    def load_state(self):

        try:

            if os.path.exists(self.state_path):

                with open(self.state_path, "r") as f:
                    d = json.load(f)

                self.state = TradeState(
                    position_ticket=d.get("position_ticket"),
                    entry_price=d.get("entry_price"),
                    side=d.get("side"),
                    opened_at=d.get("opened_at"),
                )

        except Exception as e:
            logger.warning(e)

    def save_state(self):

        os.makedirs(self.config.DATA_PATH, exist_ok=True)

        with open(self.state_path, "w") as f:

            json.dump(
                {
                    "position_ticket": self.state.position_ticket,
                    "entry_price": self.state.entry_price,
                    "side": self.state.side,
                    "opened_at": self.state.opened_at,
                },
                f,
            )

    def _ensure_symbol(self):

        info = mt5.symbol_info(self.symbol)

        if info is None:
            raise RuntimeError(f"Symbol not found: {self.symbol}")

        if not info.visible:

            if not mt5.symbol_select(self.symbol, True):
                raise RuntimeError(f"Failed to select {self.symbol}")

    def _check_spread_ok(self, max_spread_points):

        tick = mt5.symbol_info_tick(self.symbol)

        if tick is None:
            return False

        info = mt5.symbol_info(self.symbol)

        point = info.point if info else 0.01

        spread = (tick.ask - tick.bid) / point

        return spread <= max_spread_points

    async def manage_open_position(self):
        """Basic position management + state persistence.

        Current implementation:
          - Loads state on first use.
          - If state indicates a position ticket but it no longer exists, clears state.
          - If no position is tracked, nothing to do.

        Returns nothing; side effects are via MT5 orders/positions.
        """
        try:
            if self.state.position_ticket is None:
                # first loop: try to load persisted state
                self.load_state()

            if self.state.position_ticket is None:
                return

            pos = mt5.positions_get(ticket=self.state.position_ticket)
            if pos is None or len(pos) == 0:
                logger.info("Tracked position not found anymore; clearing state")
                self.state = TradeState()
                self.save_state()
                return

        except Exception as e:
            logger.warning(e)

        return

    async def close_trade(self, ticket: int, comment: str = "AI Reversal") -> bool:
        """Force close a specific position by ticket."""
        try:
            positions = mt5.positions_get(ticket=ticket)
            if not positions:
                return False
            
            p = positions[0]
            symbol = p.symbol
            tick = mt5.symbol_info_tick(symbol)
            
            # Inverse order to close
            order_type = mt5.ORDER_TYPE_SELL if p.type == mt5.POSITION_TYPE_BUY else mt5.ORDER_TYPE_BUY
            price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
            
            request = {
                "action": mt5.TRADE_ACTION_DEAL,
                "symbol": symbol,
                "volume": p.volume,
                "type": order_type,
                "position": ticket,
                "price": price,
                "deviation": 20,
                "magic": self.config.MAGIC,
                "comment": comment,
                "type_time": mt5.ORDER_TIME_GTC,
                "type_filling": mt5.ORDER_FILLING_IOC,
            }
            
            result = mt5.order_send(request)
            if result.retcode == mt5.TRADE_RETCODE_DONE:
                logger.info(f"✅ Position {ticket} closed via {comment}")
                self.state = TradeState()
                self.save_state()
                
                # Notify
                user_id = int(os.getenv('ADMIN_USER_ID', '1'))
                await notification_manager.send_notification(user_id, 'trade_close', {
                    'ticket': ticket,
                    'reason': comment,
                    'profit': result.profit
                })
                return True
            return False
        except Exception as e:
            logger.error(f"Error closing trade: {e}")
            return False

    async def open_trade(self, side: str, lots: float, stop_loss: Optional[float] = None, take_profit: Optional[float] = None) -> Dict[str, Optional[object]]:
        """Open a market trade using MetaTrader5 and persist state.
        Returns dict: {'opened': bool, 'reason': str (if failed), 'order_id': int (if opened)}
        """
        # Logic to handle reversals: If already in a trade of opposite side, close it.
        if self.state.position_ticket and self.state.side != side.upper():
            await self.close_trade(self.state.position_ticket, comment="AI Direction Switch")

        try:
            self._ensure_symbol()

            # Basic spread check (allow up to config.MAX_SPREAD if present)
            max_spread = getattr(self.config, 'MAX_SPREAD', 100)
            tick = mt5.symbol_info_tick(self.symbol)
            info = mt5.symbol_info(self.symbol)
            if tick and info and ((tick.ask - tick.bid) / info.point) > max_spread:
                logger.warning(f"Trade blocked: Spread too high ({ (tick.ask - tick.bid) / info.point } points)")
                return {'opened': False, 'reason': 'spread_too_high'}

            symbol_info = mt5.symbol_info(self.symbol)
            if symbol_info is None:
                return {'opened': False, 'reason': 'symbol_info_missing'}

            point = symbol_info.point if symbol_info else 0.01

            # Build order request similar to other parts of repo
            if side.upper() == 'BUY':
                order_type = mt5.ORDER_TYPE_BUY
            else:
                order_type = mt5.ORDER_TYPE_SELL

            # Choose current price
            if tick is None:
                return {'opened': False, 'reason': 'no_tick'}

            price = float(tick.ask) if side.upper() == 'BUY' else float(tick.bid)

            request = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': self.symbol,
                'volume': float(lots),
                'type': order_type,
                'price': price,
                'deviation': 20,
                'magic': int(getattr(self.config, 'MAGIC', 123456)),
                'comment': 'xauusd_scalper open_trade',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }

            if stop_loss is not None:
                request['sl'] = float(stop_loss)
            if take_profit is not None:
                request['tp'] = float(take_profit)

            result = mt5.order_send(request)
            if result is None:
                return {'opened': False, 'reason': 'order_send_failed'}

            retcode = getattr(result, 'retcode', None)
            comment = getattr(result, 'comment', '')
            order_id = getattr(result, 'order', None) or getattr(result, 'ticket', None)

            # retcode 10009 or 10007 often indicate success depending on broker; treat absence of error string as success
            if retcode is not None and int(retcode) not in (10009, 10007, 0):
                return {'opened': False, 'reason': f'order_failed: {comment}'}

            # Save state
            try:
                self.state.position_ticket = int(order_id) if order_id is not None else None
                self.state.entry_price = float(price)
                self.state.side = side.upper()
                self.state.opened_at = time.time()
                self.save_state()
            except Exception:
                logger.exception('Failed to persist trade state')

            # Best-effort notification
            try:
                user_id = int(os.getenv('ADMIN_USER_ID', '1'))
                notify_data = {
                    'symbol': self.symbol,
                    'action': side.upper(),
                    'volume': lots,
                    'entry_price': price,
                    'stop_loss': stop_loss,
                    'take_profit': take_profit,
                    'order_id': order_id,
                }
                await notification_manager.send_notification(user_id, 'trade', notify_data)
            except Exception:
                logger.exception('Failed to send trade notification')

            return {'opened': True, 'order_id': order_id}

        except Exception as e:
            logger.exception('open_trade exception')
            return {'opened': False, 'reason': str(e)}
