import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from psycopg.types.json import Json
from contextlib import contextmanager
import uuid

logger = logging.getLogger(__name__)

class PostgresConversationRepository:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "financial_agent",
        user: str = "postgres",
        password: str = "",
        min_connections: int = 2,
        max_connections: int = 10,
        retention_days: int = 90,
    ):
        self.connection_pool = None
        self.retention_days = retention_days

        try:
            conninfo = f"host={host} port={port} dbname={database} user={user} password={password} connect_timeout=10"

            self.connection_pool = ConnectionPool(
                conninfo=conninfo,
                min_size=min_connections,
                max_size=max_connections,
                kwargs={"row_factory": dict_row},
            )

            logger.info(
                f"PostgresConversationRepository initialized: {host}:{port}/{database}"
            )

        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    def __del__(self):
        if self.connection_pool:
            self.connection_pool.close()
            logger.info("Connection pool closed")

    @contextmanager
    def _get_connection(self):
        with self.connection_pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database error: {e}")
                raise

    def create_session(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        title: Optional[str] = None,
    ) -> str:
        if session_id is None:
            session_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # UPSERT pattern - single query instead of SELECT + INSERT/UPDATE
                cur.execute(
                    """
                    INSERT INTO conversations (session_id, user_id, title, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (session_id) DO UPDATE
                    SET user_id = COALESCE(conversations.user_id, EXCLUDED.user_id),
                        updated_at = EXCLUDED.updated_at
                    WHERE conversations.user_id IS NULL AND EXCLUDED.user_id IS NOT NULL
                    RETURNING (xmax = 0) as inserted
                    """,
                    (session_id, user_id, title, datetime.utcnow(), datetime.utcnow()),
                )
                result = cur.fetchone()

                if result and result["inserted"]:
                    logger.info(f"Session created: {session_id}")
                elif result:
                    logger.info(f"Session {session_id} migrated to user_id={user_id}")

                return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT session_id, user_id, title, created_at, updated_at
                    FROM conversations
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                return dict(row)

    def add_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        answer: Optional[str] = None,
        sources: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> int:
        self.create_session(session_id)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                sources_json = Json(sources) if sources else None

                if role == "user":
                    cur.execute(
                        """
                        INSERT INTO messages (session_id, role, content, timestamp)
                        VALUES (%s, %s::message_role, %s, %s)
                        RETURNING id
                        """,
                        (session_id, role, content, datetime.utcnow()),
                    )
                else:
                    cur.execute(
                        """
                        INSERT INTO messages (session_id, role, answer, sources_json, model_used, confidence, timestamp)
                        VALUES (%s, %s::message_role, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (session_id, role, answer, sources_json, model, confidence, datetime.utcnow()),
                    )

                message_id = cur.fetchone()["id"]
                logger.debug(f"Message added: session={session_id}, role={role}, id={message_id}")

                return message_id

    def get_history(
        self,
        session_id: str,
        limit: int = 100,
        user_id: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                if user_id is not None:
                    # Combined query: check permission and get messages in single query
                    cur.execute(
                        """
                        WITH session_check AS (
                            SELECT user_id
                            FROM conversations
                            WHERE session_id = %s
                        )
                        SELECT
                            m.id, m.role::text, m.content, m.answer,
                            m.sources_json, m.model_used, m.confidence, m.timestamp
                        FROM messages m
                        WHERE m.session_id = %s
                          AND EXISTS (
                              SELECT 1 FROM session_check sc
                              WHERE sc.user_id IS NULL OR sc.user_id = %s
                          )
                        ORDER BY m.timestamp ASC
                        LIMIT %s
                        """,
                        (session_id, session_id, user_id, limit),
                    )
                else:
                    cur.execute(
                        """
                        SELECT id, role::text, content, answer, sources_json, model_used, confidence, timestamp
                        FROM messages
                        WHERE session_id = %s
                        ORDER BY timestamp ASC
                        LIMIT %s
                        """,
                        (session_id, limit),
                    )

                rows = cur.fetchall()

                messages = []
                for row in rows:
                    message = dict(row)
                    if message.get("sources_json"):
                        message["sources_json"] = message["sources_json"]
                    messages.append(message)

                return messages

    def get_message_by_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, session_id, role::text, content, answer, sources_json, model_used, confidence, timestamp
                    FROM messages
                    WHERE id = %s
                    """,
                    (message_id,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                message = dict(row)
                if message.get("sources_json"):
                    message["sources_json"] = message["sources_json"]

                return message

    def add_feedback(
        self,
        session_id: str,
        message_id: int,
        rating: str,
        comment: Optional[str] = None,
    ) -> int:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO feedback (session_id, message_id, rating, comment, created_at)
                    VALUES (%s, %s, %s::feedback_rating, %s, %s)
                    RETURNING id
                    """,
                    (session_id, message_id, rating, comment, datetime.utcnow()),
                )

                feedback_id = cur.fetchone()["id"]
                logger.debug(f"Feedback added: message={message_id}, rating={rating}")

                return feedback_id

    def get_user_sessions(
        self,
        user_id: int,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Optimized: Use LATERAL JOIN instead of correlated subquery
                # and DISTINCT ON for getting last message efficiently
                cur.execute(
                    """
                    SELECT
                        c.session_id,
                        c.user_id,
                        c.title,
                        c.created_at,
                        c.updated_at,
                        COALESCE(msg_stats.message_count, 0) as message_count,
                        COALESCE(last_msg.last_message, 'New conversation') as last_message
                    FROM conversations c
                    LEFT JOIN LATERAL (
                        SELECT COUNT(*) as message_count
                        FROM messages
                        WHERE session_id = c.session_id
                    ) msg_stats ON true
                    LEFT JOIN LATERAL (
                        SELECT COALESCE(content, answer) as last_message
                        FROM messages
                        WHERE session_id = c.session_id
                        ORDER BY timestamp DESC
                        LIMIT 1
                    ) last_msg ON true
                    WHERE c.user_id = %s
                    ORDER BY c.updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset),
                )
                rows = cur.fetchall()

                return [dict(r) for r in rows]

    def get_user_sessions_count(self, user_id: int) -> int:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT session_id) as count
                    FROM conversations
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()

                return row["count"] if row else 0

    def delete_session(self, session_id: str) -> bool:
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM conversations WHERE session_id = %s",
                    (session_id,)
                )
                deleted = cur.rowcount > 0

                if deleted:
                    logger.info(f"Session deleted: {session_id}")

                return deleted

    def purge_old_conversations(self, days: Optional[int] = None) -> int:
        days = days or self.retention_days

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT purge_old_conversations(%s)",
                    (days,)
                )
                deleted = cur.fetchone()["purge_old_conversations"]

                if deleted > 0:
                    logger.info(f"Purged {deleted} old conversations")

                return deleted