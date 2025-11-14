import logging
from typing import Optional, List
from fastapi import Request, status
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

logger = logging.getLogger(__name__)

async def rate_limit_exception_handler(
    request: Request,

    exc: RateLimitExceeded,

    default_limits: Optional[List[str]] = None,
) -> JSONResponse:
    trace_id: Optional[str] = getattr(request.state, "request_id", None)

    logger.warning(
        f"Rate limit exceeded for {request.client.host} on "

        f"{request.method} {request.url.path} (trace_id={trace_id})"
    )

    retry_after = 60

    error_response = {
        "code": "rate_limited",

        "message": f"Rate limit exceeded: {exc.detail}",

        "trace_id": trace_id,

        "retryable": True,

        "retry_after": retry_after,
    }
    
    headers = {
        "Retry-After": str(retry_after),
    }
    
    if default_limits:
        headers["X-RateLimit-Limit"] = str(default_limits)

    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,

        content=error_response,

        headers=headers,
    )