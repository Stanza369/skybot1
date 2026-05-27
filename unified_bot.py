import argparse
import logging
import os
from datetime import datetime


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def run_live(years: int) -> None:
    # Live trading is intended to run until stopped.
    # `years` is accepted to satisfy the unified CLI, but is implemented as a maximum runtime.
    import time

    from xauusd_scalper.main import main as live_main

    max_seconds = int(years * 365 * 24 * 60 * 60)
    start = time.time()
    logging.info("Starting LIVE mode for up to %s years (max_seconds=%s)", years, max_seconds)

    # Run in-process; stop after max_seconds by raising KeyboardInterrupt.
    try:
        while True:
            if (time.time() - start) > max_seconds:
                raise KeyboardInterrupt("Max runtime reached")
            live_main()
    except KeyboardInterrupt:
        logging.info("LIVE stopped")


def run_backtest(years: int) -> None:
    # Backtest runner is already implemented in scripts_backtest.py.
    # We rerun the MT5 + feature pipeline, but override the historical window.
    from data_collector import MT5DataCollector
    from backtester import Backtester
    from risk_manager import RiskManager
    from strategy_engine import StrategyEngine

    config = __import__("config").Config
    cfg = config()

    days_back = int(years * 365)
    data_collector = MT5DataCollector(cfg)
    if not data_collector.connect():
        raise SystemExit("Failed to connect to MT5")

    try:
        # Strategy stack used by scripts_backtest.py
        from ai_predictor import AIPredictor
        from smc_detector import SMCDetector
        from liquidity_scanner import LiquidityScanner

        ai_predictor = AIPredictor(cfg)
        ai_predictor.data_collector = data_collector
        smc_detector = SMCDetector()
        liquidity_scanner = LiquidityScanner(cfg)
        strategy_engine = StrategyEngine(cfg, ai_predictor, smc_detector, liquidity_scanner)
        risk_manager = RiskManager(cfg)

        df = data_collector.get_historical_data(days_back=days_back)
        if df.empty:
            raise SystemExit("No historical data retrieved")
        df = data_collector.compute_features(df)

        backtester = Backtester(cfg, strategy_engine, risk_manager)
        results = backtester.run(df=df, initial_balance=10000)
        logging.info("Backtest results: %s", results)
        print(results)
    finally:
        data_collector.disconnect()


def main() -> None:
    _configure_logging()
    parser = argparse.ArgumentParser(description="Unified trading bot CLI")
    parser.add_argument("--mode", choices=["live", "backtest"], required=True)
    parser.add_argument("--years", type=int, required=True)
    args = parser.parse_args()

    logging.info("unified_bot start: mode=%s years=%s time=%s", args.mode, args.years, datetime.now().isoformat())

    if args.mode == "live":
        run_live(args.years)
    else:
        run_backtest(args.years)


if __name__ == "__main__":
    main()

