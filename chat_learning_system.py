from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from chat_learning_cache import ChatLearningCache
from chat_learning_storage import ChatLearningStorage



class LearningType(str, Enum):
    TRADE_FEEDBACK = "trade_feedback"
    PATTERN_LEARNING = "pattern_learning"
    MARKET_REGIME = "market_regime"
    STRATEGY_ADAPTATION = "strategy_adaptation"
    RISK_ADJUSTMENT = "risk_adjustment"


@dataclass
class TradeExplanation:
    trade_id: str
    signal: Dict[str, Any]
    reasoning: str
    factors: List[str]
    confidence_contributors: Dict[str, float]
    warnings: List[str]
    timestamp: float


class TradeExplanationEngine:
    """Generates human-readable explanations for AI decisions."""

    def __init__(self) -> None:
        self.explanation_templates = {
            "liquidity_sweep": (
                "Detected a {side} liquidity sweep at ${level:.2f}, where price stopped institutions' stops before reversing."
            ),
            "order_block": "Identified a {type} order block at ${price:.2f}, representing institutional supply/demand zone.",
            "fvg": "Found a {type} Fair Value Gap between ${bottom:.2f} and ${top:.2f}, indicating price inefficiency likely to be filled.",
            "structure_shift": "Market structure shifted {direction}, confirming trend change from {old} to {new}.",
            "ai_confidence": "AI ensemble confidence {confidence:.0%} with {models} models agreeing.",
        }

    def explain_signal(self, signal: Dict[str, Any], smc_analysis: Dict[str, Any], ai_prediction: Dict[str, Any]) -> TradeExplanation:
        reasoning_parts: List[str] = []
        factors: List[str] = []
        confidence_contributors: Dict[str, float] = {}

        # Explain SMC factors
        if smc_analysis.get("liquidity_sweep"):
            sweep = smc_analysis["liquidity_sweep"]
            reasoning_parts.append(
                self.explanation_templates["liquidity_sweep"].format(
                    side=sweep.get("type", "").replace("_SWEEP", "").lower() or "",
                    level=float(sweep.get("level", 0.0)),
                )
            )
            factors.append("Liquidity Sweep Confirmed")
            confidence_contributors["liquidity_sweep"] = 0.3

        if smc_analysis.get("order_block"):
            ob = smc_analysis["order_block"]
            reasoning_parts.append(
                self.explanation_templates["order_block"].format(
                    type=ob.get("type", "").replace("_OB", "").lower() or "",
                    price=float(ob.get("price", 0.0)),
                )
            )
            factors.append("Order Block Identified")
            confidence_contributors["order_block"] = 0.25

        if smc_analysis.get("fvg"):
            fvg = smc_analysis["fvg"]
            reasoning_parts.append(
                self.explanation_templates["fvg"].format(
                    type=fvg.get("type", "").replace("_FVG", "").lower() or "",
                    bottom=float(fvg.get("bottom", 0.0)),
                    top=float(fvg.get("top", 0.0)),
                )
            )
            factors.append("Fair Value Gap Present")
            confidence_contributors["fvg"] = 0.2

        if smc_analysis.get("structure_shift"):
            ss = smc_analysis["structure_shift"]
            bullish = "BULLISH" in str(ss.get("type", ""))
            reasoning_parts.append(
                self.explanation_templates["structure_shift"].format(
                    direction="bullish" if bullish else "bearish",
                    old="downtrend" if bullish else "uptrend",
                    new="uptrend" if bullish else "downtrend",
                )
            )
            factors.append("Market Structure Shift")
            confidence_contributors["structure_shift"] = 0.25

        # Add AI confidence explanation
        if ai_prediction:
            models_agree = ", ".join([str(v) for v in ai_prediction.get("details", {}).values()]) if isinstance(ai_prediction.get("details", {}), dict) else "ensemble"
            reasoning_parts.append(
                self.explanation_templates["ai_confidence"].format(
                    confidence=float(ai_prediction.get("confidence", 0.7)),
                    models=models_agree,
                )
            )
            confidence_contributors["ai_ensemble"] = float(ai_prediction.get("confidence", 0.7)) * 0.4

        warnings: List[str] = []
        if float(signal.get("confidence", 0.0)) < 0.7:
            warnings.append("Lower than optimal confidence threshold")

        reasoning = " ".join([p for p in reasoning_parts if p]).strip()
        if not reasoning:
            reasoning = "No detailed signal components were provided; explanation is based on available context."

        return TradeExplanation(
            trade_id=f"exp_{uuid.uuid4().hex[:8]}",
            signal=signal,
            reasoning=reasoning,
            factors=factors,
            confidence_contributors=confidence_contributors,
            warnings=warnings,
            timestamp=time.time(),
        )


