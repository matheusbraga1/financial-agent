import logging
from typing import Optional, Dict, Any
from datetime import datetime
from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from contextlib import contextmanager

logger = logging.getLogger(__name__)


class PostgresUserRepository:
    """PostgreSQL implementation of user repository with connection pooling."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 5432,
        database: str = "financial_agent",
        user: str = "postgres",
        password: str = "",
        min_connections: int = 2,
        max_connections: int = 10,
    ):
        """
        Initialize PostgreSQL user repository with connection pool.

        Args:
            host: PostgreSQL host
            port: PostgreSQL port
            database: Database name
            user: Database user
            password: Database password
            min_connections: Minimum connections in pool
            max_connections: Maximum connections in pool
        """
        self.connection_pool = None

        try:
            conninfo = f"host={host} port={port} dbname={database} user={user} password={password} connect_timeout=10"

            self.connection_pool = ConnectionPool(
                conninfo=conninfo,
                min_size=min_connections,
                max_size=max_connections,
                kwargs={"row_factory": dict_row},
            )

            logger.info(
                f"PostgresUserRepository initialized: {host}:{port}/{database}"
            )

        except Exception as e:
            logger.error(f"Failed to create connection pool: {e}")
            raise

    def __del__(self):
        """Close all connections in pool on cleanup."""
        if self.connection_pool:
            self.connection_pool.close()
            logger.info("Connection pool closed")

    @contextmanager
    def _get_connection(self):
        """
        Context manager for database connections from pool.

        Yields:
            psycopg connection with dict row factory
        """
        with self.connection_pool.connection() as conn:
            try:
                yield conn
                conn.commit()
            except Exception as e:
                conn.rollback()
                logger.error(f"Database error: {e}")
                raise

    def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        is_active: bool = True,
        is_admin: bool = False,
    ) -> int:
        """
        Create a new user.

        Args:
            username: Unique username
            email: Unique email
            hashed_password: Bcrypt hashed password
            is_active: Whether user is active
            is_admin: Whether user is admin

        Returns:
            User ID of created user

        Raises:
            ValueError: If username or email already exists
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Single query to check both username and email existence
                cur.execute(
                    """
                    SELECT
                        EXISTS(SELECT 1 FROM users WHERE username = %s) as username_exists,
                        EXISTS(SELECT 1 FROM users WHERE email = %s) as email_exists
                    """,
                    (username, email)
                )
                result = cur.fetchone()

                if result["username_exists"]:
                    raise ValueError(f"Username '{username}' already exists")
                if result["email_exists"]:
                    raise ValueError(f"Email '{email}' already exists")

                # Insert new user
                cur.execute(
                    """
                    INSERT INTO users (username, email, hashed_password, is_active, is_admin, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING id
                    """,
                    (username, email, hashed_password, is_active, is_admin),
                )

                user_id = cur.fetchone()["id"]
                logger.info(f"User created: id={user_id}, username={username}")

                return user_id

    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """
        Get user by ID.

        Args:
            user_id: User ID

        Returns:
            User dict or None if not found
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, username, email, hashed_password, is_active, is_admin, created_at, updated_at
                    FROM users
                    WHERE id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                return dict(row)

    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Get user by username.

        Args:
            username: Username

        Returns:
            User dict or None if not found
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, username, email, hashed_password, is_active, is_admin, created_at, updated_at
                    FROM users
                    WHERE username = %s
                    """,
                    (username,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                return dict(row)

    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """
        Get user by email.

        Args:
            email: Email address

        Returns:
            User dict or None if not found
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, username, email, hashed_password, is_active, is_admin, created_at, updated_at
                    FROM users
                    WHERE email = %s
                    """,
                    (email,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                return dict(row)

    def update_user(self, user_id: int, **fields) -> bool:
        """
        Update user fields.

        Args:
            user_id: User ID
            **fields: Fields to update (username, email, hashed_password, is_active, is_admin)

        Returns:
            True if user was updated, False otherwise
        """
        if not fields:
            return False

        allowed_fields = {"username", "email", "hashed_password", "is_active", "is_admin"}
        update_fields = {k: v for k, v in fields.items() if k in allowed_fields}

        if not update_fields:
            return False

        # Always update updated_at
        update_fields["updated_at"] = datetime.utcnow()

        with self._get_connection() as conn:
            with conn.cursor() as cur:
                # Build dynamic UPDATE query
                set_clause = ", ".join(f"{field} = %s" for field in update_fields.keys())
                values = list(update_fields.values()) + [user_id]

                cur.execute(
                    f"UPDATE users SET {set_clause} WHERE id = %s",
                    values,
                )

                updated = cur.rowcount > 0

                if updated:
                    logger.info(
                        f"User updated: id={user_id}, fields={list(update_fields.keys())}"
                    )

                return updated

    def delete_user(self, user_id: int) -> bool:
        """
        Delete user (cascades to refresh_tokens).

        Args:
            user_id: User ID

        Returns:
            True if user was deleted, False otherwise
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM users WHERE id = %s", (user_id,))
                deleted = cur.rowcount > 0

                if deleted:
                    logger.info(f"User deleted: id={user_id}")

                return deleted

    def store_refresh_token(
        self,
        user_id: int,
        token: str,
        expires_at: datetime,
    ) -> int:
        """
        Store refresh token.

        Args:
            user_id: User ID
            token: Refresh token string
            expires_at: Token expiration datetime

        Returns:
            Token ID
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO refresh_tokens (user_id, token, expires_at, created_at)
                    VALUES (%s, %s, %s, %s)
                    RETURNING id
                    """,
                    (user_id, token, expires_at, datetime.utcnow()),
                )

                token_id = cur.fetchone()["id"]
                logger.debug(f"Refresh token stored for user_id={user_id}")

                return token_id

    def get_refresh_token(self, token: str) -> Optional[Dict[str, Any]]:
        """
        Get refresh token by token string.

        Args:
            token: Refresh token string

        Returns:
            Token dict or None if not found
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, token, expires_at, created_at
                    FROM refresh_tokens
                    WHERE token = %s
                    """,
                    (token,),
                )
                row = cur.fetchone()

                if not row:
                    return None

                return dict(row)

    def delete_refresh_token(self, token: str) -> bool:
        """
        Delete refresh token.

        Args:
            token: Refresh token string

        Returns:
            True if token was deleted, False otherwise
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM refresh_tokens WHERE token = %s",
                    (token,)
                )

                return cur.rowcount > 0

    def delete_expired_tokens(self) -> int:
        """
        Delete all expired refresh tokens using helper function.

        Returns:
            Number of tokens deleted
        """
        with self._get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT cleanup_expired_tokens()")
                deleted = cur.fetchone()["cleanup_expired_tokens"]

                if deleted > 0:
                    logger.info(f"Removed {deleted} expired refresh tokens")

                return deleted
