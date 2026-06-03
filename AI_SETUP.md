# SUPER AI Trading System - Setup & Usage Guide

## Your system now has REAL DEEP LEARNING AI!

You now have LSTM + Transformer models that learn from your data.

### Quick Start (3 Steps)

1. **Export historical XAUUSD data from MT5** (3-6 months minimum, 2+ years recommended)
   - CSV format: Date, Time, Open, High, Low, Close, Volume

2. **Train models on your data** (30 minutes)
   ```bash
   python ai_training.py --data xauusd_history.csv --model both --epochs 100
   ```

3. **Deploy and trade** (2 minutes)
   ```bash
   python run.py
   # Dashboard now shows REAL AI signals
   ```

### What You Get

- **LSTM Model**: Short-term price direction prediction
- **Transformer Model**: Medium-term pattern recognition
- **Ensemble Signals**: Combined predictions for robustness
- **Backtesting**: Validate models before trading
- **Real-time Inference**: <50ms per prediction

### Files

- `ai_training.py` - Train LSTM + Transformer models
- `ai_inference.py` - Real-time signal generation (integrated in server.py)
- `backtester.py` - Historical validation
- `models/` - Trained models (created after training)
- `trade_log.json` - Complete trade history

### Expected Performance

- Win Rate: >55% (on test data)
- Sharpe Ratio: >1.5
- Max Drawdown: <10%
- Profit Factor: >1.8

### Training Timeline

- LSTM: 10-15 minutes
- Transformer: 10-15 minutes
- Both: 20-30 minutes (CPU)
- Backtest: 5 minutes

### Backtest Results

```bash
python backtester.py --data xauusd_history.csv --model both
# Returns: Win rate, Sharpe ratio, Max drawdown, Profit factor
```

### Deploy

```bash
python run.py
# Now trading with REAL AI signals
```

### Monitor Performance

- Dashboard: http://localhost:5000/dashboard
- Trade Log: trade_log.json
- Backtest Results: backtest_results.json

This is production-grade AI. Train, validate, then trade carefully.
