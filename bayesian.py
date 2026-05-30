from collections import defaultdict
from typing import List, Dict


class BayesianForexPredictor:
    """Lightweight Bayesian predictor using simple candle features.

    API:
      - train(candles: List[Dict]) -> None  # candles = list of {'open','high','low','close'}
      - predict(recent_candles: List[Dict]) -> (str, Dict[str,float])
    """

    def __init__(self):
        self.prior = {"UP": 1.0 / 3, "DOWN": 1.0 / 3, "SIDEWAYS": 1.0 / 3}
        self.likelihoods = {"UP": defaultdict(float), "DOWN": defaultdict(float), "SIDEWAYS": defaultdict(float)}

    def _extract_features(self, candles: List[Dict]) -> List[str]:
        features = []
        if len(candles) < 2:
            return features

        last = candles[-1]
        prev = candles[-2]

        # engulfing-like
        if last["close"] > prev["open"] and prev["close"] < prev["open"]:
            features.append("bullish_engulfing")
        if last["close"] < prev["open"] and prev["close"] > prev["open"]:
            features.append("bearish_engulfing")

        body = abs(last["close"] - last["open"])
        upper_wick = last["high"] - max(last["close"], last["open"])
        lower_wick = min(last["close"], last["open"]) - last["low"]

        if upper_wick > body * 2:
            features.append("pin_top")
        if lower_wick > body * 2:
            features.append("pin_bottom")

        # momentum
        lookback = min(5, len(candles))
        momentum = last["close"] - candles[-lookback]["close"]
        features.append("pos_momentum" if momentum > 0 else "neg_momentum")

        return features

    def train(self, historical: List[Dict]):
        # Expect historical as list of candles ordered oldest->newest
        if len(historical) < 2:
            return

        for i in range(len(historical) - 1):
            window = historical[max(0, i - 5): i + 1]
            features = self._extract_features(window)
            outcome = "UP" if historical[i + 1]["close"] > historical[i]["close"] else "DOWN"
            # simple handling: SIDEWAYS rarely observed; ignore for training
            for f in features:
                self.likelihoods[outcome][f] += 1

        # Normalize likelihoods per outcome
        for outcome in self.likelihoods:
            total = sum(self.likelihoods[outcome].values())
            if total == 0:
                continue
            for f in list(self.likelihoods[outcome].keys()):
                self.likelihoods[outcome][f] /= total

    def predict(self, recent_candles: List[Dict]):
        features = self._extract_features(recent_candles)
        probs = {"UP": self.prior["UP"], "DOWN": self.prior["DOWN"], "SIDEWAYS": self.prior["SIDEWAYS"]}

        for outcome in probs:
            for f in features:
                # small-smoothing for unseen features
                probs[outcome] *= self.likelihoods[outcome].get(f, 0.01)

        total = sum(probs.values())
        if total <= 0:
            # fallback
            return "SIDEWAYS", {k: 1.0 / 3 for k in probs}

        for k in probs:
            probs[k] /= total

        best = max(probs.items(), key=lambda x: x[1])[0]
        return best, probs
