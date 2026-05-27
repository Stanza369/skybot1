import numpy as np
import pandas as pd
import xgboost as xgb
import logging
import joblib

# TensorFlow is optional (LSTM/ensemble disabled if not installed)
try:
    import tensorflow as tf  # type: ignore
except Exception:
    tf = None


from typing import Dict, Tuple, Optional
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AIPredictor:
    def __init__(self, config):
        self.config = config
        self.xgb_model = None
        self.lstm_model = None
        self.scaler = StandardScaler()
        self.feature_columns = []

        # set by main after wiring
        self.data_collector = None

    def prepare_features(self, df: pd.DataFrame) -> Tuple[np.ndarray, np.ndarray]:
        self.feature_columns = [
            "returns",
            "volume_ratio",
            "momentum",
            "velocity",
            "acceleration",
            "rsi",
            "macd_diff",
            "atr",
            "atr_surge",
            "distance_to_vwap",
            "volatility",
            "volatility_spike",
            "ema_9",
            "ema_21",
            "ema_50",
            "high_low_ratio",
            "close_open_ratio",
            "doji",
            "overlap",
            "volume_trend",
        ]

        available_features = [f for f in self.feature_columns if f in df.columns]
        X = df[available_features].values

        future_returns = df["close"].shift(-self.config.PREDICTION_HORIZON) / df["close"] - 1
        y = (future_returns > 0).astype(int)

        valid_idx = ~(np.isnan(X).any(axis=1) | pd.isna(y))
        X = X[valid_idx]
        y = y[valid_idx]

        return X, y

    def train_xgboost(self, df: pd.DataFrame) -> Dict:
        logger.info("Training XGBoost model...")
        X, y = self.prepare_features(df)

        X_scaled = self.scaler.fit_transform(X)

        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=0.2, shuffle=False
        )

        self.xgb_model = xgb.XGBClassifier(
            n_estimators=300,
            max_depth=6,
            learning_rate=0.01,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            eval_metric="logloss",
        )

        self.xgb_model.fit(
            X_train,
            y_train,
            eval_set=[(X_test, y_test)],
            early_stopping_rounds=50,
            verbose=False,
        )

        accuracy = self.xgb_model.score(X_test, y_test)

        joblib.dump(self.xgb_model, f"{self.config.MODEL_PATH}xgboost_model.pkl")
        joblib.dump(self.scaler, f"{self.config.MODEL_PATH}scaler.pkl")

        logger.info(f"XGBoost trained. Accuracy: {accuracy:.2%}")
        return {"model": "xgboost", "accuracy": accuracy, "features": self.feature_columns}

    def predict(self, df: pd.DataFrame) -> Dict:
        if self.xgb_model is None:
            return {"error": "Model not trained"}

        latest_df = df.tail(200).copy()
        latest_df = self.data_collector.compute_features(latest_df)

        latest_row = latest_df.tail(1)
        X = latest_row[self.feature_columns].values
        X_scaled = self.scaler.transform(X)

        prob_xgb = float(self.xgb_model.predict_proba(X_scaled)[0][1])

        direction = "BULLISH" if prob_xgb > 0.5 else "BEARISH"
        confidence = abs(prob_xgb - 0.5) * 2

        signal = "NEUTRAL"
        if prob_xgb > self.config.CONFIDENCE_THRESHOLD:
            signal = "BUY"
        elif prob_xgb < (1 - self.config.CONFIDENCE_THRESHOLD):
            signal = "SELL"

        return {
            "direction": direction,
            "probability": prob_xgb,
            "confidence": confidence,
            "xgb_probability": prob_xgb,
            "lstm_probability": None,
            "signal": signal,
        }

    def load_models(self) -> bool:
        try:
            self.xgb_model = joblib.load(f"{self.config.MODEL_PATH}xgboost_model.pkl")
            self.scaler = joblib.load(f"{self.config.MODEL_PATH}scaler.pkl")
            logger.info("Models loaded successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to load models: {e}")
            return False

