from __future__ import annotations

import json
import os
import threading
import time
from typing import Any, Dict, List, Optional


class ChatLearningStorage:
    """Very small JSON-file persistence layer.

    - chat conversations: JSONL (append-only)
    - preferences: JSON
    - reinforcement learning state (weights + outcomes): JSON

    This is intentionally lightweight to fit the current repo.
    """

    def __init__(
        self,
        *,
        base_dir: str,
        conversations_file: str = "chat_conversations.jsonl",
        preferences_file: str = "chat_preferences.json",
        rl_state_file: str = "chat_rl_state.json",
    ) -> None:
        self.base_dir = base_dir
        self.conversations_path = os.path.join(base_dir, conversations_file)
        self.preferences_path = os.path.join(base_dir, preferences_file)
        self.rl_state_path = os.path.join(base_dir, rl_state_file)

        os.makedirs(self.base_dir, exist_ok=True)

        self._lock = threading.Lock()

        self._ensure_files()

    def _ensure_files(self) -> None:
        with self._lock:
            if not os.path.exists(self.conversations_path):
                # jsonl: create empty file
                with open(self.conversations_path, "w", encoding="utf-8") as f:
                    pass
            if not os.path.exists(self.preferences_path):
                with open(self.preferences_path, "w", encoding="utf-8") as f:
                    json.dump({}, f)
            if not os.path.exists(self.rl_state_path):
                with open(self.rl_state_path, "w", encoding="utf-8") as f:
                    json.dump(
                        {
                            "strategy_weights": None,
                            "trade_outcomes": [],
                        },
                        f,
                    )

    # -------------------- Conversations (JSONL) --------------------

    def append_conversation(self, row: Dict[str, Any]) -> None:
        with self._lock:
            with open(self.conversations_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(row, ensure_ascii=False) + "\n")

    def load_conversations(self, *, user_id: Optional[str] = None, limit_per_user: int = 1000) -> Dict[str, List[Dict[str, Any]]]:
        """Load conversations into memory.

        Returns: {user_id: [rows...]}
        """
        by_user: Dict[str, List[Dict[str, Any]]] = {}

        if not os.path.exists(self.conversations_path):
            return by_user

        with self._lock:
            with open(self.conversations_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        row = json.loads(line)
                    except Exception:
                        continue

                    uid = str(row.get("user_id") or "anonymous")
                    if user_id is not None and uid != str(user_id):
                        continue

                    by_user.setdefault(uid, []).append(row)

        # cap per user
        for uid, rows in list(by_user.items()):
            if len(rows) > limit_per_user:
                by_user[uid] = rows[-limit_per_user:]

        return by_user

    # -------------------- Preferences (JSON) --------------------

    def load_preferences(self) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            try:
                with open(self.preferences_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}

    def upsert_preferences(self, user_id: str, patch: Dict[str, Any]) -> None:
        with self._lock:
            prefs = self.load_preferences()
            prefs.setdefault(str(user_id), {})
            prefs[str(user_id)].update(patch)
            with open(self.preferences_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f)

    # -------------------- RL State (JSON) --------------------

    def load_rl_state(self) -> Dict[str, Any]:
        with self._lock:
            try:
                with open(self.rl_state_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"strategy_weights": None, "trade_outcomes": []}

    def save_rl_state(self, *, strategy_weights: Dict[str, float], trade_outcomes: List[Dict[str, Any]], max_outcomes: int = 5000) -> None:
        with self._lock:
            outcomes = trade_outcomes[-max_outcomes:]
            payload = {"strategy_weights": strategy_weights, "trade_outcomes": outcomes, "saved_at": time.time()}
            with open(self.rl_state_path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False)

