import logging
import json
from typing import List, Dict, Any, Optional
from datetime import datetime
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor, Json
from contextlib import contextmanager
import uuid

logger = logging.getLogger(__name__)


class PostgresConversationRepository:
    """PostgreSQL implementation of conversation repository with connection pooling."""

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
        """
        Initialize PostgreSQL conversation repository with connection pool.

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Database user
            password: Database password
            min_connections: Minimum connections in pool
            max_connections: Maximum connections in pool
            retention_days: Days to retain old conversations
        """
        self.connection_pool = None
        self.retention_days = retention_days

        try:
            self.connection_pool = pool.ThreadedConnectionPool(
                minconn=min_connections,
                maxconn=max_connections,
                host=host,
                port=port,
                database=database,
                user=user,
                password=password,
                cursor_factory=RealDictCursor,
                connect_timeout=10,
            )

            logger.info(
                f"PostgresConversationRepository initialized: {host}:{port}/{database}"
            )

        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    def __del__(self):
        """Close all connections in pool on cleanup."""
        if self.connection_pool:
            self.connection_pool.closeall()
            logger.info("Connection pool closed")

    @contextmanager
    def _get_connection(self):
        """
        Context manager for database connections from pool.

        Yields:
            psycopg2 connection with RealDictCursor
        """
        conn = None
        try:
            conn = self.connection_pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                self.connection_pool.putconn(conn)

    def create_session(
        self,
        session_id: Optional[str] = None,
        user_id: Optional[int] = None,
        title: Optional[str] = None,
    ) -> str:
        """
        Create or update a conversation session.

        Args:
            session_id: Session UUID (generated if not provided)
            user_id: User ID (optional, for authenticated users)
            title: Conversation title (optional)

        Returns:
            Session ID (UUID string)
        """
        if session_id is None:
            session_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Check if session exists
                cur.execute(
                    "SELECT user_id FROM conversations WHERE session_id = %s",
                    (session_id,)
                )
                existing = cur.fetchone()

                if existing is None:
                    # Create new session
                    cur.execute(
                        """
                        INSERT INTO conversations (session_id, user_id, title, created_at, updated_at)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (session_id, user_id, title, datetime.utcnow(), datetime.utcnow()),
                    )
                    logger.info(f"Session created: {session_id}")

                elif user_id and not existing["user_id"]:
                    # Update anonymous session to authenticated
                    cur.execute(
                        """
                        UPDATE conversations
                        SET user_id = %s, updated_at = %s
                        WHERE session_id = %s
                        """,
                        (user_id, datetime.utcnow(), session_id),
                    )
                    logger.info(f"Session {session_id} migrated to user_id={user_id}")

                return session_id

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """
        Get conversation session by ID.

        Args:
            session_id: Session UUID

        Returns:
            Session dict or None if not found
        """
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
        """
        Add message to conversation.

        Args:
            session_id: Session UUID
            role: Message role ('user' or 'assistant')
            content: User message content
            answer: Assistant answer
            sources: List of source documents (stored as JSONB)
            model: Model used for generation
            confidence: Confidence score (0-1)

        Returns:
            Message ID
        """
        # Ensure session exists
        self.create_session(session_id)

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Convert sources to JSON if provided
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
                else:  # assistant
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
        """
        Get conversation history.

        Args:
            session_id: Session UUID
            limit: Maximum number of messages
            user_id: User ID for authorization check

        Returns:
            List of message dicts
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Authorization check if user_id provided
                if user_id is not None:
                    cur.execute(
                        "SELECT user_id FROM conversations WHERE session_id = %s",
                        (session_id,),
                    )
                    session_row = cur.fetchone()

                    if not session_row:
                        logger.warning(f"Session {session_id} not found")
                        return []

                    session_user_id = session_row["user_id"]
                    if session_user_id and session_user_id != user_id:
                        logger.warning(
                            f"User {user_id} attempted to access session {session_id} "
                            f"belonging to user {session_user_id}"
                        )
                        return []

                # Get messages
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

                # Convert to list of dicts
                messages = []
                for row in rows:
                    message = dict(row)
                    # Convert sources_json to list if present
                    if message.get("sources_json"):
                        message["sources_json"] = message["sources_json"]
                    messages.append(message)

                return messages

    def get_message_by_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        """
        Get message by ID.

        Args:
            message_id: Message ID

        Returns:
            Message dict or None if not found
        """
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
                # Convert sources_json to list if present
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
        """
        Add feedback to a message.

        Args:
            session_id: Session UUID
            message_id: Message ID
            rating: Rating ('positive', 'negative', or 'neutral')
            comment: Optional feedback comment

        Returns:
            Feedback ID
        """
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
        """
        Get user's conversation sessions with statistics.

        Args:
            user_id: User ID
            limit: Maximum number of sessions
            offset: Pagination offset

        Returns:
            List of session dicts with statistics
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        c.session_id,
                        c.user_id,
                        c.title,
                        c.created_at,
                        c.updated_at,
                        COUNT(m.id) as message_count,
                        (
                            SELECT COALESCE(content, answer, 'New conversation')
                            FROM messages
                            WHERE session_id = c.session_id
                            ORDER BY timestamp DESC
                            LIMIT 1
                        ) as last_message
                    FROM conversations c
                    LEFT JOIN messages m ON c.session_id = m.session_id
                    WHERE c.user_id = %s
                    GROUP BY c.session_id, c.user_id, c.title, c.created_at, c.updated_at
                    ORDER BY c.updated_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, limit, offset),
                )
                rows = cur.fetchall()

                return [dict(r) for r in rows]

    def get_user_sessions_count(self, user_id: int) -> int:
        """
        Get count of user's sessions.

        Args:
            user_id: User ID

        Returns:
            Number of sessions
        """
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
        """
        Delete conversation session (cascades to messages and feedback).

        Args:
            session_id: Session UUID

        Returns:
            True if session was deleted, False otherwise
        """
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
        """
        Purge conversations older than specified days using helper function.

        Args:
            days: Days to retain (defaults to instance retention_days)

        Returns:
            Number of conversations deleted
        """
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
