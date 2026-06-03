# server.py - Complete Backend with Auto Withdrawal
from flask import Flask, request, jsonify, send_from_directory, session
from flask_socketio import SocketIO, emit
import threading
import time
import random
from datetime import datetime
import json
import pandas as pd
from social_trading_intelligence import SocialTradingDatabase, SocialIntelligenceEngine, social_simulation_loop
from ai_inference import AIInferenceEngine
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import MetaTrader5 as mt5
    from order_executor import MT5Broker, MT5BrokerManager
    USE_MT5 = True
except ImportError:
    USE_MT5 = False


app = Flask(__name__)
# Use session for auth gating (default for this repo)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')


# Needed for session-based auth decorators/endpoints
from flask import session


# Account state (global for legacy mode)

account_balance = 1000.00
trading_enabled = True
WITHDRAW_TARGET = 3000
KEEP_CAPITAL = 1000
balance_lock = threading.Lock()

# --- PRO auth/admin + persistence (Phase 1/2) ---
from database_store import JsonStore
from security_utils import SecurityUtils
from admin_auth import require_admin, require_approved, require_login

store = JsonStore()
security = SecurityUtils()

# Ensure default admin exists on first run
_USERS_DEFAULT_ADMIN = {
    "admin": {
        "username": "admin",
        "password_hash": security.hash_password("admin123"),
        "email": "admin@trading.com",
        "status": "approved",
        "role": "admin",
        "balance": 0,
        "registered_at": time.time(),
    }
}

users = store.load_users()
if "admin" not in users:
    users.update(_USERS_DEFAULT_ADMIN)
    store.save_users(users)



# Social Intelligence Setup
social_db = SocialTradingDatabase()
social_engine = SocialIntelligenceEngine(social_db)
threading.Thread(target=social_simulation_loop, args=(social_db,), daemon=True).start()

# Initialize legacy/global broker removed for per-user credentials.
# Trade endpoints will create an MT5 connection on-demand using MT5BrokerManager.
mt5_manager = MT5BrokerManager(symbol="XAUUSD") if USE_MT5 else None

# Initialize AI Inference Engine (loads trained models if available)
try:
    ai_engine = AIInferenceEngine()
    logger.info("AI Inference Engine initialized")
