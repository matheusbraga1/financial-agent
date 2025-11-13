from fastapi import APIRouter, status
from typing import Dict, Any
import logging
import httpx

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get(
    "/health/liveness",
    tags=["Health"],
    summary="Liveness probe",
    description="Verifica se a aplicação está viva (usado por Kubernetes/Docker)",
    status_code=status.HTTP_200_OK,
)
async def liveness() -> Dict[str, str]:
    return {"status": "alive"}

@router.get(
    "/health/readiness",
    tags=["Health"],
    summary="Readiness probe",
    description="Verifica se a aplicação está pronta para receber tráfego",
    status_code=status.HTTP_200_OK,
    responses={
        200: {
            "description": "Aplicação pronta",
            "content": {
                "application/json": {
                    "example": {
                        "status": "ready",
                        "checks": {"qdrant": "healthy", "ollama": "healthy", "glpi_db": "healthy"},
                    }
                }
            },
        },
        503: {
            "description": "Aplicação não pronta — dependências falhando",
            "content": {
                "application/json": {
                    "example": {
                        "status": "not_ready",
                        "checks": {
                            "qdrant": "healthy",
                            "ollama": "unhealthy: connection refused",
                            "glpi_db": "healthy",
                        },
                    }
                }
            },
        },
    },
)

async def readiness() -> Dict[str, Any]:
    from app.services.vector_store_service import get_vector_store_instance
    from app.services.glpi_service import glpi_service
    from app.core.config import get_settings
    from fastapi import Response

    settings = get_settings()
    checks: Dict[str, str] = {}
    
    vector_store_service = get_vector_store_instance()

    checks["qdrant"] = await _check_qdrant(vector_store_service)
    checks["ollama"] = await _check_ollama(settings.ollama_host)
    checks["glpi_db"] = await _check_glpi_db(glpi_service)

    all_healthy = all(check == "healthy" for check in checks.values())

    response = {"status": "ready" if all_healthy else "not_ready", "checks": checks}

    if not all_healthy:
        logger.warning(f"Health check failed: {checks}")
        import json
        return Response(
            content=json.dumps(response),
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            media_type="application/json",
        )

    return response

async def _check_qdrant(vector_store) -> str:
    try:
        vector_store.client.get_collections()
        collection_info = vector_store.get_collection_info()
        if collection_info and collection_info.get("vectors_count", 0) >= 0:
            return "healthy"
        return "unhealthy: collection empty or invalid"
    except Exception as e:
        logger.error(f"Qdrant health check failed: {e}")
        return f"unhealthy: {str(e)[:100]}"

async def _check_ollama(ollama_host: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{ollama_host}/api/tags")
            if response.status_code == 200:
                return "healthy"
            return f"unhealthy: status {response.status_code}"
    except httpx.ConnectError:
        logger.error("Ollama health check failed: connection refused")
        return "unhealthy: connection refused"
    except httpx.TimeoutException:
        logger.error("Ollama health check failed: timeout")
        return "unhealthy: timeout"
    except Exception as e:
        logger.error(f"Ollama health check failed: {e}")
        return f"unhealthy: {str(e)[:100]}"

async def _check_glpi_db(glpi_service) -> str:
    try:
        if glpi_service.test_connection():
            return "healthy"
        return "unhealthy: connection test failed"
    except Exception as e:
        logger.error(f"GLPI DB health check failed: {e}")
        return f"unhealthy: {str(e)[:100]}"

@router.get(
    "/health",
    tags=["Health"],
    summary="Health check geral",
    description="Health check simplificado (compatibilidade)",
    status_code=status.HTTP_200_OK,
)
async def health() -> Dict[str, str]:
    return {"status": "healthy", "message": "Use /health/readiness para verificação completa"}