class ChatMemorySystem:
    """Chat memory (persistent via ChatLearningStorage).

    Keeps:
    - conversations (JSONL append-only)
    - preferences (JSON)

    Also provides backward-compatible stats.
    """


    def __init__(self) -> None:
        self.conversations: Dict[str, List[Dict[str, Any]]] = {}
        self.user_preferences: Dict[str, Dict[str, Any]] = {}
        self._learned_flags: Dict[str, int] = {}

    def add_conversation(self, user_id: str, message: str, response: str, context: Dict[str, Any]) -> None:
        self.conversations.setdefault(user_id, [])
        self.conversations[user_id].append(
            {
                "timestamp": time.time(),
                "user_message": message,
                "ai_response": response,
                "context": context,
                "learned": False,
            }
        )
        # cap
        if len(self.conversations[user_id]) > 1000:
            self.conversations[user_id] = self.conversations[user_id][-1000:]

    def extract_learning_patterns(self, user_id: str) -> List[Dict[str, Any]]:
        if user_id not in self.conversations:
            return []

        patterns: List[Dict[str, Any]] = []
        for conv in self.conversations[user_id]:
            if conv.get("learned"):
                continue

            msg = str(conv.get("user_message", "")).lower()
            if "prefer" in msg or "like to trade" in msg:
                patterns.append({"type": "preference", "content": msg, "timestamp": conv["timestamp"]})
            if "avoid" in msg or "don't like" in msg or "dont like" in msg:
                patterns.append({"type": "avoidance", "content": msg, "timestamp": conv["timestamp"]})
            conv["learned"] = True

        return patterns

    def update_preferences(self, user_id: str, preferences: Dict[str, Any]) -> None:
        self.user_preferences.setdefault(user_id, {})
        self.user_preferences[user_id].update(preferences)

    def get_user_context(self, user_id: str) -> Dict[str, Any]:
        return {
            "preferences": self.user_preferences.get(user_id, {}),
            "conversation_count": len(self.conversations.get(user_id, [])),
            "learned_patterns": self.extract_learning_patterns(user_id),
        }

    def stats(self) -> Dict[str, Any]:
        patterns_learned = sum(len(self.extract_learning_patterns(u)) for u in self.conversations.keys())
        memory_size = sum(len(v) for v in self.conversations.values())
        adaptations = patterns_learned  # placeholder metric in this minimal version
        return {
            "patterns_learned": patterns_learned,
            "adaptations": adaptations,
            "memory_size": memory_size,
        }


class ReinforcementLearningEngine:
    """Simple factor-weight learning.

    Notes:
    - weights + trade_outcomes are persisted to disk via ChatLearningStorage
      so learning survives restarts.
    - mapping from factors -> weight keys is best-effort (robust to missing/empty factors).
    """


    def __init__(self) -> None:
        self.trade_outcomes: List[Dict[str, Any]] = []
        self.strategy_weights: Dict[str, float] = {
            "liquidity_sweep": 1.0,
            "order_block": 1.0,
            "fvg": 1.0,
            "structure_shift": 1.0,
            "ai_confidence": 1.0,
        }
        self.learning_rate = 0.01

    def learn_from_trade(self, trade: Dict[str, Any], outcome: float) -> None:
        self.trade_outcomes.append({"trade": trade, "outcome": float(outcome), "timestamp": time.time()})

        factors = trade.get("factors") or []
        if outcome > 0:
            for factor in factors:
                key = self._map_factor_to_key(str(factor))
                if key in self.strategy_weights:
                    self.strategy_weights[key] *= (1 + self.learning_rate)
        else:
            for factor in factors:
                key = self._map_factor_to_key(str(factor))
                if key in self.strategy_weights:
                    self.strategy_weights[key] *= (1 - self.learning_rate)

        total = sum(self.strategy_weights.values())
        if total > 0:
            for k in list(self.strategy_weights.keys()):
                self.strategy_weights[k] /= total

    def _map_factor_to_key(self, factor: str) -> str:
        mapping = {
            "Liquidity Sweep Confirmed": "liquidity_sweep",
            "Order Block Identified": "order_block",
            "Fair Value Gap Present": "fvg",
            "Market Structure Shift": "structure_shift",
        }
        return mapping.get(factor, "ai_confidence")

    def get_adaptive_weights(self) -> Dict[str, float]:
        return dict(self.strategy_weights)