except Exception as e:
    logger.warning(f"AI Engine failed to initialize: {e}. Using fallback signals.")
    ai_engine = None



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
                    highs = df['high'].astype(float)
                    lows = df['low'].astype(float)
                    opens = df['open'].astype(float)

                    # Use AI Inference Engine if available
                    if ai_engine:
                        try:
                            volatility = closes.std() / closes.mean()
                            market_data = {
                                'close': closes.tolist(),
                                'high': highs.tolist(),
                                'low': lows.tolist(),
                                'open': opens.tolist(),
                                'volatility': volatility
                            }

                            # Get AI prediction
                            ai_prediction = ai_engine.predict(market_data)

                            # Update AI state with real predictions
                            ai_state['trend_action'] = ai_prediction['direction']
                            ai_state['trend_confidence'] = int(ai_prediction['confidence'])
                            ai_state['volatility_action'] = 'BUY' if ai_prediction['regime'] == 'mean_reverting' else 'SELL' if ai_prediction['regime'] == 'trending' else 'HOLD'
                            ai_state['volatility_confidence'] = ai_prediction['risk_score']
                            ai_state['sentiment_action'] = ai_prediction['lstm_signal']
                            ai_state['sentiment_confidence'] = int(ai_prediction['lstm_prob'] * 100)
                            ai_state['orderflow_action'] = ai_prediction['transformer_signal']
                            ai_state['orderflow_confidence'] = int(ai_prediction['transformer_prob'] * 100)

                            logger.debug(f"AI Prediction: {ai_prediction['direction']} (confidence={ai_prediction['confidence']:.1f}%, regime={ai_prediction['regime']})")

                        except Exception as e:
                            logger.warning(f"AI prediction failed: {e}, using EMA fallback")
                            # Fallback to EMA cross
                            ema_fast = closes.ewm(span=9, adjust=False).mean().iloc[-1]
                            ema_slow = closes.ewm(span=21, adjust=False).mean().iloc[-1]
                            ai_state['trend_action'] = 'BUY' if ema_fast > ema_slow else 'SELL'
                            ai_state['trend_confidence'] = min(95, int(65 + abs(ema_fast - ema_slow) * 10))
                    else:
                        # Fallback to traditional indicators (EMA Cross)
                        ema_fast = closes.ewm(span=9, adjust=False).mean().iloc[-1]
                        ema_slow = closes.ewm(span=21, adjust=False).mean().iloc[-1]
                        ai_state['trend_action'] = 'BUY' if ema_fast > ema_slow else 'SELL'
                        ai_state['trend_confidence'] = min(95, int(65 + abs(ema_fast - ema_slow) * 10))

                        # RSI Sentiment logic
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
@require_approved
def buy():
    global account_balance, trading_enabled
    if not trading_enabled:
        return jsonify({'success': False, 'error': 'Trading disabled - withdraw target reached'})

    with balance_lock:
        if not trading_enabled:
            return jsonify({'success': False, 'error': 'Trading locked'})
        volume = float(request.args.get('volume', 0.05))

    success = False
    price = 0.0
    pnl = 0.0
    msg = ''

    username = session.get('user_id')
    selected_id = None
    selected_acc = None

    try:
        all_accounts = store.load_mt5_accounts()
        user_blob = all_accounts.get(username) or {}
        selected_id = user_blob.get('selected_account_id')
        accounts_list = user_blob.get('accounts') or []
        selected_acc = next((a for a in accounts_list if a.get('id') == selected_id), None)
    except Exception as e:
        msg = f"Account load error: {e}"
        selected_acc = None

    if mt5_manager and selected_acc and USE_MT5:
        try:
            login = int(selected_acc.get('mt5_login'))
            enc_pw = selected_acc.get('mt5_password_enc') or ''
            if not enc_pw:
                raise ValueError('Missing encrypted password')
            password = security.decrypt_text(enc_pw)
            server_name = str(selected_acc.get('mt5_server') or '')
            res = mt5_manager.execute_market_order(
                login=login, password=password, server=server_name,
                side="BUY", volume=volume,
            )
            pnl = 0.0
            success, price, msg = res.success, float(res.price or 0.0), str(res.message or '')
        except Exception as e:
            success = False
            msg = f"MT5 execute failed: {e}"

    if not success:
        price = 2650.0 + random.random()
        pnl = (random.random() - 0.4) * 100
        account_balance += pnl
        success, msg = True, f"Simulated BUY ({msg})" if msg else "Simulated BUY"

    social_db.record_trade("BOT_MAIN", "XAUUSD", "BUY", price, volume)
    if account_balance >= WITHDRAW_TARGET:
        trading_enabled = False

    socketio.emit('trade_result', {'type': 'trade_result', 'pnl': pnl, 'action': 'BUY', 'volume': volume, 'price': price})
    return jsonify({'success': success, 'price': price, 'message': msg})

@app.route('/api/trade/sell', methods=['POST'])
@require_approved
def sell():
    global account_balance, trading_enabled

    with balance_lock:
        if not trading_enabled:
            return jsonify({'success': False, 'error': 'Trading locked'})

        volume = float(request.args.get('volume', 0.05))

    success = False
    price = 0.0
    pnl = 0.0
    msg = ''

    username = session.get('user_id')
    selected_id = None
    selected_acc = None
    try:
        all_accounts = store.load_mt5_accounts()
        user_blob = all_accounts.get(username) or {}
        selected_id = user_blob.get('selected_account_id')
        accounts_list = user_blob.get('accounts') or []
        selected_acc = next((a for a in accounts_list if a.get('id') == selected_id), None)
    except Exception as e:
        msg = f"Account load error: {e}"

    if mt5_manager and selected_acc and USE_MT5:
        try:
            login = int(selected_acc.get('mt5_login'))
            enc_pw = selected_acc.get('mt5_password_enc') or ''
            if not enc_pw:
                raise ValueError('Missing encrypted password')
            password = security.decrypt_text(enc_pw)
            server_name = str(selected_acc.get('mt5_server') or '')
            res = mt5_manager.execute_market_order(
                login=login, password=password, server=server_name,
                side="SELL", volume=volume,
            )
            pnl = 0.0
            success, price, msg = res.success, float(res.price or 0.0), str(res.message or '')
        except Exception as e:
            success = False
            msg = f"MT5 execute failed: {e}"

    if not success:
        price = 2650.0 + (random.random() - 0.5) * 2
        pnl = (random.random() - 0.6) * (50 * volume * 20)
        account_balance += pnl
        success, msg = True, f"Simulated SELL ({msg})" if msg else "Simulated SELL"

    social_db.record_trade("BOT_MAIN", "XAUUSD", "SELL", price, volume)
    if account_balance >= WITHDRAW_TARGET:
        trading_enabled = False
    
    socketio.emit('trade_result', {'type': 'trade_result', 'pnl': pnl, 'action': 'SELL', 'volume': volume, 'price': price})
    return jsonify({'success': success, 'price': price, 'message': msg})

