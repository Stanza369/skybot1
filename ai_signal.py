from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from mt5_service import MT5Service

logger = logging.getLogger(__name__)


def _ensure_df(ohlc: List[Dict[str, Any]]) -> pd.DataFrame:
    if not ohlc:
        return pd.DataFrame()
    df = pd.DataFrame(ohlc)
    if 'time' in df.columns:
        # LightweightCharts expects unix seconds; for indicators any monotonic value is fine.
        df['time'] = pd.to_numeric(df['time'], errors='coerce')
    return df


def compute_votes(df: pd.DataFrame) -> Dict[str, Any]:
    """Deterministic, real indicator-based votes (no front-end simulations).

    This is still a lightweight implementation. It removes candle-proxy simulations from the UI.
    You can later replace the internals with your LSTM/XGBoost/RL models.
    """

    if df is None or df.empty or len(df) < 60:
        return {
            'vote': 'HOLD',
            'conf': 0.5,
            'meta': 'Not enough candles for indicators',
            'votes': [
                {'key': 'trend', 'vote': 'HOLD', 'conf': 0.5, 'meta': 'Insufficient data'},
                {'key': 'liquidity', 'vote': 'HOLD', 'conf': 0.5, 'meta': 'Insufficient data'},
                {'key': 'volatility', 'vote': 'HOLD', 'conf': 0.5, 'meta': 'Insufficient data'},
                {'key': 'sentiment', 'vote': 'HOLD', 'conf': 0.5, 'meta': 'Insufficient data'},
            ]
        }

    # Indicators
    close = df['close'].astype(float)

    ema_fast = close.ewm(span=20, adjust=False).mean()
    ema_slow = close.ewm(span=50, adjust=False).mean()

    # RSI(14)
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1/14, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/14, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, 1e-9)
    rsi = 100 - (100 / (1 + rs))

    # ATR(14) proxy
    high = df['high'].astype(float)
    low = df['low'].astype(float)
    prev_close = close.shift(1)
    tr = pd.concat([
        (high - low),
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/14, adjust=False).mean()

    last = df.iloc[-1]
    last_rsi = float(rsi.iloc[-1])
    last_atr = float(atr.iloc[-1])

    trend_up = float(ema_fast.iloc[-1] - ema_slow.iloc[-1])
    trend_vote = 'BUY' if trend_up > 0 else 'SELL'
    trend_conf = min(0.95, max(0.1, abs(trend_up) / (close.iloc[-1] * 0.002)))

    # Liquidity proxy: RSI extremes act like “order flow pressure” proxy
    if last_rsi > 60:
        liq_vote = 'BUY'
        liq_conf = min(0.95, (last_rsi - 60) / 40)
    elif last_rsi < 40:
        liq_vote = 'SELL'
        liq_conf = min(0.95, (40 - last_rsi) / 40)
    else:
        liq_vote = 'HOLD'
        liq_conf = 0.55

    # Volatility regime: if ATR is high relative to price -> HOLD
    atr_pct = last_atr / (float(last['close']) or 1.0)
    if atr_pct > 0.008:
        vol_vote = 'HOLD'
        vol_conf = 0.65
    else:
        vol_vote = trend_vote if trend_vote in ('BUY', 'SELL') else 'HOLD'
        vol_conf = min(0.9, 0.55 + (0.008 - atr_pct) / 0.008 * 0.35)

    # Sentiment: last candle direction
    prev = df.iloc[-2]
    last_dir = 1 if float(last['close']) >= float(last['open']) else -1
    prev_dir = 1 if float(prev['close']) >= float(prev['open']) else -1
    bias = (last_dir + prev_dir) / 2
    if bias > 0.2:
        sent_vote = 'BUY'
    elif bias < -0.2:
        sent_vote = 'SELL'
    else:
        sent_vote = 'HOLD'

    sent_conf = min(0.9, abs(bias) + 0.4)

    votes = [
        {'key': 'trend', 'vote': trend_vote, 'conf': float(trend_conf), 'meta': f'EMA20/EMA50 & RSI {last_rsi:.1f}'},
        {'key': 'liquidity', 'vote': liq_vote, 'conf': float(liq_conf), 'meta': f'RSI pressure {last_rsi:.1f}'},
        {'key': 'volatility', 'vote': vol_vote, 'conf': float(vol_conf), 'meta': f'ATR% {atr_pct*100:.3f}% (regime)'},
        {'key': 'sentiment', 'vote': sent_vote, 'conf': float(sent_conf), 'meta': 'Recent candle direction bias'},
    ]

    # Consensus: majority excluding HOLD unless all HOLD
    buy_count = sum(1 for v in votes if v['vote'] == 'BUY')
    sell_count = sum(1 for v in votes if v['vote'] == 'SELL')

    if buy_count > sell_count:
        final_vote = 'BUY'
    elif sell_count > buy_count:
        final_vote = 'SELL'
    else:
        # if tie -> HOLD
        final_vote = 'HOLD'

    contributing = [v for v in votes if v['vote'] == final_vote] or votes
    final_conf = sum(v['conf'] for v in contributing) / max(1, len(contributing))

    return {
        'vote': final_vote,
        'conf': float(final_conf),
        'meta': 'Indicator-based backend AI signal (real, no UI simulations)',
        'votes': votes
    }


def build_signal_payload(df: pd.DataFrame) -> Dict[str, Any]:
    return compute_votes(df)

