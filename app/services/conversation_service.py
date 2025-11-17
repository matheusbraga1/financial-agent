import os
import sqlite3
import threading
import time
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta


class ConversationService:
    def __init__(self, db_path: Optional[str] = None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        data_dir = os.path.join(base_dir, "app_data")
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(data_dir, "chat_history.db")
        self._lock = threading.Lock()
        self.retention_days = int(os.getenv("CHAT_HISTORY_RETENTION_DAYS", "90"))
        self._purge_interval_sec = int(os.getenv("CHAT_HISTORY_PURGE_INTERVAL_SEC", "3600"))
        self._last_purge = 0.0
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path, check_same_thread=False, timeout=5.0)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=5000;")
            conn.execute("PRAGMA foreign_keys=ON;")
        except Exception:
            pass
        return conn

    def _init_db(self):
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    created_at TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT,
                    role TEXT,
                    content TEXT,
                    answer TEXT,
                    sources_json TEXT,
                    model_used TEXT,
                    confidence REAL,
                    timestamp TEXT
                )
                """
            )
            cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_time ON messages(session_id, timestamp);")
            conn.commit()

    def _purge_if_needed(self, conn: sqlite3.Connection):
        if self.retention_days <= 0:
            return
        now = time.time()
        if (now - self._last_purge) < self._purge_interval_sec:
            return
        cutoff = (datetime.utcnow() - timedelta(days=self.retention_days)).isoformat()
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff,))
            conn.commit()
        except Exception:
            pass
        finally:
            self._last_purge = now

    def ensure_session(self, session_id: str, user_id: Optional[str] = None) -> None:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM conversations WHERE session_id=?", (session_id,))
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO conversations(session_id, user_id, created_at) VALUES(?,?,?)",
                    (session_id, user_id, datetime.utcnow().isoformat()),
                )
                conn.commit()

    def get_conversation(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT session_id, user_id, created_at FROM conversations WHERE session_id=?", (session_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def add_user_message(self, session_id: str, content: str) -> None:
        with self._lock, self._connect() as conn:
            self._purge_if_needed(conn)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO messages(session_id, role, content, timestamp) VALUES(?,?,?,?)",
                (session_id, "user", content, datetime.utcnow().isoformat()),
            )
            conn.commit()

    def add_assistant_message(
        self,
        session_id: str,
        answer: str,
        sources_json: Optional[str],
        model_used: Optional[str],
        confidence: Optional[float],
    ) -> None:
        with self._lock, self._connect() as conn:
            self._purge_if_needed(conn)
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO messages(session_id, role, answer, sources_json, model_used, confidence, timestamp) "
                "VALUES(?,?,?,?,?,?,?)",
                (
                    session_id,
                    "assistant",
                    answer,
                    sources_json,
                    model_used,
                    confidence,
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()

    def get_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT role, content, answer, sources_json, model_used, confidence, timestamp "
                "FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