@app.route('/dashboard')
@require_login
def serve_dashboard():
    return send_from_directory('.', 'dashboard.html')


# --- MT5 Accounts (Encrypted) ---


MT5_ACCOUNTS_DEFAULT_SCHEMA = {
    "accounts": [],
    "selected_account_id": None,
}


@app.route('/api/mt5/accounts/add', methods=['POST'])
@require_approved
def mt5_accounts_add():
    data = request.json or {}
    name = (data.get('name') or '').strip()
    mt5_login = str(data.get('mt5_login') or '').strip()
    mt5_password = data.get('mt5_password') or ''
    mt5_server = (data.get('mt5_server') or '').strip()

    if not name:
        return jsonify({'success': False, 'error': 'name is required'}), 400
    if not mt5_login or not mt5_login.isdigit():
        return jsonify({'success': False, 'error': 'mt5_login must be numeric string'}), 400
    if not mt5_password or len(mt5_password) < 1:
        return jsonify({'success': False, 'error': 'mt5_password is required'}), 400
    if not mt5_server:
        return jsonify({'success': False, 'error': 'mt5_server is required'}), 400

    username = session.get('user_id')
    if not username:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    all_accounts = store.load_mt5_accounts()
    user_blob = all_accounts.get(username) or dict(MT5_ACCOUNTS_DEFAULT_SCHEMA)
    accounts_list = user_blob.get('accounts') or []

    account_id = f"acc_{int(time.time())}_{random.randint(1000,9999)}"
    enc_pw = security.encrypt_text(mt5_password)

    new_acc = {
        'id': account_id,
        'name': name,
        'mt5_login': mt5_login,
        'mt5_password_enc': enc_pw,
        'mt5_server': mt5_server,
        'created_at': time.time(),
    }

    accounts_list.append(new_acc)
    user_blob['accounts'] = accounts_list
    if not user_blob.get('selected_account_id'):
        user_blob['selected_account_id'] = account_id

    all_accounts[username] = user_blob
    store.save_mt5_accounts(all_accounts)

    return jsonify({
        'success': True,
        'account': {
            'id': account_id,
            'name': name,
            'mt5_login': mt5_login,
            'mt5_server': mt5_server,
        }
    })


@app.route('/api/mt5/accounts/list', methods=['GET'])
@require_approved
def mt5_accounts_list():
    username = session.get('user_id')
    if not username:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    all_accounts = store.load_mt5_accounts()
    user_blob = all_accounts.get(username) or {}
    accounts_list = user_blob.get('accounts') or []
    selected_id = user_blob.get('selected_account_id')

    safe_accounts = [
        {
            'id': a.get('id'),
            'name': a.get('name'),
            'mt5_login': a.get('mt5_login'),
            'mt5_server': a.get('mt5_server'),
            'selected': a.get('id') == selected_id,
        }
        for a in accounts_list
        if a.get('id')
    ]

    return jsonify({
        'success': True,
        'selected_account_id': selected_id,
        'accounts': safe_accounts,
    })


@app.route('/api/mt5/accounts/select', methods=['POST'])
@require_approved
def mt5_accounts_select():
    data = request.json or {}
    account_id = (data.get('account_id') or '').strip()
    if not account_id:
        return jsonify({'success': False, 'error': 'account_id is required'}), 400

    username = session.get('user_id')
    if not username:
        return jsonify({'success': False, 'error': 'Authentication required'}), 401

    all_accounts = store.load_mt5_accounts()
    user_blob = all_accounts.get(username) or dict(MT5_ACCOUNTS_DEFAULT_SCHEMA)
    accounts_list = user_blob.get('accounts') or []

    if not any(a.get('id') == account_id for a in accounts_list):
        return jsonify({'success': False, 'error': 'Account not found'}), 404

    user_blob['selected_account_id'] = account_id
    all_accounts[username] = user_blob
    store.save_mt5_accounts(all_accounts)

    return jsonify({'success': True, 'selected_account_id': account_id})


