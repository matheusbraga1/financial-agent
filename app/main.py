from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
import logging

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.api.v1.router import api_router
from app.exceptions.handlers import (
    validation_exception_handler,
    general_exception_handler
)

setup_logging()
logger = logging.getLogger(__name__)

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API de Chat com IA para Base de Conhecimento GLPI",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handlers
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

# Incluir rotas da API v1
app.include_router(api_router, prefix="/api/v1")


@app.on_event("startup")
async def startup_event():
    logger.info(f"🚀 Iniciando {settings.app_name} v{settings.app_version}")
    logger.info(f"📊 Modo Debug: {settings.debug}")
    logger.info(f"🤖 Modelo LLM: {settings.ollama_model}")
    logger.info(f"📚 Collection: {settings.qdrant_collection}")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Encerrando aplicação...")


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Bem-vindo ao {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version
    }