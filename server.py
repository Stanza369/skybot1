# server.py - Complete Backend with Auto Withdrawal
from flask import Flask, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit
import threading
import time
import random
from datetime import datetime
import json
import pandas as pd
from social_trading_intelligence import SocialTradingDatabase, SocialIntelligenceEngine, social_simulation_loop
try:
    import MetaTrader5 as mt5
    from order_executor import MT5Broker
    USE_MT5 = True
except ImportError:
    USE_MT5 = False

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Account state
account_balance = 1000.00
trading_enabled = True
WITHDRAW_TARGET = 3000
KEEP_CAPITAL = 1000
balance_lock = threading.Lock()

# Social Intelligence Setup
social_db = SocialTradingDatabase()
social_engine = SocialIntelligenceEngine(social_db)
threading.Thread(target=social_simulation_loop, args=(social_db,), daemon=True).start()

# Initialize Broker
broker = None
if USE_MT5:
    try:
        broker = MT5Broker(symbol="XAUUSD")
        print("✅ MT5 Connected Successfully")
    except Exception as e:
        print(f"❌ MT5 Connection Failed: {e}. Falling back to simulation.")

# AI State
ai_state = {
    'trend_action': 'BUY',
    'trend_confidence': 65,
    'liquidity_action': 'BUY',
    'liquidity_confidence': 72,
    'volatility_action': 'HOLD',
    'volatility_confidence': 55,
    'sentiment_action': 'BUY',
    'sentiment_confidence': 68,
    'orderflow_action': 'BUY',
    'orderflow_confidence': 70
}

def market_loop():
    """Simulate market data (replace with MT5 in production)"""
    global account_balance, trading_enabled
    
    price = 2650.00
    trend = 0
    symbol = "XAUUSD"

    if USE_MT5:
        mt5.initialize()

    while True:
        # Always initialize these so JSON emit never crashes the loop
        high = price + 2
        low = price - 2
        spread = 2.0

        if USE_MT5:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                price = tick.bid
                sym_info = mt5.symbol_info(symbol)
                if sym_info:
                    high = sym_info.session_high
                    low = sym_info.session_low
                spread = round((tick.ask - tick.bid) * 10, 1) # Convert to pips
                
                acc = mt5.account_info()
                if acc:
                    with balance_lock:
                        account_balance = acc.balance

                # Fetch historical rates to calculate real indicators (M5 Timeframe)
                rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M5, 0, 100)
                if rates is not None and len(rates) >= 50:
                    df = pd.DataFrame(rates)
                    closes = df['close'].astype(float)
                    
                    # EMA Cross Prediction (Trend AI)
                    ema_fast = closes.ewm(span=9, adjust=False).mean().iloc[-1]
                    ema_slow = closes.ewm(span=21, adjust=False).mean().iloc[-1]
                    ai_state['trend_action'] = 'BUY' if ema_fast > ema_slow else 'SELL'
                    ai_state['trend_confidence'] = min(95, int(65 + abs(ema_fast - ema_slow) * 10))
                    
                    # RSI Sentiment logic (Sentiment AI)
                    delta = closes.diff()
                    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                    rs = gain / (loss + 1e-9)
                    rsi_val = (100 - (100 / (1 + rs))).iloc[-1]
                    
                    if rsi_val > 70:
                        ai_state['sentiment_action'] = 'SELL'
                        ai_state['sentiment_confidence'] = min(95, int(rsi_val))
                    elif rsi_val < 30:
                        ai_state['sentiment_action'] = 'BUY'
                        ai_state['sentiment_confidence'] = min(95, int(100 - rsi_val))
                    else:
                        ai_state['sentiment_action'] = 'HOLD'
                        ai_state['sentiment_confidence'] = 50

                    # Bollinger Bands (Volatility AI)
                    sma_20 = closes.rolling(window=20).mean()
                    std_20 = closes.rolling(window=20).std()
                    upper_band = sma_20 + (std_20 * 2)
                    lower_band = sma_20 - (std_20 * 2)

                    if closes.iloc[-1] > upper_band.iloc[-1]:
                        ai_state['volatility_action'] = 'SELL'
                        ai_state['volatility_confidence'] = min(95, int(70 + (closes.iloc[-1] - upper_band.iloc[-1]) / (std_20.iloc[-1] + 1e-9) * 20))
                    elif closes.iloc[-1] < lower_band.iloc[-1]:
                        ai_state['volatility_action'] = 'BUY'
                        ai_state['volatility_confidence'] = min(95, int(70 + (lower_band.iloc[-1] - closes.iloc[-1]) / (std_20.iloc[-1] + 1e-9) * 20))
                    else:
                        ai_state['volatility_action'] = 'HOLD'
                        ai_state['volatility_confidence'] = 50
            else:
                # Fallback to simulation logic if tick fails
                price += (random.random() - 0.5)
                ai_state['trend_action'] = 'BUY' if price > 2650 else 'SELL'
        else:
            # Simulation logic (existing)
            trend += (random.random() - 0.5) * 0.3
            price += trend + (random.random() - 0.5) * 0.8
            high, low, spread = price + 2, price - 2, 2.0
            ai_state['trend_action'] = 'BUY' if price > 2650 else 'SELL'
        
        social_bias = social_engine.get_social_bias(symbol)

        # Contrarian AI Logic: Fade the crowd if social confidence is too high
        contrarian_action = 'HOLD'
        contrarian_confidence = 50
        CONTRARIAN_THRESHOLD = 80 # If social confidence > 80%, consider fading

        if social_bias['consensus'] == 'BUY' and social_bias['confidence'] >= CONTRARIAN_THRESHOLD:
            contrarian_action = 'SELL'
            contrarian_confidence = min(95, int(social_bias['confidence'] * 1.1)) # Higher confidence for contrarian
        elif social_bias['consensus'] == 'SELL' and social_bias['confidence'] >= CONTRARIAN_THRESHOLD:
            contrarian_action = 'BUY'
            contrarian_confidence = min(95, int(social_bias['confidence'] * 1.1)) # Higher confidence for contrarian
        
        ai_state['contrarian_action'] = contrarian_action
        ai_state['contrarian_confidence'] = contrarian_confidence
        
        data = {
            'type': 'market_update',
            'price': round(price, 2),
            'high': round(high, 2),
            'low': round(low, 2),
            'spread': spread,
            'latency': random.randint(10, 40),
            'daily_pnl': round((account_balance - 1000), 2),
            'trend': {'action': ai_state['trend_action'], 'confidence': ai_state['trend_confidence']},
            'liquidity': {'action': ai_state['liquidity_action'], 'confidence': ai_state['liquidity_confidence']},
            'volatility': {'action': ai_state['volatility_action'], 'confidence': ai_state['volatility_confidence']},
            'sentiment': {'action': ai_state['sentiment_action'], 'confidence': ai_state['sentiment_confidence']},
            'orderflow': {'action': ai_state['orderflow_action'], 'confidence': ai_state['orderflow_confidence']}, # This was already here
            'social': {'action': social_bias['consensus'], 'confidence': int(social_bias['confidence'])},
            'contrarian': {'action': ai_state['contrarian_action'], 'confidence': ai_state['contrarian_confidence']}
        }
        
        socketio.emit('market_update', data)
        time.sleep(2)

