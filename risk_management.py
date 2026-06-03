"""
risk_management.py - Position Sizing & Drawdown Protection
Enterprise-grade risk controls for trading system
"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Optional, List
from pathlib import Path

logger = logging.getLogger(__name__)

@dataclass
class RiskProfile:
    """Account-level risk parameters"""
    account_balance: float
    account_equity: float
    max_daily_loss_percent: float = 2.0  # Max 2% loss per day
    max_drawdown_percent: float = 5.0    # Max 5% underwater
    max_position_size: float = 1.0       # Max 1 lot
    min_position_size: float = 0.01      # Min 0.01 lot
    risk_per_trade_percent: float = 1.0  # 1% risk per trade
    max_positions_open: int = 5          # Max 5 concurrent

    @property
    def daily_loss_limit(self) -> float:
        """Maximum loss allowed today in dollars"""
        return self.account_balance * self.max_daily_loss_percent / 100.0

    @property
    def drawdown_limit(self) -> float:
        """Maximum drawdown allowed in dollars"""
        return self.account_equity * self.max_drawdown_percent / 100.0

class PositionSizer:
    """Calculate optimal position size using Kelly Criterion with volatility adjustment"""

    def __init__(self, risk_profile: RiskProfile):
        self.risk_profile = risk_profile

    def calculate_size(self,
                      entry_price: float,
                      stop_loss_price: float,
                      volatility: float,
                      win_rate: float = 0.55,
                      profit_factor: float = 1.5) -> float:
        """
        Calculate position size using advanced Kelly Criterion

        Args:
            entry_price: Entry price in USD
            stop_loss_price: Stop loss price in USD
            volatility: Annualized volatility (0.15 = 15%)
            win_rate: Historical win rate (0.55 = 55%)
            profit_factor: Avg win / avg loss (1.5 = 1.5:1)

        Returns:
            Optimal position size in lots
        """
        # Risk amount per trade
        risk_amount = (self.risk_profile.account_equity *
                      self.risk_profile.risk_per_trade_percent / 100.0)

        # Distance to stop loss
        stop_distance = abs(entry_price - stop_loss_price)
        if stop_distance < 0.01:
            return self.risk_profile.min_position_size

        # Naive Kelly fraction: f = (bp - q) / b
        # where p = win prob, q = loss prob, b = avg win/loss
        kelly_fraction = (profit_factor * win_rate - (1 - win_rate)) / profit_factor
        kelly_fraction = max(0.0, min(kelly_fraction, 0.25))  # Cap at 25%

        # Volatility adjustment (higher vol = smaller position)
        vol_factor = 0.02 / max(volatility, 0.001)  # 2% target vol
        vol_factor = max(0.1, min(vol_factor, 2.0))  # Bound adjustment

        # Calculate position size
        # For gold: 1 lot = 100 oz, 1 pip = $0.10 per lot
        pip_value = 0.10  # XAU/USD pip value per lot
        position_size = (risk_amount * kelly_fraction * vol_factor) / (stop_distance * pip_value)

        # Apply limits
        position_size = max(
            self.risk_profile.min_position_size,
            min(position_size, self.risk_profile.max_position_size)
        )

        # Round to valid lot size (0.01 increments)
        position_size = round(position_size, 2)

        logger.info(f"Position sizing: risk={risk_amount:.2f}, " +
                   f"kelly={kelly_fraction:.2f}, vol_factor={vol_factor:.2f}, size={position_size:.2f}")

        return position_size

class RiskMonitor:
    """Real-time monitoring of account risk metrics"""

    def __init__(self, risk_profile: RiskProfile, log_file: str = "trade_log.json"):
        self.risk_profile = risk_profile
        self.log_file = Path(log_file)
        self.trades: List[Dict] = []
        self.daily_pnl = 0.0
        self.peak_equity = risk_profile.account_equity
        self.current_drawdown = 0.0
        self.alert_history: List[str] = []

        self._load_trade_log()

    def _load_trade_log(self):
        """Load existing trade history"""
        if self.log_file.exists():
            try:
                with open(self.log_file) as f:
                    data = json.load(f)
                self.trades = data.get('trades', [])
                logger.info(f"Loaded {len(self.trades)} trades from history")
            except Exception as e:
                logger.warning(f"Could not load trade log: {e}")

    def record_trade(self,
                    symbol: str,
                    direction: str,
                    entry_price: float,
                    size: float,
                    stop_loss: float,
                    take_profit: float,
                    commission: float = 0.0):
        """Record a new trade execution"""
        trade = {
            'timestamp': datetime.now().isoformat(),
            'symbol': symbol,
            'direction': direction,
            'entry_price': entry_price,
            'size': size,
            'stop_loss': stop_loss,
            'take_profit': take_profit,
            'commission': commission,
            'status': 'open'
        }
        self.trades.append(trade)
        self._save_trade_log()

        logger.info(f"Recorded {direction} trade: {size:.2f} lots @ {entry_price:.2f}")
        return trade

    def close_trade(self, trade_id: int, exit_price: float, exit_time: Optional[str] = None):
        """Mark trade as closed and calculate P&L"""
        if trade_id >= len(self.trades):
            logger.error(f"Trade ID {trade_id} not found")
            return None

        trade = self.trades[trade_id]
        if trade['status'] == 'closed':
            logger.warning(f"Trade {trade_id} already closed")
            return trade

        # Calculate P&L
        entry = trade['entry_price']
        direction = trade['direction']
        size = trade['size']

        if direction == 'BUY':
            pnl = (exit_price - entry) * size * 100  # 100 oz per lot
        else:  # SELL
            pnl = (entry - exit_price) * size * 100

        pnl -= trade['commission']  # Subtract commission

        # Update trade record
        trade['exit_price'] = exit_price
        trade['exit_time'] = exit_time or datetime.now().isoformat()
        trade['pnl'] = pnl
        trade['status'] = 'closed'
        trade['pnl_percent'] = (pnl / (entry * size * 100)) * 100 if entry != 0 else 0

        # Update metrics
        self.daily_pnl += pnl
        self.risk_profile.account_equity += pnl

        # Update drawdown
        if self.risk_profile.account_equity > self.peak_equity:
            self.peak_equity = self.risk_profile.account_equity
        self.current_drawdown = max(0,
            (self.peak_equity - self.risk_profile.account_equity) / self.peak_equity * 100)

        self._save_trade_log()
        self._check_risk_alerts()

        logger.info(f"Closed trade {trade_id}: PnL={pnl:.2f} ({trade['pnl_percent']:.2f}%)")
        return trade

    def _check_risk_alerts(self):
        """Check for risk violations and generate alerts"""
        alerts = []

        # Daily loss limit
        if self.daily_pnl <= -self.risk_profile.daily_loss_limit:
            alert = f"CRITICAL: Daily loss limit reached (${self.daily_pnl:.2f})"
            alerts.append(alert)
            logger.error(alert)

        # Drawdown limit
        if self.current_drawdown >= self.risk_profile.max_drawdown_percent:
            alert = f"WARNING: Drawdown at {self.current_drawdown:.2f}% (limit: {self.risk_profile.max_drawdown_percent}%)"
            alerts.append(alert)
            logger.warning(alert)

        # Multiple consecutive losses
        if len(self.trades) >= 3:
            recent_trades = [t for t in self.trades[-3:] if t['status'] == 'closed']
            losing_streak = sum(1 for t in recent_trades if t.get('pnl', 0) < 0)
            if losing_streak == 3:
                alert = "WARNING: 3 consecutive losing trades"
                alerts.append(alert)
                logger.warning(alert)

        self.alert_history.extend(alerts)

    def _save_trade_log(self):
        """Persist trade history to JSON"""
        try:
            data = {
                'trades': self.trades,
                'summary': {
                    'total_trades': len(self.trades),
                    'closed_trades': len([t for t in self.trades if t['status'] == 'closed']),
                    'daily_pnl': self.daily_pnl,
                    'current_equity': self.risk_profile.account_equity,
                    'current_drawdown': self.current_drawdown,
                    'last_updated': datetime.now().isoformat()
                }
            }
            with open(self.log_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save trade log: {e}")

    def get_daily_stats(self) -> Dict:
        """Get today's trading statistics"""
        today = datetime.now().date()
        today_trades = [t for t in self.trades
                       if datetime.fromisoformat(t['timestamp']).date() == today
                       and t['status'] == 'closed']

        if not today_trades:
            return {
                'trades_today': 0,
                'wins': 0,
                'losses': 0,
                'win_rate': 0,
                'daily_pnl': 0,
                'largest_win': 0,
                'largest_loss': 0
            }

        pnls = [t.get('pnl', 0) for t in today_trades]
        wins = sum(1 for pnl in pnls if pnl > 0)
        losses = sum(1 for pnl in pnls if pnl < 0)

        return {
            'trades_today': len(today_trades),
            'wins': wins,
            'losses': losses,
            'win_rate': wins / len(today_trades) * 100 if today_trades else 0,
            'daily_pnl': sum(pnls),
            'largest_win': max(pnls) if pnls else 0,
            'largest_loss': min(pnls) if pnls else 0
        }

    def is_trading_allowed(self) -> tuple[bool, str]:
        """Check if trading is allowed based on risk parameters"""
        # Check daily loss limit
        if self.daily_pnl <= -self.risk_profile.daily_loss_limit:
            return False, f"Daily loss limit exceeded (${self.daily_pnl:.2f})"

        # Check drawdown limit
        if self.current_drawdown >= self.risk_profile.max_drawdown_percent:
            return False, f"Drawdown limit exceeded ({self.current_drawdown:.2f}%)"

        # Check max positions
        open_positions = len([t for t in self.trades if t['status'] == 'open'])
        if open_positions >= self.risk_profile.max_positions_open:
            return False, f"Max positions reached ({open_positions}/{self.risk_profile.max_positions_open})"

        return True, "Trading allowed"
