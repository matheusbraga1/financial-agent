import os
import sqlite3
import threading
import logging
from typing import Optional, Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)

class SQLiteUserRepository:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
            data_dir = os.path.join(base_dir, "app_data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "users.db")
        
        self.db_path = db_path
        self._lock = threading.Lock()
        
        self._init_db()
        
        logger.info(f"SQLiteUserRepository inicializado: {db_path}")
    
    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            timeout=10.0
        )
        conn.row_factory = sqlite3.Row
        
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            conn.execute("PRAGMA busy_timeout=10000;")
            conn.execute("PRAGMA foreign_keys=ON;")
        except Exception as e:
            logger.warning(f"Erro ao configurar PRAGMAs: {e}")
        
        return conn
    
    def _init_db(self) -> None:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    email TEXT UNIQUE NOT NULL,
                    hashed_password TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1,
                    is_admin INTEGER DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_username ON users(username);")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email ON users(email);")
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS refresh_tokens (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    token TEXT UNIQUE NOT NULL,
                    expires_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                )
            """)
            
            cur.execute("CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user ON refresh_tokens(user_id);")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_refresh_tokens_token ON refresh_tokens(token);")
            
            conn.commit()
            logger.info("User database schema inicializado")
    
    def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        is_active: bool = True,
        is_admin: bool = False,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            
            cur.execute("SELECT id FROM users WHERE username=?", (username,))
            if cur.fetchone():
                raise ValueError(f"Username '{username}' já existe")
            
            cur.execute("SELECT id FROM users WHERE email=?", (email,))
            if cur.fetchone():
                raise ValueError(f"Email '{email}' já existe")
            
            cur.execute(
                """
                INSERT INTO users(username, email, hashed_password, is_active, is_admin, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    email,
                    hashed_password,
                    1 if is_active else 0,
                    1 if is_admin else 0,
                    datetime.utcnow().isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            
            conn.commit()
            user_id = cur.lastrowid
            
            logger.info(f"Usuário criado: id={user_id}, username={username}")
            
            return user_id
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, username, email, hashed_password, is_active, is_admin, created_at, updated_at
                FROM users WHERE id=?
                """,
                (user_id,)
            )
            row = cur.fetchone()
            
            if not row:
                return None
            
            return {
                "id": row["id"],
                "username": row["username"],
                "email": row["email"],
                "hashed_password": row["hashed_password"],
                "is_active": bool(row["is_active"]),
                "is_admin": bool(row["is_admin"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, username, email, hashed_password, is_active, is_admin, created_at, updated_at
                FROM users WHERE username=?
                """,
                (username,)
            )
            row = cur.fetchone()
            
            if not row:
                return None
            
            return {
                "id": row["id"],
                "username": row["username"],
                "email": row["email"],
                "hashed_password": row["hashed_password"],
                "is_active": bool(row["is_active"]),
                "is_admin": bool(row["is_admin"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, username, email, hashed_password, is_active, is_admin, created_at, updated_at
                FROM users WHERE email=?
                """,
                (email,)
            )
            row = cur.fetchone()
            
            if not row:
                return None
            
            return {
                "id": row["id"],
                "username": row["username"],
                "email": row["email"],
                "hashed_password": row["hashed_password"],
                "is_active": bool(row["is_active"]),
                "is_admin": bool(row["is_admin"]),
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            }
    
    def update_user(self, user_id: int, **fields) -> bool:
        if not fields:
            return False
        
        allowed_fields = {"username", "email", "hashed_password", "is_active", "is_admin"}
        update_fields = {k: v for k, v in fields.items() if k in allowed_fields}
        
        if not update_fields:
            return False
        
        if "is_active" in update_fields:
            update_fields["is_active"] = 1 if update_fields["is_active"] else 0
        if "is_admin" in update_fields:
            update_fields["is_admin"] = 1 if update_fields["is_admin"] else 0
        
        update_fields["updated_at"] = datetime.utcnow().isoformat()
        
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            
            set_clause = ", ".join(f"{field}=?" for field in update_fields.keys())
            values = list(update_fields.values()) + [user_id]
            
            cur.execute(
                f"UPDATE users SET {set_clause} WHERE id=?",
                values
            )
            
            conn.commit()
            updated = cur.rowcount > 0
            
            if updated:
                logger.info(f"Usuário atualizado: id={user_id}, fields={list(update_fields.keys())}")
            
            return updated
    
    def delete_user(self, user_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM users WHERE id=?", (user_id,))
            conn.commit()
            deleted = cur.rowcount > 0
            
            if deleted:
                logger.info(f"Usuário deletado: id={user_id}")
            
            return deleted
    
    def store_refresh_token(
        self,
        user_id: int,
        token: str,
        expires_at: datetime,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO refresh_tokens(user_id, token, expires_at, created_at)
                VALUES(?, ?, ?, ?)
                """,
                (
                    user_id,
                    token,
                    expires_at.isoformat(),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            
            logger.debug(f"Refresh token armazenado para user_id={user_id}")
            
            return cur.lastrowid
    
    def get_refresh_token(self, token: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT id, user_id, token, expires_at, created_at
                FROM refresh_tokens WHERE token=?
                """,
                (token,)
            )
            row = cur.fetchone()
            
            if not row:
                return None
            
            return {
                "id": row["id"],
                "user_id": row["user_id"],
                "token": row["token"],
                "expires_at": row["expires_at"],
                "created_at": row["created_at"],
            }
    
    def delete_refresh_token(self, token: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM refresh_tokens WHERE token=?", (token,))
            conn.commit()
            
            return cur.rowcount > 0
    
    def delete_expired_tokens(self) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            now = datetime.utcnow().isoformat()
            cur.execute("DELETE FROM refresh_tokens WHERE expires_at < ?", (now,))
            conn.commit()
            deleted = cur.rowcount
            
            if deleted > 0:
                logger.info(f"Removed {deleted} expired refresh tokens")
            
            return deleted

user_repository = SQLiteUserRepository()