@app.route('/api/trade/buy', methods=['POST'])
def buy():
    global account_balance, trading_enabled
    if not trading_enabled:
        return jsonify({'success': False, 'error': 'Trading disabled - withdraw target reached'})
    
    with balance_lock:
        if not trading_enabled:
            return jsonify({'success': False, 'error': 'Trading locked'})
    
        volume = float(request.args.get('volume', 0.05))
        
        if broker:
            res = broker.execute(side="BUY", volume=volume, price=0)
            pnl = 0 # In real trading, P&L updates via account balance in loop
            success, price, msg = res.success, res.price, res.message
        else:
            price = 2650 + random.random()
            pnl = (random.random() - 0.4) * 100
            account_balance += pnl
            success, msg = True, "Simulated BUY"
        
        social_db.record_trade("BOT_MAIN", "XAUUSD", "BUY", price, volume)
        
        # Check withdrawal target
        if account_balance >= WITHDRAW_TARGET:
            trading_enabled = False

    socketio.emit('trade_result', {'type': 'trade_result', 'pnl': pnl, 'action': 'BUY', 'volume': volume, 'price': price})
    return jsonify({'success': success, 'price': price, 'message': msg})

@app.route('/api/trade/sell', methods=['POST'])
def sell():
    global account_balance, trading_enabled

    with balance_lock:
        if not trading_enabled:
            return jsonify({'success': False, 'error': 'Trading locked'})
    
        volume = float(request.args.get('volume', 0.05))

        if broker:
            res = broker.execute(side="SELL", volume=volume, price=0)
            pnl = 0 
            success, price, msg = res.success, res.price, res.message
        else:
            price = 2650 + (random.random() - 0.5) * 2
            pnl = (random.random() - 0.6) * (50 * volume * 20)
            account_balance += pnl
            success, msg = True, "Simulated SELL"
        
        social_db.record_trade("BOT_MAIN", "XAUUSD", "SELL", price, volume)
        
        if account_balance >= WITHDRAW_TARGET:
            trading_enabled = False
    
    socketio.emit('trade_result', {'type': 'trade_result', 'pnl': pnl, 'action': 'SELL', 'volume': volume, 'price': price})
    return jsonify({'success': success, 'price': price, 'message': msg})

@app.route('/dashboard')
def serve_dashboard():
    return send_from_directory('.', 'dashboard.html')

@app.route('/api/withdraw/request', methods=['POST'])
def request_withdrawal():
    global account_balance, trading_enabled
    with balance_lock:
        withdraw_amount = account_balance - KEEP_CAPITAL
        if withdraw_amount > 0:
            account_balance = KEEP_CAPITAL
            trading_enabled = True
            return jsonify({'success': True, 'amount': withdraw_amount, 'new_balance': account_balance})
    
    return jsonify({'success': False, 'error': 'Insufficient funds for withdrawal'})

if __name__ == '__main__':
    print("""
    ╔══════════════════════════════════════════════════════════════╗
    ║                                                              ║
    ║     🚀 TRADING SERVER - LIVE MODE                           ║
    ║                                                              ║
    ║     WebSocket: ws://localhost:5000                          ║
    ║     Dashboard: http://localhost:5000/dashboard              ║
    ║                                                              ║
    ║     Withdrawal Target: $3,000                               ║
    ║     Keep Capital: $1,000                                    ║
    ║                                                              ║
    ╚══════════════════════════════════════════════════════════════╝
    """)
    
    threading.Thread(target=market_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)