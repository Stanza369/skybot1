"""
ai_inference.py - Real-Time AI Inference Engine
Loads trained models and generates trading signals
"""
import json
import pickle
import numpy as np
import pandas as pd
import torch
import torch.nn as nn
from pathlib import Path
import logging
from collections import deque
from typing import Dict, Optional, Tuple
import warnings

warnings.filterwarnings('ignore')
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEVICE = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# ============================================================================
# MODEL ARCHITECTURES (SAME AS TRAINING)
# ============================================================================

class LSTMPredictor(nn.Module):
    """LSTM for short-term price direction prediction"""

    def __init__(self, input_size: int, hidden_size: int = 128,
                 num_layers: int = 3, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout
        )
        self.fc1 = nn.Linear(hidden_size, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 2)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        lstm_out, (h_n, c_n) = self.lstm(x)
        last_hidden = h_n[-1]
        x = self.relu(self.fc1(last_hidden))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.fc3(x)
        return x

class TransformerPredictor(nn.Module):
    """Transformer for pattern recognition"""

    def __init__(self, input_size: int, d_model: int = 64,
                 nhead: int = 8, num_layers: int = 3, dropout: float = 0.2):
        super().__init__()
        self.input_projection = nn.Linear(input_size, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=256,
            dropout=dropout,
            batch_first=True,
            activation='relu'
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.fc1 = nn.Linear(d_model, 64)
        self.fc2 = nn.Linear(64, 32)
        self.fc3 = nn.Linear(32, 2)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)

    def forward(self, x):
        x = self.input_projection(x)
        x = self.transformer(x)
        x = x.mean(dim=1)
        x = self.relu(self.fc1(x))
        x = self.dropout(x)
        x = self.relu(self.fc2(x))
        x = self.dropout(x)
        x = self.fc3(x)
        return x

# ============================================================================
# FEATURE ENGINEERING (INFERENCE-TIME)
# ============================================================================

class FeatureEngine:
    """Real-time feature engineering for inference"""

    def __init__(self, feature_names: list):
        self.feature_names = feature_names

    def engineer_features(self, price_data: dict) -> np.ndarray:
        """Engineer features from current market data

        Expected price_data:
        {
            'close': [prices...],
            'high': [prices...],
            'low': [prices...],
            'open': [prices...],
            'volume': [volumes...]
        }
        """
        close = np.array(price_data.get('close', []))
        high = np.array(price_data.get('high', []))
        low = np.array(price_data.get('low', []))
        open_ = np.array(price_data.get('open', []))

        if len(close) < 50:
            return None  # Not enough data

        features = {}

        # Basic features
        features['open'] = open_[-1]
        features['high'] = high[-1]
        features['low'] = low[-1]
        features['close'] = close[-1]

        # Price-based
        features['returns'] = (close[-1] - close[-2]) / close[-2]
        features['log_returns'] = np.log(close[-1] / close[-2])
        features['high_low'] = (high[-1] - low[-1]) / close[-1]
        features['close_open'] = (close[-1] - open_[-1]) / open_[-1]

        # Momentum
        features['momentum_5'] = close[-1] - close[-5]
        features['momentum_10'] = close[-1] - close[-10]
        features['roc_5'] = (close[-1] - close[-5]) / close[-5]

        # Volatility
        features['volatility_5'] = np.std(close[-5:])
        features['volatility_10'] = np.std(close[-10:])

        # EMAs
        features['ema_9'] = self._ema(close, 9)
        features['ema_21'] = self._ema(close, 21)
        features['ema_50'] = self._ema(close, 50)

        # RSI
        features['rsi_14'] = self._rsi(close, 14)

        # MACD
        ema_12 = self._ema(close, 12)
        ema_26 = self._ema(close, 26)
        features['macd'] = ema_12 - ema_26
        macd_signal = self._ema(np.array([ema_12 - ema_26 for _ in range(len(close))]), 9)
        features['macd_signal'] = macd_signal

        # Bollinger Bands
        bb_mid = np.mean(close[-20:])
        bb_std = np.std(close[-20:])
        bb_upper = bb_mid + (bb_std * 2)
        bb_lower = bb_mid - (bb_std * 2)
        features['bb_upper'] = bb_upper
        features['bb_lower'] = bb_lower
        features['bb_position'] = (close[-1] - bb_lower) / (bb_upper - bb_lower)

        # Convert to array matching feature names order
        feature_array = []
        for fname in self.feature_names:
            feature_array.append(features.get(fname, 0.0))

        return np.array(feature_array)

    def _ema(self, data: np.ndarray, period: int) -> float:
        """Calculate EMA"""
        if len(data) < period:
            return data[-1]
        multiplier = 2 / (period + 1)
        ema = data[0]
        for price in data[1:]:
            ema = price * multiplier + ema * (1 - multiplier)
        return ema

    def _rsi(self, data: np.ndarray, period: int) -> float:
        """Calculate RSI"""
        if len(data) < period + 1:
            return 50.0
        deltas = np.diff(data)
        seed = deltas[:period + 1]
        up = seed[seed >= 0].sum() / period
        down = -seed[seed < 0].sum() / period
        rs = up / down if down != 0 else 1.0
        rsi = 100 - 100 / (1 + rs)
        return rsi

