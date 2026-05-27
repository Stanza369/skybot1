import logging
from typing import Dict, Optional

from fvg_detector import FVGDetector
from order_block_detector import OrderBlockDetector
from liquidity_grab_scanner import LiquidityGrabScanner

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


from scalping_engine import GoldScalpingOrchestrator


class StrategyEngine:
    def __init__(self, config, ai_predictor, smc_detector, liquidity_scanner):
        self.config = config
        self.ai_predictor = ai_predictor
        self.smc_detector = smc_detector
        self.liquidity_scanner = liquidity_scanner
        self.scalping_orchestrator = GoldScalpingOrchestrator()



    def generate_signal(self, df, data_collector) -> Dict:
        df = data_collector.compute_features(df)

        # AI
        ai_pred = self.ai_predictor.predict(df)

        latest = df.iloc[-1]
        current_price = float(latest.get("close", 0.0))
        momentum_burst = float(latest.get("atr_surge", 0.0)) > self.config.MIN_ATR_SURGE
        volume_spike = float(latest.get("volume_ratio", 0.0)) > 1.5

        # ICT modules based on OHLC
        fvg_detector = FVGDetector(df)
        ob_detector = OrderBlockDetector(df)
        lg_detector = LiquidityGrabScanner(df)

        nearest_fvg = fvg_detector.get_nearest_fvg(current_price)
        order_block = ob_detector.get_mitigated_order_block(current_price)
        liquidity_grab = lg_detector.detect_liquidity_grab(current_price=current_price)

        # Existing liquidity sweep (repo feature)
        liquidity = self.liquidity_scanner.detect_liquidity_sweep(df.tail(100))
        insta_flow = self.liquidity_scanner.calculate_insta_flow(df)


        # MTF trends
        m5_df = data_collector.get_rates(self.config.TIMEFRAMES["M5"], 50)
        m15_df = data_collector.get_rates(self.config.TIMEFRAMES["M15"], 50)

        if not m5_df.empty and not m15_df.empty:
            m5_trend = "BULLISH" if m5_df["close"].iloc[-1] > m5_df["close"].rolling(20).mean().iloc[-1] else "BEARISH"
            m15_trend = "BULLISH" if m15_df["close"].iloc[-1] > m15_df["close"].rolling(20).mean().iloc[-1] else "BEARISH"
        else:
            m5_trend = m15_trend = "BULLISH"

        bullish_conditions = [
            ai_pred["direction"] == "BULLISH",
            ai_pred["confidence"] > 0.6,
            momentum_burst or volume_spike,
            m5_trend == "BULLISH",
            m15_trend == "BULLISH",
            liquidity["sweep_detected"] is False,
            insta_flow > 0.5,
        ]
        bearish_conditions = [
            ai_pred["direction"] == "BEARISH",
            ai_pred["confidence"] > 0.6,
            momentum_burst or volume_spike,
            m5_trend == "BEARISH",
            m15_trend == "BEARISH",
            liquidity["sweep_detected"] is False,
            insta_flow < -0.5,
        ]

        bullish_score = sum(bullish_conditions) / len(bullish_conditions)
        bearish_score = sum(bearish_conditions) / len(bearish_conditions)

        # --- Scalping layer (aggressive XAUUSD scalps) ---
        # Uses the same df that already contains OHLC(+ computed features like atr/volume_ratio).
        scalping_signal = None
        try:
            scalping_signal = self.scalping_orchestrator.analyze(df.tail(120))
        except Exception:
            scalping_signal = None

        if scalping_signal and scalping_signal.get("signal") in ("BUY", "SELL"):
            sc_side = scalping_signal["signal"]
            sc_conf = float(scalping_signal.get("confidence", 0.0) or 0.0)
            if sc_side == "BUY":
                bullish_score += 0.20 * min(1.0, sc_conf / 0.85)
            else:
                bearish_score += 0.20 * min(1.0, sc_conf / 0.85)


        # ICT confluence gating (FVG + Order Block + Liquidity Grab)
        fvg_present = nearest_fvg is not None
        ob_present = order_block is not None
        liquidity_grab_present = liquidity_grab is not None

        if liquidity_grab_present:
            if liquidity_grab["type"] == "BUY_SIDE_GRAB":
                bullish_score += 0.15
            elif liquidity_grab["type"] == "SELL_SIDE_GRAB":
                bearish_score += 0.15

        if ob_present:
            if order_block["type"] == "BULLISH":
                bullish_score += 0.10
            elif order_block["type"] == "BEARISH":
                bearish_score += 0.10

        if fvg_present:
            if nearest_fvg["type"] == "BULLISH":
                # If price is near/below bullish FVG boundary, favor BUY
                if current_price <= float(nearest_fvg["bottom"]) * 1.001:
                    bullish_score += 0.10
            elif nearest_fvg["type"] == "BEARISH":
                if current_price >= float(nearest_fvg["top"]) * 0.999:
                    bearish_score += 0.10

        # Final decision
        signal = "NEUTRAL"
        if bullish_score > 0.72:
            signal = "BUY"
        elif bearish_score > 0.72:
            signal = "SELL"


        atr = float(latest.get("atr", 0.0))
        entry = stop_loss = take_profit = 0.0

        # If scalping layer produced a strong side, prefer its SL/TP.
        if "scalping_signal" in locals() and scalping_signal and scalping_signal.get("signal") == signal:
            sc_conf = float(scalping_signal.get("confidence", 0.0) or 0.0)
            if sc_conf >= 0.65:
                entry = float(scalping_signal.get("entry", 0.0) or 0.0)
                stop_loss = float(scalping_signal.get("stop_loss", 0.0) or 0.0)
                take_profit = float(scalping_signal.get("take_profit", 0.0) or 0.0)
                atr = float(scalping_signal.get("atr", atr) or atr)

        if entry == 0.0 and signal == "BUY":
            entry = float(latest.get("close", 0.0))
            stop_loss = entry - (atr * 1.5)
            take_profit = entry + (atr * 2.5)
        elif entry == 0.0 and signal == "SELL":
            entry = float(latest.get("close", 0.0))
            stop_loss = entry + (atr * 1.5)
            take_profit = entry - (atr * 2.5)


        return {
            "signal": signal,
            "bullish_score": bullish_score,
            "bearish_score": bearish_score,
            "entry": entry,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "atr": atr,
            "ai_prediction": ai_pred,
            "momentum_burst": momentum_burst,
            "volume_spike": volume_spike,
            "liquidity_sweep": liquidity["sweep_detected"],
            "institutional_flow": insta_flow,
            # ICT additions (optional fields for telegram/diagnostics)
            "fvg_present": fvg_present,
            "fvg_type": nearest_fvg.get("type") if fvg_present else None,
            "order_block_present": ob_present,
            "order_block_type": order_block.get("type") if ob_present else None,
            "liquidity_grab_present": liquidity_grab_present,
            "liquidity_grab_type": liquidity_grab.get("type") if liquidity_grab_present else None,
            # Scalars (optional diagnostics)
            "scalping_layer": {
                "used": True if "scalping_signal" in locals() and scalping_signal else False,
                "signal": scalping_signal.get("signal") if "scalping_signal" in locals() and scalping_signal else None,
                "confidence": float(scalping_signal.get("confidence")) if "scalping_signal" in locals() and scalping_signal else None,
                "scalp_type": scalping_signal.get("scalp_type") if "scalping_signal" in locals() and scalping_signal else None,
                "reason": scalping_signal.get("scalp_reason") if "scalping_signal" in locals() and scalping_signal else None,
            },
        }



    def analyze_multi_timeframe(self, data_collector) -> Dict:
        out = {}
        for tf_name, tf_value in self.config.TIMEFRAMES.items():
            df = data_collector.get_rates(tf_value, 200)
            if df.empty:
                continue
            # lightweight featureless trend
            ema_9 = df["close"].ewm(span=9, adjust=False).mean().iloc[-1]
            ema_21 = df["close"].ewm(span=21, adjust=False).mean().iloc[-1]
            price = float(df["close"].iloc[-1])
            out[tf_name] = {
                "trend": "BULLISH" if price > ema_9 > ema_21 else "BEARISH",
                "price": price,
                "ema_9": float(ema_9),
                "ema_21": float(ema_21),
            }
        return out

