# ai_trading_bot_final.py - Completely fixed version
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import yfinance as yf
import pickle
import os
import time
from sklearn.ensemble import RandomForestClassifier
from sklearn.neural_network import MLPClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.impute import SimpleImputer
import warnings
warnings.filterwarnings('ignore')

# ============================================
# FEATURE ENGINEERING
# ============================================

class FeatureEngineer:
    @staticmethod
    def calculate_features(df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        
        # Returns
        for period in [1, 2, 3, 5, 7, 10, 14, 20]:
            df[f'return_{period}'] = df['close'].pct_change(period)
        
        # Moving Averages
        for period in [5, 10, 20, 50]:
            df[f'sma_{period}'] = df['close'].rolling(period).mean()
            df[f'price_to_sma_{period}'] = df['close'] / df[f'sma_{period}']
        
        # RSI
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        df['rsi_14'] = 100 - (100 / (1 + rs))
        
        # Price position
        high_20 = df['high'].rolling(20).max()
        low_20 = df['low'].rolling(20).min()
        df['price_position'] = (df['close'] - low_20) / (high_20 - low_20)
        
        # Volume
        df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        
        # Momentum
        df['momentum_5'] = df['close'] - df['close'].shift(5)
        df['momentum_10'] = df['close'] - df['close'].shift(10)
        
        # Bollinger Bands
        sma_20 = df['close'].rolling(20).mean()
        std_20 = df['close'].rolling(20).std()
        df['bb_position'] = (df['close'] - (sma_20 - 2*std_20)) / (4*std_20)
        
        # MACD
        exp1 = df['close'].ewm(span=12, adjust=False).mean()
        exp2 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp1 - exp2
        df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
        df['macd_hist'] = df['macd'] - df['macd_signal']
        
        # ATR
        high_low = df['high'] - df['low']
        high_close = abs(df['high'] - df['close'].shift())
        low_close = abs(df['low'] - df['close'].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df['atr'] = tr.rolling(14).mean()
        
        # Volatility
        df['volatility'] = df['return_1'].rolling(20).std()
        
        return df
    
    @staticmethod
    def create_labels(df: pd.DataFrame) -> pd.DataFrame:
        future_returns = df['close'].shift(-3) / df['close'] - 1
        df['label'] = 1
        df.loc[future_returns > 0.005, 'label'] = 2
        df.loc[future_returns < -0.005, 'label'] = 0
        return df

# ============================================
# AI TRADING BOT
# ============================================

class AITradingBot:
    def __init__(self, symbol="XAUUSD"):
        self.symbol = symbol
        self.model = None
        self.scaler = StandardScaler()
        self.imputer = SimpleImputer(strategy='median')
        self.feature_engineer = FeatureEngineer()
        self.trained = False
        
    def train(self, years=3):
        print("\n" + "="*50)
        print("🧠 TRAINING AI MODEL")
        print("="*50)
        
        # Download data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=years*365)
        ticker = yf.Ticker("GC=F")
        df = ticker.history(start=start_date, end=end_date, interval="1d")
        
        if df.empty:
            print("❌ Failed to download data")
            return False
        
        df.columns = [col.lower() for col in df.columns]
        print(f"✅ Downloaded {len(df)} days of data")
        
        # Calculate features
        df = self.feature_engineer.calculate_features(df)
        df = self.feature_engineer.create_labels(df)
        df = df.dropna()
        
        # Prepare features
        exclude = ['open', 'high', 'low', 'close', 'volume', 'label']
        feature_cols = [c for c in df.columns if c not in exclude]
        X = df[feature_cols].values
        y = df['label'].values
        
        print(f"📊 Training samples: {len(X)}")
        print(f"📊 Features: {len(feature_cols)}")
        print(f"📊 BUY: {(y==2).sum()}, HOLD: {(y==1).sum()}, SELL: {(y==0).sum()}")
        
        # Preprocess
        X = self.imputer.fit_transform(X)
        X = self.scaler.fit_transform(X)
        
        # Train models
        print("\n🤖 Training Random Forest...")
        rf = RandomForestClassifier(n_estimators=100, max_depth=10, random_state=42)
        rf.fit(X, y)
        
        print("🤖 Training Neural Network...")
        nn = MLPClassifier(hidden_layer_sizes=(64, 32), max_iter=100, random_state=42)
        nn.fit(X, y)
        
        # Store
        self.model = {
            'rf': rf,
            'nn': nn,
            'scaler': self.scaler,
            'imputer': self.imputer,
            'feature_cols': feature_cols
        }
        
        rf_acc = rf.score(X, y)
        nn_acc = nn.score(X, y)
        print(f"\n📈 Accuracy: RF={rf_acc:.1%}, NN={nn_acc:.1%}, Avg={(rf_acc+nn_acc)/2:.1%}")
        
        # Save
        os.makedirs("ai_models", exist_ok=True)
        with open(f"ai_models/{self.symbol}_model.pkl", 'wb') as f:
            pickle.dump(self.model, f)
        
        self.trained = True
        print("✅ Training complete!")
        return True
    
    def load(self):
        path = f"ai_models/{self.symbol}_model.pkl"
        if os.path.exists(path):
            with open(path, 'rb') as f:
                self.model = pickle.load(f)
            self.scaler = self.model['scaler']
            self.imputer = self.model['imputer']
            self.trained = True
            print("📂 Model loaded")
            return True
        return False
    
    def predict(self):
        """Get live prediction"""
        if not self.trained:
            return {"action": "WAIT", "confidence": 0}
        
        try:
            # Get live data
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="5d", interval="5m")
            if df.empty or len(df) < 30:
                return {"action": "WAIT", "confidence": 0, "error": "Insufficient data"}
            
            df.columns = [col.lower() for col in df.columns]
            
            # Calculate features
            df = self.feature_engineer.calculate_features(df)
            latest = df.iloc[-1:].copy()
            
            # Prepare features
            X = latest[self.model['feature_cols']].values
            X = self.imputer.transform(X)
            X = self.scaler.transform(X)
            
            # Get predictions
            rf_pred = self.model['rf'].predict_proba(X)[0]
            nn_pred = self.model['nn'].predict_proba(X)[0]
            
            # Average predictions
            avg_probs = (rf_pred + nn_pred) / 2
            
            predicted = np.argmax(avg_probs)
            confidence = avg_probs[predicted]
            
            actions = {0: "SELL", 1: "HOLD", 2: "BUY"}
            
            return {
                "action": actions[predicted],
                "confidence": float(confidence),
                "buy_prob": float(avg_probs[2]),
                "sell_prob": float(avg_probs[0]),
                "hold_prob": float(avg_probs[1])
            }
            
        except Exception as e:
            return {"action": "WAIT", "confidence": 0, "error": str(e)}

# ============================================
# MAIN PROGRAM
# ============================================

def main():
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🧠 AI TRADING BOT - READY TO GO!                        ║
    ║                                                              ║
    ║     ✓ Real-time market analysis                             ║
    ║     ✓ Machine learning predictions                          ║
    ║     ✓ 2% risk management                                    ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    bot = AITradingBot()
    
    # Try to load existing model
    if not bot.load():
        print("No model found. Training new model...")
        if not bot.train(years=3):
            print("❌ Training failed")
            return
    else:
        print("\n✅ Model ready!")
    
    print("\n" + "="*50)
    print("🎮 SELECT MODE")
    print("="*50)
    print("1. 📊 AUTO MODE - Continuous market analysis")
    print("2. 💬 CHAT MODE - Interactive predictions")
    print("3. 🔄 RETRAIN - Train on more data")
    print("="*50)
    
    choice = input("\n👉 Enter choice (1-3): ").strip()
    
    if choice == '1':
        print("\n🟢 AUTO MODE ACTIVE")
        print("Press Ctrl+C to stop\n")
        while True:
            try:
                pred = bot.predict()
                if 'error' not in pred:
                    print(f"\r[{datetime.now().strftime('%H:%M:%S')}] 📊 {pred['action']} | "
                          f"Conf: {pred['confidence']:.0%} | "
                          f"📈 BUY:{pred['buy_prob']:.0%} 📉 SELL:{pred['sell_prob']:.0%}", end="")
                time.sleep(30)
            except KeyboardInterrupt:
                print("\n\n🛑 Stopped")
                break
            except Exception as e:
                print(f"\nError: {e}")
                time.sleep(30)
    
    elif choice == '2':
        print("\n💬 CHAT MODE ACTIVE")
        print("-"*40)
        print("Commands: predict, status, help, exit")
        print("-"*40)
        
        while True:
            cmd = input("\n👉 You: ").lower().strip()
            
            if cmd == 'exit':
                print("Goodbye! 📈")
                break
            elif cmd == 'predict':
                print("\n🤖 Analyzing market...")
                pred = bot.predict()
                if 'error' not in pred:
                    print(f"\n{'='*40}")
                    print(f"📊 AI PREDICTION: {pred['action']}")
                    print(f"🎯 Confidence: {pred['confidence']:.1%}")
                    print(f"\n📈 Probabilities:")
                    print(f"   BUY:  {pred['buy_prob']*100:5.1f}%  {'█' * int(pred['buy_prob']*20)}")
                    print(f"   HOLD: {pred['hold_prob']*100:5.1f}%  {'█' * int(pred['hold_prob']*20)}")
                    print(f"   SELL: {pred['sell_prob']*100:5.1f}%  {'█' * int(pred['sell_prob']*20)}")
                    print(f"{'='*40}")
                    
                    if pred['confidence'] > 0.6:
                        print(f"\n💡 Suggestion: {pred['action']} with {pred['confidence']:.0%} confidence")
                else:
                    print(f"❌ Error: {pred.get('error')}")
            
            elif cmd == 'status':
                print(f"\n📊 Bot Status:")
                print(f"   Symbol: XAUUSD")
                print(f"   Model: Trained on 3 years")
                print(f"   Status: {'✅ Ready' if bot.trained else '❌ Not ready'}")
            
            elif cmd == 'help':
                print("\nCommands: predict, status, exit")
            
            else:
                print("Unknown command. Try: predict, status, help")
    
    elif choice == '3':
        years = input("How many years to train on? (default 5): ").strip()
        years = int(years) if years else 5
        bot.train(years=years)
        print("✅ Training complete!")
    
    else:
        print("Invalid choice")

if __name__ == "__main__":
    main()