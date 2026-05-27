# main_ultimate.py - Ultimate ICT Bot (repo-integrated)
# Combines: strategy_engine confluence + risk limits + MT5 execution (if configured).

import os
import time
import logging
from datetime import datetime
from typing import Optional

import pandas as pd

try:
    import MetaTrader5 as mt5  # type: ignore
except Exception:
    mt5 = None

import yfinance as yf
import pytz

from config import TRADING_CONFIG, Config  # repo root config.py

# ai_predictor requires optional heavy deps (xgboost). Allow running the bot even if missing.
try:
    from ai_predictor import AIPredictor  # type: ignore
except ModuleNotFoundError:
    AIPredictor = None
except Exception:
    AIPredictor = None


from smc_detector import SMCDetector
from data_collector import MT5DataCollector

from strategy_engine import StrategyEngine
from risk_manager import AdvancedRiskManager


logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_est_hour() -> float:
    est = pytz.timezone("US/Eastern")
    now_est = datetime.now(est)
    return now_est.hour + now_est.minute / 60.0


def is_killzone(hour: float) -> tuple[bool, Optional[str]]:
    # ICT killzones (EST)
    if 3 <= hour <= 5:
        return True, "London"
    if 9.5 <= hour <= 11.5:
        return True, "NY AM"
    if 14 <= hour <= 16:
        return True, "NY PM"
    return False, None


