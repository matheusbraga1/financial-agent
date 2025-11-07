from fastapi import Request, status, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
import logging
from app.models.error import ErrorResponse


logger = logging.getLogger(__name__)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    trace_id = getattr(request.state, "request_id", None)
    logger.warning(f"Erro de validação: {exc.errors()} | trace_id={trace_id}")
    err = ErrorResponse(
        code="validation_error",
        message="Dados inválidos",
        trace_id=trace_id,
        details=exc.errors(),
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content=err.model_dump()
    )


async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    trace_id = getattr(request.state, "request_id", None)
    logger.error(
        f"Erro não tratado: {str(exc)} | trace_id={trace_id}", exc_info=True
    )
    err = ErrorResponse(
        code="internal_error",
        message="Erro interno do servidor",
        trace_id=trace_id,
        details=None,
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content=err.model_dump()
    )


async def http_exception_handler(
    request: Request, exc: HTTPException
) -> JSONResponse:
    trace_id = getattr(request.state, "request_id", None)
    code_map = {
        status.HTTP_400_BAD_REQUEST: "bad_request",
        status.HTTP_401_UNAUTHORIZED: "unauthorized",
        status.HTTP_403_FORBIDDEN: "forbidden",
        status.HTTP_404_NOT_FOUND: "not_found",
    }
    code = code_map.get(exc.status_code, "http_error")
    message = exc.detail if isinstance(exc.detail, str) else "Erro na requisição"
    logger.warning(f"HTTPException {exc.status_code}: {message} | trace_id={trace_id}")
    err = ErrorResponse(
        code=code,
        message=message,
        trace_id=trace_id,
        details=None,
    )
    return JSONResponse(status_code=exc.status_code, content=err.model_dump())

