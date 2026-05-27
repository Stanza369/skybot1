# XAUUSD AI Scalping Bot (Standalone)

This is a **standalone** Python project (separate from the NPATS PHP app).

## Features
- MT5 integration (rates + historical + live tick)
- Feature engineering (ta)
- XGBoost + optional LSTM ensemble
- Risk management (position sizing + daily loss guard)
- Telegram alerts
- Backtester scaffold
- FastAPI dashboard (optional)

## Setup
1) Install MT5 and ensure `MetaTrader5` Python package can connect.
2) Create virtual env (recommended) and install deps:

```bash
pip install -r requirements.txt
```

3) Create folders:
```bash
mkdir models data
```

4) Copy env:
```bash
copy .env.example .env
```
Edit `.env` with your MT5 + Telegram values.

## Run
```bash
python main.py
```

## Dashboard (optional)
```bash
uvicorn dashboard:app --reload --port 8000
```

## Important note on “90% accuracy”
No production trading bot can guarantee 90% accuracy without rigorous dataset-specific training and evaluation. This project includes a training + backtesting pipeline; you should validate using demo data and improve with proper labeling, walk-forward validation, and broker execution assumptions.

