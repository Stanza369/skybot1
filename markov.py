from collections import defaultdict
from typing import Tuple, List


class MarkovForexPredictor:
    """Simple discrete-state Markov chain predictor for price-change states.

    API:
      - train(price_changes: List[float]) -> None
      - predict_next_state(current_change: float) -> Tuple[str, float]
    """

    def __init__(self, strong_threshold: float = 0.0005):
        self.transition_matrix = defaultdict(lambda: defaultdict(int))
        self.prob_matrix = {}
        self.strong_threshold = strong_threshold

    def _get_state(self, price_change: float) -> str:
        if price_change > self.strong_threshold:
            return "STRONG_UP"
        if price_change > 0:
            return "WEAK_UP"
        if price_change < -self.strong_threshold:
            return "STRONG_DOWN"
        if price_change < 0:
            return "WEAK_DOWN"
        return "SIDEWAYS"

    def train(self, price_changes: List[float]):
        if not price_changes or len(price_changes) < 2:
            return

        for i in range(len(price_changes) - 1):
            cur = self._get_state(price_changes[i])
            nxt = self._get_state(price_changes[i + 1])
            self.transition_matrix[cur][nxt] += 1

        # convert to probabilities
        self.prob_matrix = {}
        for s, targets in self.transition_matrix.items():
            total = sum(targets.values())
            if total == 0:
                continue
            self.prob_matrix[s] = {t: c / total for t, c in targets.items()}

    def predict_next_state(self, current_change: float) -> Tuple[str, float]:
        s = self._get_state(current_change)
        probs = self.prob_matrix.get(s, {})
        if not probs:
            return None, 0.0
        next_state, prob = max(probs.items(), key=lambda x: x[1])
        return next_state, prob
