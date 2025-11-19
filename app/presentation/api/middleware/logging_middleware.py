import time
import uuid
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from app.infrastructure.logging.structured_logger import (
    StructuredLogger,
    request_id_var,
    user_id_var
)

class LoggingMiddleware(BaseHTTPMiddleware):

    def __init__(self, app, logger: StructuredLogger):
        super().__init__(app)
        self.logger = logger
    
    async def dispatch(self, request: Request, call_next):
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)

        user_id = getattr(request.state, 'user_id', '')
        user_id_var.set(user_id)

        start_time = time.time()

        response = await call_next(request)

        duration_ms = (time.time() - start_time) * 1000

        self.logger.log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host,
            user_agent=request.headers.get('user-agent', ''),
            query_params=dict(request.query_params)
        )

        response.headers['X-Request-Id'] = request_id

        return response