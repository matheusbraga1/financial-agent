import logging

from typing import Optional

from fastapi import Request, status

from fastapi.exceptions import RequestValidationError

from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

async def validation_exception_handler(

    request: Request, exc: RequestValidationError

) -> JSONResponse:
    trace_id: Optional[str] = getattr(request.state, "request_id", None)
    
    errors = exc.errors()
    
    logger.warning(
        f"Validation error on {request.method} {request.url.path} "

        f"(trace_id={trace_id}): {len(errors)} field(s) failed validation"
    )
    
    error_response = {
        "code": "validation_error",

        "message": "Validation error in request data",

        "details": errors,

        "trace_id": trace_id,

        "retryable": False,
    }
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,

        content=error_response,
    )