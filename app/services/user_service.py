import os
import sqlite3
import threading
from typing import Optional, Dict, Any
from datetime import datetime


class UserService:
    def __init__(self, db_path: Optional[str] = None):
        base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        data_dir = os.path.join(base_dir, "app_data")
        os.makedirs(data_dir, exist_ok=True)
        self.db_path = db_path or os.path.join(data_dir, "auth.db")
        self._lock = threading.RLock()  # RLock permite reentrância (mesmo thread pode adquirir múltiplas vezes)
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
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    email TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    name TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    is_admin INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);")

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS token_blacklist (
                    jti TEXT PRIMARY KEY,
                    expires_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    # Users
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE email=?", (email.lower(),))
            row = cur.fetchone()
            return dict(row) if row else None

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT * FROM users WHERE id=?", (user_id,))
            row = cur.fetchone()
            return dict(row) if row else None

    def create_user(self, email: str, password_hash: str, name: Optional[str]) -> Dict[str, Any]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            now = datetime.utcnow().isoformat()
            cur.execute(
                "INSERT INTO users(email, password_hash, name, created_at) VALUES(?,?,?,?)",
                (email.lower(), password_hash, name, now)
            )
            user_id = cur.lastrowid
            conn.commit()
            return self.get_user_by_id(user_id)

    # Token blacklist
    def revoke_token(self, jti: str, expires_at: datetime) -> None:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO token_blacklist(jti, expires_at) VALUES(?,?)",
                (jti, expires_at.isoformat())
            )
            conn.commit()

    def is_token_revoked(self, jti: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM token_blacklist WHERE jti=?", (jti,))
            return cur.fetchone() is not None