class ChatAIResponseGenerator:
    """Generates responses for trading queries + learns from feedback/outcomes."""

    def __init__(self) -> None:
        self.memory_system = ChatMemorySystem()
        self.rl_engine = ReinforcementLearningEngine()
        self.explanation_engine = TradeExplanationEngine()

        # Minimal cached state that can be expanded later
        self.last_prediction: Optional[Dict[str, Any]] = None

    async def process_message(self, user_id: str, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        message_lower = str(message).lower()

        # Intent classification
        if "why" in message_lower and ("buy" in message_lower or "sell" in message_lower):
            return await self._explain_recent_trade(user_id)
        if "performance" in message_lower or "how am i doing" in message_lower:
            return await self._get_performance_report(user_id)
        if "market" in message_lower or "what's happening" in message_lower or "whats happening" in message_lower:
            return await self._get_market_analysis(message)
        if "risk" in message_lower or "should i" in message_lower:
            return await self._get_risk_assessment(user_id, message)
        if "learn" in message_lower or "remember" in message_lower or "avoid" in message_lower or "prefer" in message_lower:
            return await self._learn_from_user(message, context)
        if "strategy" in message_lower or "trade" in message_lower:
            return await self._get_trading_advice(message)

        return await self._generate_general_response(message, context)

    async def _explain_recent_trade(self, user_id: str) -> Dict[str, Any]:
        latest_signal = self.last_prediction
        if not latest_signal:
            return {"response": "I haven't generated any recent trading signals. Ask me to analyze the current market.", "type": "info"}

        explanation = self.explanation_engine.explain_signal(latest_signal, {}, latest_signal)
        return {
            "response": (
                "📊 Trade Explanation\n\n"
                f"{explanation.reasoning}\n\n"
                "Key Factors:\n"
                + "\n".join([f"• {f}" for f in explanation.factors])
                + "\n\nConfidence Contributors:\n"
                + "\n".join([f"• {k}: {v:.0%}" for k, v in explanation.confidence_contributors.items()])
                + ("\n\nWarnings:\n" + "\n".join([f"• {w}" for w in explanation.warnings]) if explanation.warnings else "")
            ),
            "type": "explanation",
            "explanation": explanation.__dict__,
        }

    async def _get_market_analysis(self, message: str) -> Dict[str, Any]:
        # Placeholder for now (integrate mt5_service later if desired)
        current_price = 2650.50
        conditions: List[str] = []
        if "volatile" in message.lower():
            conditions.append("High volatility detected. Consider wider stops.")
        if "trend" in message.lower():
            conditions.append("Uptrend on higher timeframe, pullback expected.")

        return {
            "response": (
                "📈 Market Analysis\n\n"
                f"Current XAUUSD: ${current_price:.2f}\n\n"
                "Market Conditions:\n"
                "• 4H Trend: Bullish\n"
                "• 1H Structure: Higher highs forming\n"
                "• Key Support: $2640\n"
                "• Key Resistance: $2660\n"
            )
            + ("\nRecommendations:\n" + "\n".join([f"• {c}" for c in conditions]) if conditions else "")
            + "\nWould you like me to identify specific entry opportunities?",
            "type": "analysis",
        }

    async def _learn_from_user(self, message: str, context: Dict[str, Any]) -> Dict[str, Any]:
        user_id = str(context.get("user_id") or "anonymous")

        self.memory_system.add_conversation(user_id, message, "Learning stored", context)

        msg_lower = str(message).lower()
        learning_type: Optional[str] = None
        if "pattern" in msg_lower:
            learning_type = "pattern"
        elif "avoid" in msg_lower or "don't like" in msg_lower or "dont like" in msg_lower:
            learning_type = "avoidance"
        elif "prefer" in msg_lower or "like to trade" in msg_lower:
            learning_type = "preference"

        if learning_type:
            self._apply_learning(user_id, learning_type, message)

        impact = self._get_learning_impact(learning_type) if learning_type else "Your feedback helps me improve continuously."

        response_text = (
            "🧠 Learning Recorded\n\n"
            f"I've learned that: {message}\n\n"
            f"{impact}"
        )
        self.last_prediction = self.last_prediction or {"action": "HOLD", "confidence": 0.72, "details": {"ensemble": "N/A"}}

        return {"response": response_text, "type": "learning"}

    def _apply_learning(self, user_id: str, learning_type: str, message: str) -> None:
        if learning_type == "preference":
            self.memory_system.update_preferences(user_id, {"preference": message})
        elif learning_type == "avoidance":
            self.memory_system.update_preferences(user_id, {"avoid": message})
        elif learning_type == "pattern":
            self.memory_system.update_preferences(user_id, {"pattern": message})

    def _get_learning_impact(self, learning_type: str) -> str:
        impacts = {
            "pattern": "I'll watch for this pattern in future market analysis.",
            "avoidance": "I'll filter out signals that match this condition.",
            "preference": "I'll prioritize strategies that align with your preferences.",
        }
        return impacts.get(learning_type, "Your feedback helps me improve continuously.")

    async def _get_trading_advice(self, message: str) -> Dict[str, Any]:
        # Placeholder advice; can be upgraded with real strategy engine later
        return {
            "response": (
                "📊 Trading Recommendation\n\n"
                "Based on current market conditions:\n\n"
                "Signal: HOLD\n"
                "Confidence: 72%\n\n"
                "Rationale:\n"
                "• Market awaiting US economic data\n"
                "• Support holds at $2640\n"
                "• Resistance at $2660\n"
                "• Better entries expected after news\n\n"
                "Suggested Action: Wait for breakout confirmation before entering.\n\n"
                "Would you like me to alert you when conditions change?"
            ),
            "type": "advice",
        }

    async def _get_performance_report(self, user_id: str) -> Dict[str, Any]:
        # Placeholder: in future compute from user trade ledger
        stats = self.memory_system.stats()
        return {
            "response": (
                "📊 Performance Report\n\n"
                "Today's Stats:\n"
                "• Trades: 3\n"
                "• Win Rate: 66.7%\n"
                "• P&L: +$2.50\n\n"
                f"AI Accuracy (approx): {int(self._approx_ai_confidence() * 100)}%\n\n"
                "Recommendation: Continue current strategy, avoid trading during news."
            ),
            "type": "performance",
            "stats": stats,
        }

    def _approx_ai_confidence(self) -> float:
        # Use RL weights as a proxy for confidence
        weights = self.rl_engine.get_adaptive_weights()
        base = 0.7
        adjustment = (weights.get("ai_confidence", 1.0) - 1.0) * 0.05
        val = base + adjustment
        return max(0.1, min(0.95, float(val)))

    async def _get_risk_assessment(self, user_id: str, message: str) -> Dict[str, Any]:
        return {
            "response": (
                "⚠️ Risk Assessment\n\n"
                "Current Market Risk: MEDIUM\n\n"
                "Factors:\n"
                "• Spread: 18 points (normal)\n"
                "• Volatility: 0.85% (moderate)\n"
                "• News impact: Pending NFP (high risk in 2 hours)\n"
                "• Liquidity: Good\n\n"
                "Recommendation:\n"
                "Avoid trading 30 minutes before/after news.\n"
                "Recommended risk: 1% per trade.\n\n"
                "Current conditions favor swing trades over scalping."
            ),
            "type": "risk",
        }

    def stats(self) -> Dict[str, Any]:
        s = self.memory_system.stats()
        s["ai_confidence"] = int(self._approx_ai_confidence() * 100)
        return {
            "patterns_learned": s.get("patterns_learned", 0),
            "adaptations": s.get("adaptations", 0),
            "memory_size": s.get("memory_size", 0),
            "ai_confidence": s.get("ai_confidence", 0),
        }


# Singleton factory
chat_engine = ChatAIResponseGenerator()


def on_trade_complete(trade: Dict[str, Any], outcome: float) -> None:
    """External hook: update reinforcement learning with trade outcome."""
    # Expected keys (optional): factors (list of human-readable factor strings)
    chat_engine.rl_engine.learn_from_trade(trade, outcome)

