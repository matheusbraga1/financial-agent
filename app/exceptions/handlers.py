from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging

logger = logging.getLogger(__name__)


class DocumentNotFoundException(Exception):
    pass


class EmbeddingException(Exception):
    pass


class LLMException(Exception):
    pass


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    logger.warning(f"Erro de validação: {exc.errors()}")
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": "Dados inválidos",
            "errors": exc.errors()
        }
    )


async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    logger.error(f"Erro não tratado: {str(exc)}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "detail": "Erro interno do servidor",
            "error": str(exc) if logger.level == logging.DEBUG else "Entre em contato com o suporte"
        }
    )