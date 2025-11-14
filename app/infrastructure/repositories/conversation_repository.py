import os
import sqlite3
import threading
import time
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class SQLiteConversationRepository:
    def __init__(self, db_path: Optional[str] = None):
        if db_path is None:
            base_dir = os.path.abspath(
                os.path.join(os.path.dirname(__file__), "..", "..", "..")
            )
            data_dir = os.path.join(base_dir, "app_data")
            os.makedirs(data_dir, exist_ok=True)
            db_path = os.path.join(data_dir, "chat_history.db")
        
        self.db_path = db_path
        self._lock = threading.Lock()
        
        self.retention_days = int(os.getenv("CHAT_HISTORY_RETENTION_DAYS", "90"))
        self._purge_interval_sec = int(os.getenv("CHAT_HISTORY_PURGE_INTERVAL_SEC", "3600"))
        self._last_purge = 0.0
        
        self._init_db()
        
        logger.info(f"SQLiteConversationRepository inicializado: {db_path}")
    
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
                CREATE TABLE IF NOT EXISTS conversations (
                    session_id TEXT PRIMARY KEY,
                    user_id TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                )
            """)
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                    content TEXT,
                    answer TEXT,
                    sources_json TEXT,
                    model_used TEXT,
                    confidence REAL CHECK(confidence >= 0 AND confidence <= 1),
                    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(session_id) REFERENCES conversations(session_id) ON DELETE CASCADE
                )
            """)
            
            cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_messages_session_time ON messages(session_id, timestamp);")
            
            cur.execute("""
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    message_id INTEGER NOT NULL,
                    rating TEXT NOT NULL,
                    comment TEXT,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    FOREIGN KEY(session_id) REFERENCES conversations(session_id) ON DELETE CASCADE,
                    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
                )
            """)
            
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_message ON feedback(message_id);")
            cur.execute("CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);")
            
            conn.commit()
            logger.info("Database schema inicializado")
    
    def _purge_if_needed(self, conn: sqlite3.Connection) -> None:
        if self.retention_days <= 0:
            return
        
        now = time.time()
        if (now - self._last_purge) < self._purge_interval_sec:
            return
        
        cutoff = (datetime.utcnow() - timedelta(days=self.retention_days)).isoformat()
        
        try:
            cur = conn.cursor()
            cur.execute("DELETE FROM messages WHERE timestamp < ?", (cutoff,))
            deleted_count = cur.rowcount
            conn.commit()
            
            if deleted_count > 0:
                logger.info(f"Purged {deleted_count} mensagens antigas")
        except Exception as e:
            logger.error(f"Erro durante purge: {e}")
        finally:
            self._last_purge = now
    
    def create_session(self, session_id: str, user_id: Optional[str] = None) -> None:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM conversations WHERE session_id=?", (session_id,))
            
            if cur.fetchone() is None:
                cur.execute(
                    "INSERT INTO conversations(session_id, user_id, created_at) VALUES(?,?,?)",
                    (session_id, user_id, datetime.utcnow().isoformat()),
                )
                conn.commit()
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT session_id, user_id, created_at FROM conversations WHERE session_id=?",
                (session_id,)
            )
            row = cur.fetchone()
            return dict(row) if row else None
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        answer: Optional[str] = None,
        sources: Optional[str] = None,
        model: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> int:
        with self._lock, self._connect() as conn:
            self._purge_if_needed(conn)
            cur = conn.cursor()
            
            if role == "user":
                cur.execute(
                    "INSERT INTO messages(session_id, role, content, timestamp) VALUES(?,?,?,?)",
                    (session_id, "user", content, datetime.utcnow().isoformat()),
                )
            else:
                cur.execute(
                    "INSERT INTO messages(session_id, role, answer, sources_json, model_used, confidence, timestamp) "
                    "VALUES(?,?,?,?,?,?,?)",
                    (
                        session_id,
                        "assistant",
                        answer,
                        sources,
                        model,
                        confidence,
                        datetime.utcnow().isoformat(),
                    ),
                )
            
            conn.commit()
            return cur.lastrowid
    
    def get_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, role, content, answer, sources_json, model_used, confidence, timestamp "
                "FROM messages WHERE session_id=? ORDER BY id ASC LIMIT ?",
                (session_id, limit),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    
    def get_message_by_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "SELECT id, session_id, role, content, answer, sources_json, model_used, confidence, timestamp "
                "FROM messages WHERE id=?",
                (message_id,),
            )
            row = cur.fetchone()
            return dict(row) if row else None
    
    def add_feedback(
        self,
        session_id: str,
        message_id: int,
        rating: str,
        comment: Optional[str] = None,
    ) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO feedback(session_id, message_id, rating, comment, created_at) VALUES(?,?,?,?,?)",
                (session_id, message_id, rating, comment, datetime.utcnow().isoformat()),
            )
            conn.commit()
            return cur.lastrowid
    
    def get_user_sessions(self, user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                    c.session_id,
                    c.user_id,
                    c.created_at,
                    COUNT(m.id) as message_count,
                    (
                        SELECT COALESCE(content, answer, 'Nova conversa')
                        FROM messages
                        WHERE session_id = c.session_id
                        ORDER BY timestamp DESC
                        LIMIT 1
                    ) as last_message
                FROM conversations c
                LEFT JOIN messages m ON c.session_id = m.session_id
                WHERE c.user_id = ? AND c.user_id IS NOT NULL AND c.user_id != ''
                GROUP BY c.session_id, c.user_id, c.created_at
                ORDER BY c.created_at DESC
                LIMIT ?
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()
            return [dict(r) for r in rows]
    
    def delete_session(self, session_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM conversations WHERE session_id=?", (session_id,))
            deleted = cur.rowcount > 0
            conn.commit()
            
            if deleted:
                logger.info(f"Sessão deletada: {session_id}")
            
            return deleted

conversation_repository = SQLiteConversationRepository()