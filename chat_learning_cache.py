from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class UserSignalCache:
    """Per-user cache of the last model inputs used for trade.

    This enables: "Why did you buy/sell?" explanations tied to the last signal.
    """

    last_signal: Optional[Dict[str, Any]] = None
    last_smc_analysis: Optional[Dict[str, Any]] = None
    last_ai_prediction: Optional[Dict[str, Any]] = None
    last_timestamp: float = 0.0


class ChatLearningCache:
    def __init__(self) -> None:
        self._by_user: Dict[str, UserSignalCache] = {}

    def get(self, user_id: str) -> UserSignalCache:
        if user_id not in self._by_user:
            self._by_user[user_id] = UserSignalCache()
        return self._by_user[user_id]

    def set_last(self, user_id: str, *, signal: Dict[str, Any], smc_analysis: Dict[str, Any], ai_prediction: Dict[str, Any], timestamp: float) -> None:
        uc = self.get(user_id)
        uc.last_signal = signal
        uc.last_smc_analysis = smc_analysis
        uc.last_ai_prediction = ai_prediction
        uc.last_timestamp = timestamp

