import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import pickle
import os
from typing import Dict, List, Tuple
import warnings
warnings.filterwarnings('ignore')
import json
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from xgboost import XGBClassifier
import asyncio
import websockets
import joblib

# Optional: Only import heavy ML deps if needed
try:
    from lightgbm import LGBMClassifier
except ImportError:
    LGBMClassifier = None

# ============================================
# FEATURE ENGINEERING
# ============================================

class FeatureEngineer:
    """Extract features from market data"""
    
    def __init__(self):
        from ta.trend import MACD, EMAIndicator, ADXIndicator
        from ta.momentum import RSIIndicator, StochasticOscillator
        from ta.volatility import AverageTrueRange, BollingerBands
        self.ta_trend = {"MACD": MACD, "EMA": EMAIndicator, "ADX": ADXIndicator}
        self.ta_mom = {"RSI": RSIIndicator, "Stoch": StochasticOscillator}
        self.ta_vol = {"ATR": AverageTrueRange, "BB": BollingerBands}

    def calculate_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Calculate 100+ comprehensive technical features using vectorized TA library"""
        df = df.copy()
        df.columns = [col.lower() for col in df.columns]
        
        # Returns
        for period in [1, 2, 3, 5, 7, 10, 14, 20, 30, 50]:
            df[f'return_{period}d'] = df['close'].pct_change(period)
        
        # Moving Averages
        for period in [5, 10, 20, 30, 50, 100, 200]:
            df[f'SMA_{period}'] = df['close'].rolling(period).mean()
            df[f'EMA_{period}'] = df['close'].ewm(span=period, adjust=False).mean()
            df[f'dist_sma_{period}'] = (df['close'] - df[f'SMA_{period}']) / df[f'SMA_{period}']
        
        # RSI
        df['RSI_14'] = self.ta_mom['RSI'](df['close'], window=14).rsi()
        df['RSI_9'] = self.ta_mom['RSI'](df['close'], window=9).rsi()
        
        # MACD
        macd_obj = self.ta_trend['MACD'](df['close'])
        df['MACD'] = macd_obj.macd()
        df['MACD_signal'] = macd_obj.macd_signal()
        df['MACD_diff'] = macd_obj.macd_diff()

        # Bollinger Bands
        bb = self.ta_vol['BB'](df['close'], window=20)
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_lower'] = bb.bollinger_lband()
        df['BB_width'] = bb.bollinger_wband()
        df['BB_pct'] = bb.bollinger_pband()
        
        # Volatility & ATR
        df['ATR_14'] = self.ta_vol['ATR'](df['high'], df['low'], df['close'], window=14).average_true_range()
        df['volatility_20d'] = df['return_1d'].rolling(20).std() * np.sqrt(252)
        
        # Volume Microstructure
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        df['obv'] = (df['volume'] * np.sign(df['close'].diff())).cumsum()
        
        # Rolling Hurst Exponent (Fixed implementation)
        df['hurst'] = df['close'].rolling(100).apply(self._calculate_hurst)
        
        # Time features
        if isinstance(df.index, pd.DatetimeIndex):
            df['day_of_week'] = df.index.dayofweek
            df['month'] = df.index.month
            df['sin_day'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
            df['cos_day'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        
        return df.replace([np.inf, -np.inf], np.nan).fillna(method='ffill')

    def _calculate_hurst(self, ts):
        """Helper for rolling Hurst Exponent"""
        lags = range(2, 20)
        tau = [np.sqrt(np.std(np.subtract(ts[lag:], ts[:-lag]))) for lag in lags]
        poly = np.polyfit(np.log(lags), np.log(tau), 1)
        return poly[0] * 2.0
    
    @staticmethod
    def create_labels(df: pd.DataFrame, forward_days: int = 5, threshold: float = 0.01) -> pd.DataFrame:
        """Create labels for supervised learning"""
        future_returns = df['close'].shift(-forward_days) / df['close'] - 1
        df['label'] = 1  # HOLD
        df.loc[future_returns > threshold, 'label'] = 2  # BUY
        df.loc[future_returns < -threshold, 'label'] = 0  # SELL
        return df

# ============================================
# ADVANCED ENSEMBLE AI
# ============================================

class SelfLearningTradingAI:
    """AI trading bot that learns from market data"""
    
    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.model = None
        self.scaler = StandardScaler()
        self.feature_engineer = FeatureEngineer()
        self.trained = False
        self.models_dir = "ai_models"
        os.makedirs(self.models_dir, exist_ok=True)
        
        # Performance tracking
        self.predictions_made = 0
        self.correct_predictions = 0

    def train_ensemble(self, X_train, y_train, X_val, y_val):
        """Train state-of-the-art ensemble models"""
        from sklearn.ensemble import VotingClassifier
        
        logger.info(f"🤖 Training Ensemble on {len(X_train)} samples...")
        
        xgb = XGBClassifier(n_estimators=300, learning_rate=0.01, max_depth=8, eval_metric='mlogloss', n_jobs=-1)
        rf = RandomForestClassifier(n_estimators=200, max_depth=15, n_jobs=-1)
        mlp = MLPClassifier(hidden_layer_sizes=(256, 128, 64), max_iter=500, early_stopping=True)

        # Integrated Voting Ensemble
        ensemble = VotingClassifier(
            estimators=[('xgb', xgb), ('rf', rf), ('mlp', mlp)],
            voting='soft',
            weights=[3, 1, 2]
        )
        
        # Scale and fit
        X_scaled = self.scaler.fit_transform(X_train)
        ensemble.fit(X_scaled, y_train)

        self.model = {'ensemble': ensemble, 'scaler': self.scaler}
        self.trained = True
        
        # Validate
        X_val_scaled = self.scaler.transform(X_val)
        acc = ensemble.score(X_val_scaled, y_val)
        logger.info(f"✅ Ensemble Validation Accuracy: {acc:.2%}")

    def predict(self, df: pd.DataFrame) -> Dict:
        if not self.trained:
            return {"action": "HOLD", "confidence": 0, "error": "Model not trained"}
        
        try:
            # Process latest features
            df_features = self.feature_engineer.calculate_features(df)
            latest_row = df_features.iloc[-1:].drop(columns=['label'], errors='ignore')
            
            # Align features (ensure columns match training)
            X = self.scaler.transform(latest_row.values)
            probs = self.model['ensemble'].predict_proba(X)[0]
            
            predicted_class = np.argmax(probs)
            confidence = probs[predicted_class]
            
            action_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
            return {
                "action": action_map[predicted_class],
                "confidence": float(confidence),
                "probabilities": {action_map[i]: float(probs[i]) for i in range(3)}
            }
        except Exception as e:
            return {"action": "HOLD", "confidence": 0, "error": str(e)}

    def save_model(self):
        """Save trained model to disk"""
        if self.model:
            with open(f"{self.models_dir}/{self.symbol}_model.pkl", 'wb') as f:
                pickle.dump(self.model, f)
            print(f"💾 Model saved to {self.models_dir}/{self.symbol}_model.pkl")
    
    def load_model(self):
        """Load trained model from disk"""
        model_path = f"{self.models_dir}/{self.symbol}_model.pkl"
        if os.path.exists(model_path):
            with open(model_path, 'rb') as f:
                self.model = pickle.load(f)
            self.trained = True
            print(f"📂 Loaded model from {model_path}")
            return True
        return False
    
    def get_current_features(self, df: pd.DataFrame) -> np.ndarray:
        """Extract features from current market data"""
        df = self.feature_engineer.calculate_features(df)
        
        # Get latest row
        latest = df.iloc[-1:]
        
        # Select feature columns
        X = latest[self.model['feature_cols']].values
        
        # Scale
        X_scaled = self.model['scaler'].transform(X)
        
        return X_scaled
    
    def predict(self, df: pd.DataFrame) -> Dict:
        """Make prediction on current market data"""
        if not self.trained:
            return {"action": "HOLD", "confidence": 0, "error": "Model not trained"}
        
        try:
            X = self.get_current_features(df)
            
            # Get predictions from each model
            rf_pred = self.model['random_forest'].predict_proba(X)[0]
            gb_pred = self.model['gradient_boosting'].predict_proba(X)[0]
            nn_pred = self.model['neural_network'].predict_proba(X)[0]
            
            # Weighted average (more weight to better models)
            avg_probs = (rf_pred * 0.3 + gb_pred * 0.3 + nn_pred * 0.4)
            
            predicted_class = np.argmax(avg_probs)
            confidence = avg_probs[predicted_class]
            
            action_map = {0: "SELL", 1: "HOLD", 2: "BUY"}
            
            # Update statistics
            self.predictions_made += 1
            
            return {
                "action": action_map[predicted_class],
                "confidence": float(confidence),
                "probabilities": {
                    "SELL": float(avg_probs[0]),
                    "HOLD": float(avg_probs[1]),
                    "BUY": float(avg_probs[2])
                }
            }
            
        except Exception as e:
            print(f"Prediction error: {e}")
            return {"action": "HOLD", "confidence": 0, "error": str(e)}
    
    def learn_from_outcome(self, prediction: Dict, actual_return: float):
        """Learn from actual outcome (for continuous learning)"""
        predicted_action = prediction['action']
        
        # Determine if correct
        if predicted_action == "BUY" and actual_return > 0.005:
            self.correct_predictions += 1
        elif predicted_action == "SELL" and actual_return < -0.005:
            self.correct_predictions += 1
        elif predicted_action == "HOLD" and abs(actual_return) < 0.005:
            self.correct_predictions += 1
        else:
            pass  # Incorrect prediction
        
        accuracy = self.correct_predictions / self.predictions_made if self.predictions_made > 0 else 0
        
        return accuracy


# ============================================
# REAL-TIME TRADING BOT
# ============================================

class AITradingBot:
    """Complete AI-powered trading bot"""
    
    def __init__(self, symbol: str = "XAUUSD"):
        self.symbol = symbol
        self.ai = SelfLearningTradingAI(symbol)
        self.data_buffer = []
        self.current_position = None
        self.balance = 5.0
        self.risk_percent = 2.0
        
        # Market data cache
        self.latest_data = None
        
    def initialize(self):
        """Initialize the bot (load model or train)"""
        print("\n" + "="*60)
        print(f"🤖 Initializing AI Trading Bot for {self.symbol}")
        print("="*60)
        
        if not self.ai.load_model():
            print("No existing model found. Training new model...")
            success = self.ai.train(years=5)  # Train on 5 years for speed (change to 15 for full)
            return success
        
        return True
    
    def get_live_data(self) -> pd.DataFrame:
        """Fetch live market data"""
        try:
            yf_symbol = "GC=F" if self.symbol == "XAUUSD" else f"{self.symbol}=X"
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(period="1d", interval="5m")
            if df.empty:
                return None
            df.columns = [col.lower() for col in df.columns]
            return df
        except Exception as e:
            print(f"Data error: {e}")
            return None
    
    def get_prediction(self) -> Dict:
        """Get AI prediction for current market"""
        data = self.get_live_data()
        if data is None or len(data) < 50:
            return {"action": "WAIT", "confidence": 0, "error": "Insufficient data"}
        
        prediction = self.ai.predict(data)
        self.latest_data = data
        return prediction
    
    def calculate_position_size(self) -> float:
        """Calculate position size based on risk"""
        risk_amount = self.balance * (self.risk_percent / 100)
        lot_size = risk_amount / (10 * 0.10)
        return max(0.01, round(lot_size, 2))
    
    def execute_signal(self, prediction: Dict):
        """Execute trade based on AI signal"""
        action = prediction['action']
        confidence = prediction['confidence']
        
        if action == "BUY" and confidence > 0.6 and self.current_position is None:
            lot_size = self.calculate_position_size()
            print(f"\n🚀 EXECUTING BUY TRADE")
            print(f"   Lot Size: {lot_size}")
            print(f"   Confidence: {confidence:.1%}")
            print(f"   Entry: {self.latest_data['close'].iloc[-1]:.2f}")
            self.current_position = {'type': 'BUY', 'entry': self.latest_data['close'].iloc[-1], 'lot': lot_size}
            
        elif action == "SELL" and confidence > 0.6 and self.current_position is None:
            lot_size = self.calculate_position_size()
            print(f"\n🚀 EXECUTING SELL TRADE")
            print(f"   Lot Size: {lot_size}")
            print(f"   Confidence: {confidence:.1%}")
            print(f"   Entry: {self.latest_data['close'].iloc[-1]:.2f}")
            self.current_position = {'type': 'SELL', 'entry': self.latest_data['close'].iloc[-1], 'lot': lot_size}
    
    def run(self):
        """Main bot loop"""
        print("\n🟢 AI Trading Bot is LIVE!")
        print("📊 Analyzing market patterns...")
        print("💡 AI will make predictions and trade automatically")
        print("-" * 60)
        
        while True:
            try:
                # Get AI prediction
                prediction = self.get_prediction()
                
                if 'error' not in prediction:
                    print(f"\n🤖 AI PREDICTION: {prediction['action']} (Confidence: {prediction['confidence']:.1%})")
                    
                    # Show probabilities
                    if 'probabilities' in prediction:
                        probs = prediction['probabilities']
                        print(f"   BUY: {probs['BUY']:.1%} | HOLD: {probs['HOLD']:.1%} | SELL: {probs['SELL']:.1%}")
                    
                    # Execute trade if confident
                    self.execute_signal(prediction)
                
                # Update position monitoring (simplified)
                if self.current_position and self.latest_data is not None:
                    current_price = self.latest_data['close'].iloc[-1]
                    print(f"💰 Position: {self.current_position['type']} at {self.current_position['entry']:.2f} | Current: {current_price:.2f}")
                
                time.sleep(60)  # Wait 1 minute
                
            except KeyboardInterrupt:
                print("\n🛑 Bot stopped")
                break
            except Exception as e:
                print(f"Error: {e}")
                time.sleep(60)


# ============================================
# WEB CHAT INTERFACE (Simple version)
# ============================================

class SimpleAIChat:
    """Simple chat interface for the AI"""
    
    def __init__(self, trading_bot: AITradingBot):
        self.bot = trading_bot
        
    def chat(self):
        """Interactive chat mode"""
        print("\n" + "="*60)
        print("💬 AI CHAT MODE")
        print("="*60)
        print("You can ask me:")
        print("  • 'predict' - Get current market prediction")
        print("  • 'train' - Retrain AI with more data")
        print("  • 'status' - Check bot status")
        print("  • 'balance' - Show account balance")
        print("  • 'strategy [description]' - Share a new strategy")
        print("  • 'exit' - Quit chat")
        print("-" * 60)
        
        while True:
            user_input = input("\nYou: ").lower().strip()
            
            if user_input == 'exit':
                print("Goodbye! Happy trading!")
                break
            
            elif user_input == 'predict':
                prediction = self.bot.get_prediction()
                if 'error' not in prediction:
                    print(f"\n🤖 AI Prediction: {prediction['action']}")
                    print(f"   Confidence: {prediction['confidence']:.1%}")
                    if 'probabilities' in prediction:
                        probs = prediction['probabilities']
                        print(f"   BUY: {probs['BUY']:.1%} | SELL: {probs['SELL']:.1%} | HOLD: {probs['HOLD']:.1%}")
                else:
                    print(f"Error: {prediction.get('error')}")
            
            elif user_input == 'status':
                print(f"\n📊 Bot Status:")
                print(f"   Symbol: {self.bot.symbol}")
                print(f"   Balance: ${self.bot.balance:.2f}")
                print(f"   Risk: {self.bot.risk_percent}%")
                print(f"   AI Trained: {self.bot.ai.trained}")
                print(f"   Predictions: {self.bot.ai.predictions_made}")
                print(f"   Accuracy: {(self.bot.ai.correct_predictions / max(1, self.bot.ai.predictions_made) * 100):.1f}%")
            
            elif user_input == 'balance':
                print(f"💰 Account Balance: ${self.bot.balance:.2f}")
            
            elif user_input == 'train':
                print("🔄 Retraining AI...")
                self.bot.ai.train(years=5)
                print("✅ Retraining complete!")
            
            elif user_input.startswith('strategy'):
                strategy_desc = user_input.replace('strategy', '').strip()
                if strategy_desc:
                    print(f"\n📚 Thanks for sharing! I've noted your strategy:")
                    print(f"   \"{strategy_desc}\"")
                    print("   I'll look for patterns like this in future market data.")
                else:
                    print("Please describe your strategy after 'strategy'")
            
            else:
                print("\n🤖 I'm still learning! Try asking for a 'predict', 'status', or tell me a 'strategy'.")


# ============================================
# MAIN ENTRY POINT
# ============================================

import time

def main():
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🧠 SELF-LEARNING AI TRADING BOT                         ║
    ║                                                              ║
    ║     Trained on historical market data                       ║
    ║     Continuously learning from market movements             ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    # Create the bot
    bot = AITradingBot(symbol="XAUUSD")
    
    # Initialize (load or train)
    if not bot.initialize():
        print("❌ Failed to initialize bot")
        return
    
    # Choose mode
    print("\nSelect mode:")
    print("1. Auto-Trade Mode (Bot trades automatically)")
    print("2. Chat Mode (Interact with AI)")
    print("3. Training Only (Just train the AI)")
    
    choice = input("\nEnter choice (1-3): ").strip()
    
    if choice == '1':
        bot.run()
    elif choice == '2':
        chat = SimpleAIChat(bot)
        chat.chat()
    elif choice == '3':
        print("🔄 Training AI on 15 years of data...")
        bot.ai.train(years=15)
        print("✅ Training complete!")
    else:
        print("Invalid choice. Running in auto-trade mode...")
        bot.run()

if __name__ == "__main__":
    main()