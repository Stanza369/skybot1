from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

try:
    import asyncpg  # type: ignore
except Exception:  # pragma: no cover
    asyncpg = None


class ProductionDatabase:

    """Production-ready PostgreSQL database (asyncpg)."""

    def __init__(self) -> None:
        self.pool: Optional[asyncpg.Pool] = None
        self.is_connected: bool = False

    async def connect(self) -> bool:
        if asyncpg is None:
            self.is_connected = False
            return False

        import os

        try:
            self.pool = await asyncpg.create_pool(
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", "5432")),

                user=os.getenv("DB_USER", "trader"),
                password=os.getenv("DB_PASSWORD", "secure_password"),
                database=os.getenv("DB_NAME", "trading_db"),
                min_size=2,
                max_size=10,
                command_timeout=60,
            )
            await self._init_schema()
            self.is_connected = True
            return True
        except Exception:
            self.is_connected = False
            return False

    async def _init_schema(self) -> None:
        assert self.pool is not None

        # Users
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                balance DECIMAL(15,2) DEFAULT 10000.00,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP,
                is_active BOOLEAN DEFAULT TRUE,
                settings JSONB DEFAULT '{}'
            );
            """
        )

        # Trades
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS trades (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id),
                order_id VARCHAR(64) UNIQUE,
                symbol VARCHAR(16) NOT NULL,
                action VARCHAR(8) NOT NULL,
                volume DECIMAL(18,6) NOT NULL,
                entry_price DECIMAL(18,6) NOT NULL,
                exit_price DECIMAL(18,6),
                stop_loss DECIMAL(18,6),
                take_profit DECIMAL(18,6),
                pnl DECIMAL(18,6),
                status VARCHAR(20) DEFAULT 'OPEN',
                open_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                close_time TIMESTAMP,
                strategy VARCHAR(64),
                confidence DECIMAL(6,4),
                metadata JSONB DEFAULT '{}'
            );
            """
        )

        # Indexes
        await self.pool.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_trades_user_id ON trades(user_id);
            CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
            CREATE INDEX IF NOT EXISTS idx_trades_open_time ON trades(open_time);
            CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
            """
        )

        # AI Predictions
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS ai_predictions (
                id SERIAL PRIMARY KEY,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol VARCHAR(16),
                prediction VARCHAR(16),
                confidence DECIMAL(6,4),
                actual_outcome VARCHAR(16),
                was_correct BOOLEAN,
                models_used JSONB DEFAULT '{}'
            );
            """
        )

        # System logs
        await self.pool.execute(
            """
            CREATE TABLE IF NOT EXISTS system_logs (
                id SERIAL PRIMARY KEY,
                level VARCHAR(20),
                module VARCHAR(64),
                message TEXT,
                details JSONB DEFAULT '{}',
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            """
        )

    async def log_system_event(
        self,
        *,
        level: str,
        module: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.pool:
            return

        await self.pool.execute(
            """
            INSERT INTO system_logs (level, module, message, details)
            VALUES ($1, $2, $3, $4)
            """,
            level,
            module,
            message,
            json.dumps(details or {}),
        )

    async def save_trade(self, trade: Dict[str, Any]) -> Optional[int]:
        """Insert a trade row. Returns inserted id if possible."""

        if not self.pool:
            return None

        # Required fields (we best-effort defaults to keep it robust)
        user_id = trade.get("user_id")
        order_id = trade.get("order_id")
        symbol = trade.get("symbol")
        action = trade.get("action")
        volume = trade.get("volume", 0.0)
        entry_price = trade.get("entry_price", 0.0)

        if symbol is None or action is None or order_id is None:
            return None

        row = await self.pool.fetchrow(
            """
            INSERT INTO trades (
                user_id, order_id, symbol, action, volume, entry_price,
                stop_loss, take_profit, status, strategy, confidence, metadata
            ) VALUES (
                $1, $2, $3, $4, $5, $6,
                $7, $8, $9, $10, $11, $12
            )
            RETURNING id
            """,
            user_id,
            order_id,
            symbol,
            action,
            volume,
            entry_price,
            trade.get("stop_loss"),
            trade.get("take_profit"),
            trade.get("status", "OPEN"),
            trade.get("strategy"),
            trade.get("confidence"),
            json.dumps(trade.get("metadata") or {}),
        )

        return int(row["id"]) if row else None

    async def close_trade(self, *, order_id: str, exit_price: float, pnl: float) -> None:
        if not self.pool:
            return

        await self.pool.execute(
            """
            UPDATE trades
            SET exit_price = $1,
                pnl = $2,
                status = 'CLOSED',
                close_time = CURRENT_TIMESTAMP
            WHERE order_id = $3
            """,
            exit_price,
            pnl,
            order_id,
        )

    async def get_user_trades(self, *, user_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.pool:
            return []

        rows = await self.pool.fetch(
            """
            SELECT * FROM trades
            WHERE user_id = $1
            ORDER BY open_time DESC
            LIMIT $2
            """,
            user_id,
            limit,
        )
        return [dict(r) for r in rows]