# --- Auth endpoints ---

@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''
    email = (data.get('email') or '').strip()

    if not username or len(username) < 3:
        return jsonify({'success': False, 'error': 'Username must be at least 3 characters'}), 400
    if not password or len(password) < 6:
        return jsonify({'success': False, 'error': 'Password must be at least 6 characters'}), 400
    if not email:
        return jsonify({'success': False, 'error': 'Email is required'}), 400

    users = store.load_users()
    pending = store.load_pending_users()

    if username in users or username in pending:
        return jsonify({'success': False, 'error': 'Username already exists'}), 409

    pending[username] = {
        'username': username,
        'password_hash': security.hash_password(password),
        'email': email,
        'registered_at': time.time(),
        'status': 'pending',
        'role': 'user',
        'balance': 10000,
    }
    store.save_pending_users(pending)
    return jsonify({'success': True, 'message': 'Registration submitted. Awaiting admin approval.'})


@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    username = (data.get('username') or '').strip()
    password = data.get('password') or ''

    users = store.load_users()
    pending = store.load_pending_users()

    # Admin login by stored user
    if username in users:
        user = users[username]
        if security.verify_password(password, user['password_hash']):
            session.clear()
            session['user_id'] = username
            session['username'] = username
            session['role'] = user.get('role', 'user')
            session['status'] = user.get('status')
            return jsonify({'success': True, 'is_admin': session['role'] == 'admin'})

    # Pending accounts cannot login for trading, but return informative error
    if username in pending:
        return jsonify({'success': False, 'error': 'Account pending admin approval'}), 403

    return jsonify({'success': False, 'error': 'Invalid credentials'}), 401


@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({'success': True})


@app.route('/api/auth/me', methods=['GET'])
def me():
    if not session.get('user_id'):
        return jsonify({'success': False, 'error': 'Not logged in'}), 401
    return jsonify({'success': True, 'user': {
        'username': session.get('username'),
        'role': session.get('role'),
        'status': session.get('status'),
    }})


@app.route('/api/account', methods=['GET'])
@require_approved
def api_account():
    """Dashboard compatibility endpoint.

    Existing dashboard.html expects /api/account to return balance + equity.
    """
    return jsonify({
        'balance': account_balance,
        'equity': account_balance,
    })



# --- Admin endpoints ---
@app.route('/api/admin/pending', methods=['GET'])
@require_admin
def get_pending():
    pending = store.load_pending_users()
    return jsonify({'pending': list(pending.values())})


@app.route('/api/admin/approve', methods=['POST'])
@require_admin
def approve_user():
    data = request.json or {}
    username = (data.get('username') or '').strip()

    pending = store.load_pending_users()
    users = store.load_users()

    if username not in pending:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    user_data = pending.pop(username)
    user_data['status'] = 'approved'
    user_data['approved_at'] = time.time()
    user_data['balance'] = user_data.get('balance', 10000)
    users[username] = user_data

    store.save_pending_users(pending)
    store.save_users(users)
    return jsonify({'success': True})


@app.route('/api/admin/reject', methods=['POST'])
@require_admin
def reject_user():
    data = request.json or {}
    username = (data.get('username') or '').strip()

    pending = store.load_pending_users()
    if username not in pending:
        return jsonify({'success': False, 'error': 'User not found'}), 404

    pending.pop(username)
    store.save_pending_users(pending)
    return jsonify({'success': True})


@app.route('/api/admin/users', methods=['GET'])
@require_admin
def get_users():
    users = store.load_users()
    user_list = [
        {'username': u.get('username'), 'email': u.get('email', ''), 'status': u.get('status'), 'balance': u.get('balance', 0)}
        for u in users.values()
    ]
    return jsonify({'users': user_list})


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
    ============================================================

     TRADING SERVER - LIVE MODE

     WebSocket: ws://localhost:5000
     Dashboard: http://localhost:5000/dashboard

     Withdrawal Target: $3,000
     Keep Capital: $1,000

    ============================================================
    """)
    
    threading.Thread(target=market_loop, daemon=True).start()
    socketio.run(app, host='0.0.0.0', port=5000, debug=False)