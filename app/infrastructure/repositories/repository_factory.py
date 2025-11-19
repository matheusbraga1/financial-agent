"""
Repository Factory Pattern

Factory for creating database repository instances based on configuration.
Supports both SQLite (legacy) and PostgreSQL (production).
"""

import logging
from typing import Union
from app.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


def create_user_repository():
    """
    Create user repository based on configuration.

    Returns:
        UserRepository instance (SQLite or PostgreSQL)
    """
    settings = get_settings()

    if settings.database_type.lower() == "postgres":
        logger.info("Initializing PostgreSQL user repository")
        from app.infrastructure.repositories.postgres_user_repository import (
            PostgresUserRepository,
        )

        return PostgresUserRepository(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_database,
            user=settings.postgres_user,
            password=settings.postgres_password,
            min_connections=settings.postgres_min_connections,
            max_connections=settings.postgres_max_connections,
        )
    else:
        logger.info("Initializing SQLite user repository")
        from app.infrastructure.repositories.user_repository import (
            SQLiteUserRepository,
        )

        return SQLiteUserRepository(db_path=settings.sqlite_users_db)


def create_conversation_repository():
    """
    Create conversation repository based on configuration.

    Returns:
        ConversationRepository instance (SQLite or PostgreSQL)
    """
    settings = get_settings()

    if settings.database_type.lower() == "postgres":
        logger.info("Initializing PostgreSQL conversation repository")
        from app.infrastructure.repositories.postgres_conversation_repository import (
            PostgresConversationRepository,
        )

        return PostgresConversationRepository(
            host=settings.postgres_host,
            port=settings.postgres_port,
            database=settings.postgres_database,
            user=settings.postgres_user,
            password=settings.postgres_password,
            min_connections=settings.postgres_min_connections,
            max_connections=settings.postgres_max_connections,
            retention_days=settings.chat_history_retention_days,
        )
    else:
        logger.info("Initializing SQLite conversation repository")
        from app.infrastructure.repositories.conversation_repository import (
            SQLiteConversationRepository,
        )

        return SQLiteConversationRepository(db_path=settings.sqlite_chat_db)


# Singleton instances
_user_repo = None
_conversation_repo = None


def get_user_repository():
    """
    Get singleton user repository instance.

    Returns:
        UserRepository instance
    """
    global _user_repo
    if _user_repo is None:
        _user_repo = create_user_repository()
    return _user_repo


def get_conversation_repository():
    """
    Get singleton conversation repository instance.

    Returns:
        ConversationRepository instance
    """
    global _conversation_repo
    if _conversation_repo is None:
        _conversation_repo = create_conversation_repository()
    return _conversation_repo
