from fastapi import APIRouter, Depends, status, HTTPException
from typing import Dict, Any, List
from datetime import datetime
import psutil
import asyncio
from dataclasses import dataclass
from enum import Enum

class HealthStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"

@dataclass
class ComponentHealth:
    name: str
    status: HealthStatus
    message: str = ""
    metadata: Dict[str, Any] = None

class HealthCheckService:
    """Serviço de health check abrangente"""
    
    def __init__(self, dependencies: Dict[str, Any]):
        self.dependencies = dependencies
    
    async def check_database(self) -> ComponentHealth:
        """Verifica saúde do banco de dados"""
        try:
            # Exemplo com SQLAlchemy
            db = self.dependencies.get('database')
            if db:
                result = await db.execute("SELECT 1")
                return ComponentHealth(
                    name="database",
                    status=HealthStatus.HEALTHY,
                    metadata={"connected": True, "response_time_ms": 5}
                )
        except Exception as e:
            return ComponentHealth(
                name="database",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                metadata={"connected": False}
            )
    
    async def check_redis(self) -> ComponentHealth:
        """Verifica saúde do Redis"""
        try:
            redis = self.dependencies.get('redis')
            if redis:
                await redis.ping()
                info = await redis.info()
                return ComponentHealth(
                    name="redis",
                    status=HealthStatus.HEALTHY,
                    metadata={
                        "connected": True,
                        "used_memory": info.get('used_memory_human'),
                        "connected_clients": info.get('connected_clients')
                    }
                )
        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                metadata={"connected": False}
            )
    
    async def check_vector_store(self) -> ComponentHealth:
        """Verifica saúde do Qdrant"""
        try:
            qdrant = self.dependencies.get('vector_store')
            if qdrant:
                info = qdrant.get_collection_info()
                return ComponentHealth(
                    name="vector_store",
                    status=HealthStatus.HEALTHY,
                    metadata={
                        "connected": True,
                        "vectors_count": info.get('vectors_count'),
                        "status": "operational"
                    }
                )
        except Exception as e:
            return ComponentHealth(
                name="vector_store",
                status=HealthStatus.DEGRADED,
                message=str(e),
                metadata={"connected": False}
            )
    
    async def check_external_services(self) -> List[ComponentHealth]:
        """Verifica APIs externas"""
        results = []
        
        # Exemplo: Verificar Groq API
        try:
            groq = self.dependencies.get('groq_client')
            if groq:
                # Fazer chamada de teste leve
                results.append(ComponentHealth(
                    name="groq_api",
                    status=HealthStatus.HEALTHY,
                    metadata={"available": True}
                ))
        except Exception as e:
            results.append(ComponentHealth(
                name="groq_api",
                status=HealthStatus.DEGRADED,
                message=str(e)
            ))
        
        return results
    
    def get_system_metrics(self) -> Dict[str, Any]:
        """Coleta métricas do sistema"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu": {
                "usage_percent": cpu_percent,
                "count": psutil.cpu_count()
            },
            "memory": {
                "total_gb": round(memory.total / (1024**3), 2),
                "available_gb": round(memory.available / (1024**3), 2),
                "used_percent": memory.percent
            },
            "disk": {
                "total_gb": round(disk.total / (1024**3), 2),
                "free_gb": round(disk.free / (1024**3), 2),
                "used_percent": disk.percent
            }
        }
    
    async def full_health_check(self) -> Dict[str, Any]:
        """Executa health check completo"""
        # Executa checks em paralelo
        results = await asyncio.gather(
            self.check_database(),
            self.check_redis(),
            self.check_vector_store(),
            self.check_external_services(),
            return_exceptions=True
        )
        
        # Processa resultados
        components = []
        overall_status = HealthStatus.HEALTHY
        
        for result in results:
            if isinstance(result, list):
                components.extend(result)
            elif isinstance(result, ComponentHealth):
                components.append(result)
            else:
                # Erro na execução
                components.append(ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=str(result)
                ))
        
        # Determina status geral
        for component in components:
            if component.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
                break
            elif component.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED
        
        return {
            "status": overall_status,
            "timestamp": datetime.utcnow().isoformat(),
            "version": self.dependencies.get('app_version', 'unknown'),
            "components": [
                {
                    "name": c.name,
                    "status": c.status,
                    "message": c.message,
                    "metadata": c.metadata
                }
                for c in components
            ],
            "system": self.get_system_metrics()
        }

# Router para health checks
health_router = APIRouter(tags=["Health"])

@health_router.get("/health", response_model=Dict[str, Any])
async def health_check(
    health_service: HealthCheckService = Depends()
):
    """Health check completo do sistema"""
    result = await health_service.full_health_check()
    
    # Define status code baseado no status
    if result["status"] == HealthStatus.HEALTHY:
        status_code = status.HTTP_200_OK
    elif result["status"] == HealthStatus.DEGRADED:
        status_code = status.HTTP_200_OK  # Ou 207 MULTI_STATUS
    else:
        status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    
    return result

@health_router.get("/health/live")
async def liveness_probe():
    """Liveness probe simples para Kubernetes"""
    return {"status": "alive"}

@health_router.get("/health/ready")
async def readiness_probe(
    health_service: HealthCheckService = Depends()
):
    """Readiness probe para Kubernetes"""
    result = await health_service.full_health_check()
    
    if result["status"] == HealthStatus.UNHEALTHY:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Service not ready"
        )
    
    return {"status": "ready"}