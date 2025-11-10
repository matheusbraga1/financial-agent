"""Embedding adapters."""

from app.infrastructure.adapters.embeddings.sentence_transformer_adapter import (
    EmbeddingService,
    get_embedding_service_instance
)

__all__ = ["EmbeddingService", "get_embedding_service_instance"]