class UltimateICTBot:
    def __init__(self):
        cfg = Config()
        self.symbol = getattr(cfg, "SYMBOL", TRADING_CONFIG.get("symbol", "XAUUSD"))
        self.timeframe = getattr(cfg, "TIMEFRAME", "5m")
        self.risk_percent = getattr(cfg, "MAX_RISK_PER_TRADE", TRADING_CONFIG.get("risk_percent", 2.0))

        self.loop_sleep_sec = int(os.getenv("BOT_LOOP_SLEEP_SEC", "60"))

        # MT5 config via env vars
        self.use_mt5 = os.getenv("USE_MT5", "0").strip() == "1"
        self.mt5_login = int(os.getenv("MT5_LOGIN", "0") or "0")
        self.mt5_password = os.getenv("MT5_PASSWORD", "")
        self.mt5_server = os.getenv("MT5_SERVER", "")
        self.magic = int(os.getenv("MT5_MAGIC", "123456"))

        self.balance = float(getattr(cfg, "INITIAL_BALANCE", 5.0))
        self.risk_manager = AdvancedRiskManager(initial_balance=self.balance)

        # repo components
        # NOTE: StrategyEngine expects config + ai_predictor + smc_detector + liquidity_scanner
        self.data_collector = DataCollector(config=cfg)
        self.ai_predictor = AIPredictor(self.symbol)
        self.smc_detector = SMCDetector()
        self.strategy_engine = StrategyEngine(
            config=cfg,
            ai_predictor=self.ai_predictor,
            smc_detector=self.smc_detector,
            liquidity_scanner=self.data_collector.liquidity_scanner,
        )

        self.position = None  # in-memory shadow position (for demo)

        logger.info("=" * 60)
        logger.info("🚀 Ultimate ICT Bot (repo-integrated)")
        logger.info(f"Symbol: {self.symbol} | TF: {self.timeframe} | Risk%: {self.risk_percent}")
        logger.info(f"Killzones: London(3-5), NY AM(9.5-11.5), NY PM(14-16) EST")
        logger.info(f"USE_MT5={self.use_mt5}")
        logger.info("=" * 60)

    def init_mt5(self) -> bool:
        if not self.use_mt5:
            return False
        if mt5 is None:
            logger.error("MetaTrader5 package not available. pip install MetaTrader5")
            return False

        if not mt5.initialize():
            logger.error("MT5 initialize() failed")
            return False

        if self.mt5_login:
            ok = mt5.login(login=self.mt5_login, password=self.mt5_password, server=self.mt5_server)
            if not ok:
                logger.error("MT5 login failed")
                mt5.shutdown()
                return False

        logger.info("MT5 connected")
        return True

    def fetch_market_snapshot(self) -> Optional[pd.DataFrame]:
        # Uses yfinance like your existing scripts/backtester.
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="1d", interval="5m")
            if df is None or df.empty:
                return None
            df.columns = [str(c).lower() for c in df.columns]
            df.index = pd.to_datetime(df.index)
            return df
        except Exception as e:
            logger.error(f"Data fetch error: {e}")
            return None

    def estimate_lot(self, stop_loss_distance: float) -> float:
        # Keep consistent with repo AdvancedRiskManager rough sizing.
        # stop_loss_distance is in price units.
        stop_pips = abs(stop_loss_distance) * 10000
        if stop_pips <= 0:
            return 0.01
        risk_amount = self.risk_manager.balance * (self.risk_percent / 100.0)
        lot_size = risk_amount / (stop_pips * 0.10)
        if self.risk_manager.balance < 25:
            lot_size = min(lot_size, 0.02)
        elif self.risk_manager.balance < 100:
            lot_size = min(lot_size, 0.05)
        else:
            lot_size = min(lot_size, 0.10)
        return float(max(0.01, round(lot_size, 2)))

    def can_take_trade(self, signal: dict) -> bool:
        # Validate NEUTRAL
        decision = self.risk_manager.validate_trade(signal, balance=self.risk_manager.balance)
        return bool(decision.get("allowed"))

    def run(self):
        mt5_ok = self.init_mt5()

        while True:
            try:
                hour = get_est_hour()
                in_kz, zone = is_killzone(hour)

                # Always manage existing shadow position
                if self.position is not None:
                    snap = self.fetch_market_snapshot()
                    if snap is not None and len(snap) > 0:
                        current_price = float(snap.iloc[-1]["close"])
                        self._manage_shadow_position(current_price)

                if not in_kz:
                    time.sleep(self.loop_sleep_sec)
                    continue

                snap = self.fetch_market_snapshot()
                if snap is None or len(snap) < 50:
                    time.sleep(self.loop_sleep_sec)
                    continue

                # StrategyEngine works off DataCollector.compute_features; easiest is to feed
                # the same df and let it compute features inside generate_signal.
                signal = self.strategy_engine.generate_signal(snap, self.data_collector)

                # signal format: {signal: BUY/SELL/NEUTRAL, entry, stop_loss, take_profit, ...}
                if not signal:
                    time.sleep(self.loop_sleep_sec)
                    continue

                if not self.can_take_trade(signal):
                    logger.info(f"[{zone}] Risk/Signal guard blocks trade. signal={signal.get('signal')}")
                    time.sleep(self.loop_sleep_sec)
                    continue

                side = signal.get("signal")
                entry = float(signal.get("entry", 0.0) or 0.0)
                sl = float(signal.get("stop_loss", 0.0) or 0.0)
                tp = float(signal.get("take_profit", 0.0) or 0.0)

                if side not in ("BUY", "SELL"):
                    time.sleep(self.loop_sleep_sec)
                    continue

                lot = self.estimate_lot(entry - sl)

                logger.info(f"[{zone}] ✅ Trade setup: {side} entry={entry:.5f} SL={sl:.5f} TP={tp:.5f} lot={lot}")

                # For now, execute a shadow trade so the repo can run without MT5 permissions.
                # If USE_MT5=1, we only log (no robust order-send wiring here) because the repo's
                # MT5 executor lives under xauusd_scalper/, not root.
                if self.position is None:
                    self.position = {
                        "side": side,
                        "entry": entry,
                        "sl": sl,
                        "tp": tp,
                        "lot": lot,
                        "opened_at": time.time(),
                    }

                    # TODO (optional): wire into xauusd_scalper.trade_executor for real orders.
                    if self.use_mt5 and mt5_ok:
                        logger.info("MT5 enabled, but real order placement not wired in this unified bot.")

                time.sleep(self.loop_sleep_sec)

            except KeyboardInterrupt:
                logger.info("Stopping UltimateICTBot.")
                break
            except Exception as e:
                logger.error(f"Loop error: {e}")
                time.sleep(self.loop_sleep_sec)

    def _manage_shadow_position(self, current_price: float):
        pos = self.position
        side = pos["side"]
        entry = float(pos["entry"])
        sl = float(pos["sl"])
        tp = float(pos["tp"])
        lot = float(pos["lot"])

        # Approx pnl model: pips * lot * 0.10
        def pnl_for(close_price: float) -> float:
            if side == "BUY":
                pips = (close_price - entry) * 10000
            else:
                pips = (entry - close_price) * 10000
            return pips * lot * 0.10

        if side == "BUY":
            if current_price <= sl:
                pnl = pnl_for(sl)
                self.risk_manager.record_trade(pnl)
                logger.info(f"❌ Shadow SL hit. pnl=${pnl:.2f}")
                self.position = None
                return
            if current_price >= tp:
                pnl = pnl_for(tp)
                self.risk_manager.record_trade(pnl)
                logger.info(f"✅ Shadow TP hit. pnl=${pnl:.2f}")
                self.position = None
                return
        else:
            if current_price >= sl:
                pnl = pnl_for(sl)
                self.risk_manager.record_trade(pnl)
                logger.info(f"❌ Shadow SL hit. pnl=${pnl:.2f}")
                self.position = None
                return
            if current_price <= tp:
                pnl = pnl_for(tp)
                self.risk_manager.record_trade(pnl)
                logger.info(f"✅ Shadow TP hit. pnl=${pnl:.2f}")
                self.position = None
                return


if __name__ == "__main__":
    UltimateICTBot().run()

