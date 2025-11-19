"""
Repository Factory Pattern

Factory for creating database repository instances.
Uses PostgreSQL for production.
"""

import logging
from app.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)


def create_user_repository():
    """
    Create PostgreSQL user repository.

    Returns:
        PostgresUserRepository instance
    """
    settings = get_settings()

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


def create_conversation_repository():
    """
    Create PostgreSQL conversation repository.

    Returns:
        PostgresConversationRepository instance
    """
    settings = get_settings()

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


_user_repo = None
_conversation_repo = None


def get_user_repository():
    global _user_repo
    if _user_repo is None:
        _user_repo = create_user_repository()
    return _user_repo


def get_conversation_repository():
    global _conversation_repo
    if _conversation_repo is None:
        _conversation_repo = create_conversation_repository()
    return _conversation_repo
