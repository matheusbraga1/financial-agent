import logging
from typing import Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, status, HTTPException
import psutil

from app.presentation.api.dependencies import (
    get_vector_store,
    get_embeddings_adapter,
    get_redis_client,
)
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter
from app.infrastructure.adapters.embeddings.sentence_transformer_adapter import SentenceTransformerAdapter
from app.infrastructure.config.settings import get_settings
import redis.asyncio as redis

logger = logging.getLogger(__name__)

router = APIRouter()

@router.get(
    "",
    summary="Health check completo com componentes",
    responses={
        200: {"description": "Sistema saudável"},
        503: {"description": "Sistema com problemas"},
    },
)
async def health_check(
    vector_store: QdrantAdapter = Depends(get_vector_store),
    embeddings: SentenceTransformerAdapter = Depends(get_embeddings_adapter),
    redis_client: redis.Redis = Depends(get_redis_client),
) -> Dict[str, Any]:
    settings = get_settings()
    
    health = {
        "status": "healthy",
        "version": settings.app_version,
        "timestamp": datetime.utcnow().isoformat(),
        "components": {},
        "system": {}
    }

    try:
        stats = vector_store.get_stats()
        health["components"]["vector_store"] = {
            "status": "healthy",
            "type": "qdrant",
            "vectors_count": stats.get("vectors_count", 0),
            "indexed_vectors_count": stats.get("indexed_vectors_count", 0),
        }
    except Exception as e:
        logger.error(f"Vector store health check failed: {e}")
        health["status"] = "degraded"
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
            "device": "cpu",
        }
    except Exception as e:
        logger.error(f"Embeddings health check failed: {e}")
        health["status"] = "degraded"
        health["components"]["embeddings"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    try:
        from app.infrastructure.repositories.conversation_repository import conversation_repository
        conn = conversation_repository._connect()
        conn.execute("SELECT 1")
        conn.close()
        
        health["components"]["database"] = {
            "status": "healthy",
            "type": "sqlite",
            "location": "app_data/",
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        health["status"] = "unhealthy"
        health["components"]["database"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    try:
        await redis_client.ping()
        info = await redis_client.info()
        
        health["components"]["redis"] = {
            "status": "healthy",
            "connected_clients": info.get("connected_clients", 0),
            "used_memory": info.get("used_memory_human", "unknown"),
            "uptime_seconds": info.get("uptime_in_seconds", 0),
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        health["status"] = "degraded"
        health["components"]["redis"] = {
            "status": "unhealthy",
            "error": str(e),
        }

    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        health["system"] = {
            "cpu": {
                "usage_percent": cpu_percent,
                "count": psutil.cpu_count(),
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": memory.percent,
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_percent": disk.percent,
            }
        }
    except Exception as e:
        logger.error(f"System metrics failed: {e}")
        health["system"] = {"error": str(e)}

    status_code = (
        status.HTTP_200_OK
        if health["status"] == "healthy"
        else status.HTTP_503_SERVICE_UNAVAILABLE
        if health["status"] == "unhealthy"
        else status.HTTP_200_OK
    )

    return health

@router.get(
    "/live",
    summary="Liveness probe para Kubernetes",
    responses={
        200: {"description": "Aplicação está viva"},
    },
)
async def liveness_probe() -> Dict[str, str]:
    return {"status": "alive"}

@router.get(
    "/ready",
    summary="Readiness probe para Kubernetes",
    responses={
        200: {"description": "Aplicação pronta para receber tráfego"},
        503: {"description": "Aplicação não está pronta"},
    },
)
async def readiness_probe(
    vector_store: QdrantAdapter = Depends(get_vector_store),
    redis_client: redis.Redis = Depends(get_redis_client),
) -> Dict[str, str]:
    try:
        vector_store.get_stats()
        await redis_client.ping()

        return {"status": "ready"}
    except Exception as e:
        logger.error(f"Readiness check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )