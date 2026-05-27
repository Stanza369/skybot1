from fastapi import FastAPI, WebSocket
from fastapi.responses import HTMLResponse
import asyncio

app = FastAPI()

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
  <title>XAUUSD AI Scalping Dashboard</title>
  <style>
    body { font-family: Arial; margin: 20px; background: #1e1e1e; color: white; }
    .grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; }
    .card { background: #2d2d2d; padding: 15px; border-radius: 10px; }
    .signal-buy { color: #00ff00; }
    .signal-sell { color: #ff0000; }
    .signal-neutral { color: #ffff00; }
  </style>
</head>
<body>
  <h1>🤖 XAUUSD AI Scalping Bot</h1>
  <div class="grid">
    <div class="card">
      <h3>Live Price & Signal</h3>
      <div id="price">Loading...</div>
      <div id="signal" class="signal-neutral">NEUTRAL</div>
    </div>
    <div class="card">
      <h3>AI Prediction</h3>
      <div id="prediction">Loading...</div>
    </div>
    <div class="card">
      <h3>Market Conditions</h3>
      <div id="conditions">Loading...</div>
    </div>
    <div class="card">
      <h3>Performance</h3>
      <div id="performance">Loading...</div>
    </div>
  </div>

  <script>
    var ws = new WebSocket("ws://localhost:8000/ws");
    ws.onmessage = function(event) {
      var data = JSON.parse(event.data);
      document.getElementById('price').innerHTML = `Price: $${data.price}`;
      document.getElementById('signal').innerHTML = data.signal;
      document.getElementById('signal').className = `signal-${data.signal.toLowerCase()}`;
      document.getElementById('prediction').innerHTML = `Probability: ${data.probability}%<br>Confidence: ${data.confidence}%`;
      var conditions = '';
      for (var key in data.conditions) {
        conditions += `${key}: ${data.conditions[key] ? '✅' : '❌'}<br>`;
      }
      document.getElementById('conditions').innerHTML = conditions;
    };
  </script>
</body>
</html>
"""


@app.get("/")
async def get_dashboard():
    return HTMLResponse(HTML_TEMPLATE)


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    while True:
        data = {
            "price": 0,
            "signal": "NEUTRAL",
            "probability": 0,
            "confidence": 0,
            "conditions": {
                "Momentum Burst": False,
                "Volume Spike": False,
                "Liquidity Sweep": False,
                "Inst. Flow": False,
            },
        }
        await websocket.send_json(data)
        await asyncio.sleep(1)