# ============================================================================
# INFERENCE ENGINE
# ============================================================================

class AIInferenceEngine:
    """Real-time trading signal generation from trained models"""

    def __init__(self, lstm_model_path: str = 'models/lstm_model.pt',
                 transformer_model_path: str = 'models/transformer_model.pt',
                 scaler_path: str = 'models/feature_scaler.pkl',
                 feature_names_path: str = 'models/feature_names.json',
                 sequence_length: int = 60):

        self.sequence_length = sequence_length
        self.feature_engine = None
        self.scaler = None
        self.lstm_model = None
        self.transformer_model = None
        self.price_buffer = deque(maxlen=sequence_length)

        self._load_models(lstm_model_path, transformer_model_path,
                         scaler_path, feature_names_path)

    def _load_models(self, lstm_path: str, transformer_path: str,
                     scaler_path: str, feature_names_path: str):
        """Load pre-trained models and feature scaler"""

        try:
            # Load feature scaler
            if Path(scaler_path).exists():
                with open(scaler_path, 'rb') as f:
                    self.scaler = pickle.load(f)
                logger.info(f"Loaded scaler from {scaler_path}")
            else:
                logger.warning(f"Scaler not found at {scaler_path}, using identity scaling")
                self.scaler = None

            # Load feature names
            feature_names = []
            if Path(feature_names_path).exists():
                with open(feature_names_path) as f:
                    feature_names = json.load(f)
                logger.info(f"Loaded {len(feature_names)} feature names")
            else:
                logger.warning("Feature names not found")

            self.feature_engine = FeatureEngine(feature_names)

            # Load LSTM model
            if Path(lstm_path).exists():
                self.lstm_model = LSTMPredictor(input_size=len(feature_names))
                self.lstm_model.load_state_dict(torch.load(lstm_path, map_location=DEVICE))
                self.lstm_model.to(DEVICE)
                self.lstm_model.eval()
                logger.info(f"Loaded LSTM model from {lstm_path}")
            else:
                logger.warning(f"LSTM model not found at {lstm_path}")

            # Load Transformer model
            if Path(transformer_path).exists():
                self.transformer_model = TransformerPredictor(input_size=len(feature_names))
                self.transformer_model.load_state_dict(torch.load(transformer_path, map_location=DEVICE))
                self.transformer_model.to(DEVICE)
                self.transformer_model.eval()
                logger.info(f"Loaded Transformer model from {transformer_path}")
            else:
                logger.warning(f"Transformer model not found at {transformer_path}")

        except Exception as e:
            logger.error(f"Error loading models: {e}")
            logger.warning("Running in fallback mode (mock signals)")

    def predict(self, market_data: dict) -> Dict:
        """Generate trading signal from market data

        Args:
            market_data: {
                'price': float,
                'close': [float],
                'high': [float],
                'low': [float],
                'open': [float],
                'volatility': float (optional)
            }

        Returns:
            {
                'direction': 'BUY' | 'SELL' | 'HOLD',
                'confidence': 0-100,
                'lstm_signal': 'BUY' | 'SELL',
                'lstm_prob': float,
                'transformer_signal': 'BUY' | 'SELL',
                'transformer_prob': float,
                'regime': 'trending' | 'mean_reverting' | 'volatile',
                'risk_score': 0-100
            }
        """

        # Fallback if models not loaded
        if self.lstm_model is None and self.transformer_model is None:
            return self._fallback_signal(market_data)

        try:
            # Engineer features
            features = self.feature_engine.engineer_features(market_data)
            if features is None:
                return self._fallback_signal(market_data)

            # Normalize features
            if self.scaler:
                features = self.scaler.transform(features.reshape(1, -1))[0]

            # Add to buffer
            self.price_buffer.append(features)

            # Need full sequence to make prediction
            if len(self.price_buffer) < self.sequence_length:
                return self._fallback_signal(market_data)

            # Create sequence
            sequence = np.array(list(self.price_buffer))
            X = torch.FloatTensor(sequence).unsqueeze(0).to(DEVICE)

            # Get predictions
            lstm_signal, lstm_prob = self._get_lstm_signal(X)
            transformer_signal, transformer_prob = self._get_transformer_signal(X)

            # Ensemble
            final_signal, confidence = self._ensemble_signals(
                lstm_signal, lstm_prob,
                transformer_signal, transformer_prob,
                market_data.get('volatility', 0.02)
            )

            # Calculate regime
            regime = self._detect_regime(market_data)

            # Calculate risk score
            risk_score = self._calculate_risk_score(market_data.get('volatility', 0.02))

            return {
                'direction': final_signal,
                'confidence': confidence,
                'lstm_signal': lstm_signal,
                'lstm_prob': float(lstm_prob),
                'transformer_signal': transformer_signal,
                'transformer_prob': float(transformer_prob),
                'regime': regime,
                'risk_score': risk_score
            }

        except Exception as e:
            logger.error(f"Error in prediction: {e}")
            return self._fallback_signal(market_data)

    def _get_lstm_signal(self, X: torch.Tensor) -> Tuple[str, float]:
        """Get LSTM signal"""
        if self.lstm_model is None:
            return 'HOLD', 0.5

        with torch.no_grad():
            output = self.lstm_model(X)
            probs = torch.softmax(output, dim=1)[0]
            pred = torch.argmax(output, dim=1).item()

        signal = 'BUY' if pred == 1 else 'SELL'
        prob = probs[pred].item()

        return signal, prob

    def _get_transformer_signal(self, X: torch.Tensor) -> Tuple[str, float]:
        """Get Transformer signal"""
        if self.transformer_model is None:
            return 'HOLD', 0.5

        with torch.no_grad():
            output = self.transformer_model(X)
            probs = torch.softmax(output, dim=1)[0]
            pred = torch.argmax(output, dim=1).item()

        signal = 'BUY' if pred == 1 else 'SELL'
        prob = probs[pred].item()

        return signal, prob

    def _ensemble_signals(self, lstm_sig: str, lstm_prob: float,
                         tf_sig: str, tf_prob: float,
                         volatility: float) -> Tuple[str, float]:
        """Combine LSTM and Transformer signals"""

        # Weight: LSTM 60%, Transformer 40%
        lstm_weight = 0.6
        tf_weight = 0.4

        # Convert signals to numerical
        lstm_val = 1.0 if lstm_sig == 'BUY' else 0.0
        tf_val = 1.0 if tf_sig == 'BUY' else 0.0

        # Weighted ensemble
        ensemble_score = lstm_weight * lstm_prob * lstm_val + tf_weight * tf_prob * tf_val

        # Volatility adjustment: reduce confidence in high volatility
        volatility_adjustment = 1.0 - min(volatility / 0.05, 0.3)  # Max 30% reduction
        confidence = (ensemble_score * volatility_adjustment) * 100

        # Determine final signal
        threshold = 40  # 40% threshold
        if confidence > threshold:
            final_signal = 'BUY'
        elif confidence < (100 - threshold):
            final_signal = 'SELL'
            confidence = 100 - confidence
        else:
            final_signal = 'HOLD'
            confidence = 0

        return final_signal, max(0, min(100, confidence))

    def _detect_regime(self, market_data: dict) -> str:
        """Detect current market regime"""
        close = np.array(market_data.get('close', []))
        if len(close) < 20:
            return 'unknown'

        # Trend detection
        ema_9 = np.mean(close[-9:])
        ema_21 = np.mean(close[-21:])

        # Volatility
        volatility = np.std(close[-20:])

        if volatility > 0.05:
            return 'volatile'
        elif ema_9 > ema_21 * 1.01 or ema_9 < ema_21 * 0.99:
            return 'trending'
        else:
            return 'mean_reverting'

    def _calculate_risk_score(self, volatility: float) -> int:
        """Calculate market risk level (0-100)"""
        # Normalized volatility to risk score
        base_volatility = 0.02
        if volatility < base_volatility:
            risk = int((volatility / base_volatility) * 50)
        else:
            risk = 50 + int((volatility - base_volatility) / 0.05 * 50)

        return max(0, min(100, risk))

    def _fallback_signal(self, market_data: dict) -> Dict:
        """Return conservative signal when models unavailable"""
        close = np.array(market_data.get('close', []))
        volatility = market_data.get('volatility', 0.02)

        if len(close) < 2:
            signal = 'HOLD'
        else:
            # Simple price direction
            signal = 'BUY' if close[-1] > close[-2] else 'SELL'

        return {
            'direction': signal,
            'confidence': 45,  # Low confidence fallback
            'lstm_signal': 'HOLD',
            'lstm_prob': 0.5,
            'transformer_signal': 'HOLD',
            'transformer_prob': 0.5,
            'regime': 'unknown',
            'risk_score': self._calculate_risk_score(volatility)
        }
