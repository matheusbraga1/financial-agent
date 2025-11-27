import logging
from typing import Any, Dict, List, Optional

from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def _make_json_serializable(errors: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Converts validation errors to JSON-serializable format.

    Bug Fix: Pydantic validation errors may contain non-serializable objects
    like ValueError instances. This function ensures all error details can be
    safely serialized to JSON.

    Args:
        errors: List of error dictionaries from RequestValidationError.errors()

    Returns:
        List of JSON-serializable error dictionaries
    """
    serializable_errors = []

    for error in errors:
        serializable_error = {}

        for key, value in error.items():
            # Convert non-serializable objects to strings
            if isinstance(value, (str, int, float, bool, type(None))):
                serializable_error[key] = value
            elif isinstance(value, (list, tuple)):
                # Handle lists/tuples (like location in error dict)
                serializable_error[key] = [
                    str(item) if not isinstance(item, (str, int, float, bool, type(None))) else item
                    for item in value
                ]
            elif isinstance(value, dict):
                # Recursively handle nested dicts
                serializable_error[key] = {
                    k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                    for k, v in value.items()
                }
            else:
                # Convert any other object (like ValueError) to string
                serializable_error[key] = str(value)

        serializable_errors.append(serializable_error)

    return serializable_errors


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handles validation errors and returns a standardized JSON response.

    Bug Fix: Ensures all error details are JSON-serializable by converting
    ValueError and other exception objects to strings.

    Args:
        request: FastAPI request object
        exc: Validation error exception

    Returns:
        JSON response with error details
    """
    trace_id: Optional[str] = getattr(request.state, "request_id", None)

    raw_errors = exc.errors()

    # Convert errors to JSON-serializable format
    serializable_errors = _make_json_serializable(raw_errors)

    logger.warning(
        f"Validation error on {request.method} {request.url.path} "
        f"(trace_id={trace_id}): {len(raw_errors)} field(s) failed validation"
    )

    error_response = {
        "code": "validation_error",
        "message": "Validation error in request data",
        "details": serializable_errors,
        "trace_id": trace_id,
        "retryable": False,
    }

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=error_response,
    )