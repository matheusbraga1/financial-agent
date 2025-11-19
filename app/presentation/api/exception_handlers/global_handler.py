import logging
from typing import Optional
from fastapi import Request, status
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:

    trace_id: Optional[str] = getattr(request.state, "request_id", None)

    logger.error(
        f"Unhandled exception on {request.method} {request.url.path} "

        f"(trace_id={trace_id}): {type(exc).__name__}: {str(exc)}",

        exc_info=True,
    )

    error_response = {
        "code": "internal_error",

        "message": "An unexpected error occurred. Please try again later.",

        "trace_id": trace_id,

        "retryable": True,
    }

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,

        content=error_response,
    )

