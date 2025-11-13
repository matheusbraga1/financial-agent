import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.v1 import auth, chat, documents
from app.core.config import get_settings
from app.models.error import ErrorResponse

settings = get_settings()

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"🚀 Starting {settings.app_name} v{settings.app_version}")
    logger.info(f"Debug mode: {settings.debug}")
    logger.info(f"LLM Provider: {settings.llm_provider}")
    yield
    logger.info(f"👋 Shutting down {settings.app_name}")

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API de Chat com IA para suporte técnico",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.state.limiter = limiter

app.add_middleware(SlowAPIMiddleware)

origins = settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Total-Count", "X-Page", "X-Page-Size", "X-Total-Pages", "X-Request-ID", "API-Version"],
)

@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["API-Version"] = settings.app_version
    return response

@app.middleware("http")
async def add_request_id(request: Request, call_next):
    import uuid
    request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Process-Time"] = f"{process_time:.3f}s"
    
    logger.info(
        f"{request.method} {request.url.path} - {response.status_code} - {process_time:.3f}s - ID: {request_id}"
    )
    
    return response

@app.exception_handler(RateLimitExceeded)
async def rate_limit_exception_handler(request: Request, exc: RateLimitExceeded):
    trace_id = getattr(request.state, "request_id", None)
    
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        content=ErrorResponse(
            code="rate_limited",
            message=f"Rate limit exceeded: {exc.detail}",
            trace_id=trace_id,
            retryable=True,
            retry_after=60,
        ).model_dump(),
        headers={
            "Retry-After": "60",
            "X-RateLimit-Limit": str(limiter.default_limits),
        }
    )

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    trace_id = getattr(request.state, "request_id", None)
    errors = exc.errors()
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=ErrorResponse(
            code="validation_error",
            message="Validation error in request data",
            details=errors,
            trace_id=trace_id,
            retryable=False,
        ).model_dump(),
    )

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    trace_id = getattr(request.state, "request_id", None)
    logger.error(f"Unhandled exception (trace_id={trace_id}): {exc}", exc_info=True)
    
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=ErrorResponse(
            code="internal_error",
            message="An unexpected error occurred. Please try again later.",
            trace_id=trace_id,
            retryable=True,
        ).model_dump(),
    )

app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(chat.router, prefix="/api/v1/chat", tags=["Chat"])
app.include_router(documents.router, prefix="/api/v1/documents", tags=["Documents"])

@app.get("/", include_in_schema=False)
async def root():
    return {
        "app": settings.app_name,
        "version": settings.app_version,
        "docs": "/docs",
        "health": "/health",
    }

@app.get("/health", tags=["Health"])
async def health_check():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }