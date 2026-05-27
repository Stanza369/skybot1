# trading_server.py - Web dashboard for Windows
from flask import Flask, jsonify, render_template_string
import threading
import time
import subprocess
import sys

app = Flask(__name__)

# Global variable to store latest prediction
latest_prediction = {"action": "WAIT", "confidence": 0, "buy_prob": 0, "sell_prob": 0, "hold_prob": 0}

def run_bot():
    """Run the AI bot in background"""
    global latest_prediction
    try:
        # Import bot module
        sys.path.append('C:\\Users\\SMART TECH HUB\\Desktop\\xauusd_scalper')
        from ai_trading_bot_final import AITradingBot
        
        bot = AITradingBot()
        if not bot.load():
            print("Training model first...")
            bot.train(years=3)
        
        print("Bot started! Making predictions...")
        
        while True:
            pred = bot.predict()
            if 'error' not in pred:
                latest_prediction = pred
                print(f"Prediction: {pred['action']} ({pred['confidence']:.0%})")
            time.sleep(30)
    except Exception as e:
        print(f"Bot error: {e}")

@app.route('/')
def dashboard():
    return render_template_string('''
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI Trading Bot Dashboard</title>
        <meta http-equiv="refresh" content="5">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            * { margin: 0; padding: 0; box-sizing: border-box; }
            body {
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            .container {
                max-width: 600px;
                margin: 0 auto;
            }
            .card {
                background: white;
                border-radius: 20px;
                padding: 30px;
                margin-bottom: 20px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 {
                color: #333;
                margin-bottom: 10px;
                display: flex;
                align-items: center;
                gap: 10px;
            }
            .status {
                font-size: 14px;
                color: #27ae60;
                background: #d4edda;
                padding: 4px 12px;
                border-radius: 20px;
            }
            .prediction {
                text-align: center;
                padding: 30px;
                border-radius: 15px;
                margin: 20px 0;
            }
            .prediction.BUY { background: linear-gradient(135deg, #27ae60, #1e8449); color: white; }
            .prediction.SELL { background: linear-gradient(135deg, #e74c3c, #c0392b); color: white; }
            .prediction.HOLD { background: linear-gradient(135deg, #f39c12, #e67e22); color: white; }
            .prediction.WAIT { background: #95a5a6; color: white; }
            .action {
                font-size: 48px;
                font-weight: bold;
                letter-spacing: 2px;
            }
            .confidence {
                font-size: 18px;
                margin-top: 10px;
                opacity: 0.9;
            }
            .prob-container {
                margin: 20px 0;
            }
            .prob-item {
                margin: 10px 0;
            }
            .prob-label {
                display: inline-block;
                width: 60px;
                font-weight: bold;
            }
            .prob-bar {
                display: inline-block;
                width: 70%;
                height: 30px;
                background: #ecf0f1;
                border-radius: 15px;
                overflow: hidden;
                vertical-align: middle;
            }
            .prob-fill {
                height: 100%;
                line-height: 30px;
                color: white;
                font-size: 12px;
                padding-left: 10px;
                transition: width 0.5s ease;
            }
            .buy-fill { background: #27ae60; }
            .sell-fill { background: #e74c3c; }
            .hold-fill { background: #f39c12; }
            .timestamp {
                text-align: center;
                color: #7f8c8d;
                margin-top: 20px;
                font-size: 12px;
            }
            .footer {
                text-align: center;
                color: white;
                font-size: 12px;
            }
            @keyframes pulse {
                0%, 100% { opacity: 1; }
                50% { opacity: 0.7; }
            }
            .live {
                animation: pulse 2s infinite;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="card">
                <h1>
                    🤖 AI Trading Bot
                    <span class="status live">● LIVE</span>
                </h1>
                <p>Real-time market analysis using Machine Learning</p>
                
                <div class="prediction {{ prediction.action }}">
                    <div class="action">{{ prediction.action }}</div>
                    <div class="confidence">Confidence: {{ "%.0f"|format(prediction.confidence*100) }}%</div>
                </div>
                
                <div class="prob-container">
                    <div class="prob-item">
                        <span class="prob-label">📈 BUY</span>
                        <div class="prob-bar">
                            <div class="prob-fill buy-fill" style="width: {{ prediction.buy_prob*100 }}%">
                                {{ "%.0f"|format(prediction.buy_prob*100) }}%
                            </div>
                        </div>
                    </div>
                    <div class="prob-item">
                        <span class="prob-label">⏸️ HOLD</span>
                        <div class="prob-bar">
                            <div class="prob-fill hold-fill" style="width: {{ prediction.hold_prob*100 }}%">
                                {{ "%.0f"|format(prediction.hold_prob*100) }}%
                            </div>
                        </div>
                    </div>
                    <div class="prob-item">
                        <span class="prob-label">📉 SELL</span>
                        <div class="prob-bar">
                            <div class="prob-fill sell-fill" style="width: {{ prediction.sell_prob*100 }}%">
                                {{ "%.0f"|format(prediction.sell_prob*100) }}%
                            </div>
                        </div>
                    </div>
                </div>
                
                <div class="timestamp">
                    Last update: {{ timestamp }}<br>
                    Refreshes every 5 seconds
                </div>
            </div>
            <div class="footer">
                🧠 Self-learning AI | Trained on 3+ years of gold data | Updates every 30 seconds
            </div>
        </div>
    </body>
    </html>
    ''', prediction=latest_prediction, timestamp=time.strftime("%Y-%m-%d %H:%M:%S"))

@app.route('/api/prediction')
def api_prediction():
    return jsonify(latest_prediction)

if __name__ == '__main__':
    # Start bot in background thread
    bot_thread = threading.Thread(target=run_bot, daemon=True)
    bot_thread.start()
    
    # Wait a moment for bot to initialize
    time.sleep(2)
    
    # Start web server
    print("\n" + "="*50)
    print("🌐 AI Trading Bot Dashboard")
    print("="*50)
    print("Dashboard running at: http://localhost:5000")
    print("Press Ctrl+C to stop")
    print("="*50 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)