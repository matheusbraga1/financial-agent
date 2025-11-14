import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, status

from app.presentation.api.dependencies import (
    get_vector_store,
    get_embeddings_adapter,
)
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter
from app.infrastructure.adapters.embeddings.sentence_transformer_adapter import SentenceTransformerAdapter
from app.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get(
    "",
    summary="Health check completo",
    responses={
        200: {"description": "Sistema saudável"},
        503: {"description": "Sistema com problemas"},
    },
)
async def health_check(
    vector_store: QdrantAdapter = Depends(get_vector_store),
    embeddings: SentenceTransformerAdapter = Depends(get_embeddings_adapter),
) -> Dict[str, Any]:
    settings = get_settings()
    
    health = {
        "status": "healthy",
        "version": settings.app_version,
        "components": {},
    }
    
    try:
        stats = vector_store.get_stats()
        health["components"]["vector_store"] = {
            "status": "healthy",
            "documents": stats.get("vectors_count", 0),
        }
    except Exception as e:
        logger.error(f"Vector store health check failed: {e}")
        health["status"] = "unhealthy"
        health["components"]["vector_store"] = {
            "status": "unhealthy",
            "error": str(e),
        }
    
    try:
        dimension = embeddings.get_dimension()
        health["components"]["embeddings"] = {
            "status": "healthy",
            "model": settings.embedding_model,
            "dimension": dimension,
        }
    except Exception as e:
        logger.error(f"Embeddings health check failed: {e}")
        health["status"] = "unhealthy"
        health["components"]["embeddings"] = {
            "status": "unhealthy",
            "error": str(e),
        }
    
    try:
        from app.infrastructure.repositories.conversation_repository import conversation_repository
        conversation_repository._connect().close()
        health["components"]["database"] = {
            "status": "healthy",
            "type": "sqlite",
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health["status"] = "unhealthy"
        health["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }
    
    status_code = status.HTTP_200_OK if health["status"] == "healthy" else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return health