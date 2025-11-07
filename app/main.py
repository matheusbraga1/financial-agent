from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
from fastapi.security import HTTPBearer
import logging
import uuid

from app.core.config import get_settings
from app.core.logging import setup_logging
from app.api.v1.router import api_router
from app.exceptions.handlers import (
    validation_exception_handler,
    general_exception_handler,
    http_exception_handler,
)

# Configuração de segurança para Swagger
security_scheme = HTTPBearer()


setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()


tags_metadata = [
    {
        "name": "Autenticação",
        "description": """
        Gerenciamento de usuários e autenticação JWT.

        **Fluxo de Autenticação:**
        1. Registrar novo usuário com `/auth/register`
        2. Fazer login com `/auth/login` para obter token JWT
        3. Usar o token nas requisições protegidas: `Authorization: Bearer TOKEN`
        4. Verificar dados do usuário com `/auth/me`
        5. Fazer logout com `/auth/logout` para revogar o token
        """
    },
    {
        "name": "Chat",
        "description": """
        Endpoints de conversação com IA usando RAG (Retrieval Augmented Generation).

        **Funcionalidades:**
        - Chat com respostas contextualizadas baseadas na base de conhecimento GLPI
        - Streaming de respostas em tempo real (SSE)
        - Histórico de conversas persistente
        - Busca híbrida (vetorial + texto) com MMR
        """
    },
    {
        "name": "Documentos",
        "description": """
        Gestão da base de conhecimento e documentos indexados.

        **Recursos:**
        - Adicionar novos documentos (requer admin)
        - Consultar estatísticas da coleção
        - Sincronização automática com GLPI
        """
    },
    {
        "name": "Health",
        "description": """
        Endpoints para monitoramento e verificação de saúde dos serviços.

        **Verificações:**
        - Status geral da aplicação
        - Conectividade com Qdrant (Vector DB)
        - Conectividade com Ollama (LLM)
        """
    },
]

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="API REST para sistema de chat inteligente com busca contextualizada em documentos GLPI usando RAG (Retrieval Augmented Generation).",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=tags_metadata,
    contact={
        "name": "Suporte TI",
        "email": "ti@empresa.com.br",
    },
    license_info={
        "name": "Interno - Empresa",
    },
    swagger_ui_parameters={
        "persistAuthorization": True,
        "displayRequestDuration": True,
        "filter": True,
        "tryItOutEnabled": True,
    },
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(",") if settings.cors_origins != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(Exception, general_exception_handler)

app.include_router(api_router, prefix="/api/v1")


# Configurar o botão Authorize no Swagger
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    from fastapi.openapi.utils import get_openapi

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        description=app.description,
        routes=app.routes,
        tags=app.openapi_tags,
    )

    # Adicionar configuração de segurança JWT Bearer
    openapi_schema["components"]["securitySchemes"] = {
        "Bearer": {
            "type": "http",
            "scheme": "bearer",
            "bearerFormat": "JWT",
            "description": "Insira o token JWT obtido do endpoint /auth/login (sem o prefixo 'Bearer')"
        }
    }

    # Marcar endpoints protegidos (que usam get_current_user obrigatório)
    protected_endpoints = [
        "/api/v1/auth/me",
        "/api/v1/auth/logout",
        "/api/v1/chat/history",  # Histórico requer autenticação para verificar propriedade
        "/api/v1/documents",  # Criar documentos requer admin
    ]

    # Nota: /api/v1/chat e /api/v1/chat/stream usam autenticação OPCIONAL (get_optional_user)
    # O histórico NÃO será persistido se o usuário não estiver autenticado

    # Adicionar segurança aos endpoints protegidos
    for path, path_item in openapi_schema["paths"].items():
        for method in path_item:
            if method in ["get", "post", "put", "delete", "patch"]:
                # Verificar se o endpoint está na lista de protegidos
                if any(path.startswith(protected) for protected in protected_endpoints):
                    path_item[method]["security"] = [{"Bearer": []}]

    app.openapi_schema = openapi_schema
    return app.openapi_schema


app.openapi = custom_openapi


@app.middleware("http")
async def add_request_id(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    response = await call_next(request)
    response.headers["X-Request-ID"] = request_id
    return response


@app.on_event("startup")
async def startup_event():
    logger.info(f"Iniciando {settings.app_name} v{settings.app_version}")
    logger.info(f"Modo Debug: {settings.debug}")
    logger.info(f"Modelo LLM: {settings.ollama_model}")
    logger.info(f"Collection: {settings.qdrant_collection}")

    # Validação de segurança para JWT Secret
    if settings.jwt_secret == "change-me-in-.env":
        logger.warning("⚠️  ATENÇÃO: JWT_SECRET está usando valor padrão!")
        if not settings.debug:
            logger.error("❌ Configure JWT_SECRET no arquivo .env para produção!")
            raise ValueError("JWT_SECRET não configurado para ambiente de produção")


@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Encerrando aplicação...")


@app.get("/", tags=["Root"])
async def root():
    return {
        "message": f"Bem-vindo ao {settings.app_name}",
        "version": settings.app_version,
        "docs": "/docs",
    }


@app.get("/health", tags=["Health"])
async def health():
    return {
        "status": "healthy",
        "app": settings.app_name,
        "version": settings.app_version,
    }

