import logging

import time

import uuid

from typing import Callable

from fastapi import Request, Response

from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = str(uuid.uuid4())

        request.state.request_id = request_id

        start_time = time.time()

        response = await call_next(request)

        process_time = time.time() - start_time

        response.headers["X-Request-ID"] = request_id

        response.headers["X-Process-Time"] = f"{process_time:.3f}s"

        logger.info(

            f"{request.method} {request.url.path} - "

            f"Status: {response.status_code} - "

            f"Time: {process_time:.3f}s - "

            f"ID: {request_id}"

        )

        return response