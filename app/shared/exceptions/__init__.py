"""Custom exceptions for the application."""

from app.shared.exceptions.domain_exceptions import (
    DomainException,
    ValidationException,
    EntityNotFoundException,
)
from app.shared.exceptions.infrastructure_exceptions import (
    InfrastructureException,
    DatabaseException,
    ExternalServiceException,
    VectorStoreException,
)

__all__ = [
    "DomainException",
    "ValidationException",
    "EntityNotFoundException",
    "InfrastructureException",
    "DatabaseException",
    "ExternalServiceException",
    "VectorStoreException",
]
