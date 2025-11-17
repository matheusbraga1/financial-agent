import logging
from typing import Dict, Any
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.infrastructure.config.settings import get_settings
from app.presentation.api.v1.router import api_router

from app.presentation.api.middleware import (
    SecurityHeadersMiddleware,
    RequestIDMiddleware,
)

from app.presentation.api.exception_handlers import (
    validation_exception_handler,
    rate_limit_exception_handler,
    global_exception_handler,
)

from app.presentation.api.lifespan import create_lifespan_manager

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)

def create_application() -> FastAPI:
    lifespan_manager = create_lifespan_manager(
        app_name=settings.app_name,
        app_version=settings.app_version,
        debug=settings.debug,
        llm_provider=settings.llm_provider,
    )

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="API de Chat com IA para suporte técnico financeiro",
        docs_url="/docs" if settings.debug else None,
        redoc_url="/redoc" if settings.debug else None,
        lifespan=lifespan_manager.lifespan_context,
    )
    _configure_rate_limiting(app)

    _configure_middleware(app)

    _configure_exception_handlers(app)

    _configure_routers(app)

    _add_utility_endpoints(app)
    return app

def get_real_client_ip(request: Request) -> str:
    """
    Obtém o IP real do cliente considerando proxies e load balancers.

    Args:
        request: Request do FastAPI

    Returns:
        IP do cliente
    """
    # Tentar X-Forwarded-For primeiro (comum em proxies)
    if x_forwarded_for := request.headers.get("X-Forwarded-For"):
        # X-Forwarded-For pode ter múltiplos IPs, pegar o primeiro (cliente original)
        return x_forwarded_for.split(",")[0].strip()

    # Tentar X-Real-IP (usado por nginx)
    if x_real_ip := request.headers.get("X-Real-IP"):
        return x_real_ip.strip()

    # Fallback para IP direto
    return get_remote_address(request)


def _configure_rate_limiting(app: FastAPI) -> None:
    """Configura rate limiting global e por endpoint."""

    limiter = Limiter(
        key_func=get_real_client_ip,  # Usar função que considera proxies
        default_limits=["50/minute"],  # Reduzido de 100 para 50
    )

    app.state.limiter = limiter

    app.add_middleware(SlowAPIMiddleware)

    logger.info("✓ Rate limiting configured: 50 requests/minute per IP (considers X-Forwarded-For)")
    logger.info("  → Login endpoints: 5/minute")
    logger.info("  → Chat endpoints: 30/minute")
    logger.info("  → Other endpoints: 50/minute (default)")

def _configure_middleware(app: FastAPI) -> None:
    origins = (
        settings.cors_origins.split(",")
        if settings.cors_origins != "*"
        else ["*"]
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Total-Count",
            "X-Page",
            "X-Page-Size",
            "X-Total-Pages",
            "X-Request-ID",
            "X-Process-Time",
            "API-Version",
        ],
    )

    logger.info(f"✓ CORS configured: {origins}")

    app.add_middleware(
        SecurityHeadersMiddleware,
        api_version=settings.app_version,
    )

    logger.info("✓ Security headers middleware configured")

    app.add_middleware(RequestIDMiddleware)
    logger.info("✓ Request ID and timing middleware configured")

def _configure_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    logger.info("✓ Validation exception handler configured")

    async def rate_limit_handler_wrapper(request: Request, exc: RateLimitExceeded):
        return await rate_limit_exception_handler(
            request, exc, default_limits=app.state.limiter.default_limits
        )

    app.add_exception_handler(RateLimitExceeded, rate_limit_handler_wrapper)

    logger.info("✓ Rate limit exception handler configured")

    app.add_exception_handler(Exception, global_exception_handler)
    logger.info("✓ Global exception handler configured")

def _configure_routers(app: FastAPI) -> None:
    app.include_router(api_router, prefix="/api/v1")
    logger.info("✓ API routers configured under /api/v1")

def _add_utility_endpoints(app: FastAPI) -> None:
    @app.get("/", include_in_schema=False)
    async def root() -> Dict[str, Any]:
        return {
            "app": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs" if settings.debug else None,
            "health": "/health",
        }

    @app.get("/health", tags=["Health"])
    async def health_check() -> Dict[str, Any]:
        return {
            "status": "healthy",
            "app": settings.app_name,
            "version": settings.app_version,
        }
    logger.info("✓ Utility endpoints configured (/, /health)")

app = create_application()

logger.info("=" * 60)
logger.info(f"✓ {settings.app_name} application created successfully")
logger.info("=" * 60)