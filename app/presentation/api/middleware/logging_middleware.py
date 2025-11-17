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
    """Middleware para logging estruturado de requisições"""
    
    def __init__(self, app, logger: StructuredLogger):
        super().__init__(app)
        self.logger = logger
    
    async def dispatch(self, request: Request, call_next):
        # Gera request ID
        request_id = str(uuid.uuid4())
        request_id_var.set(request_id)
        
        # Extrai user_id do token se disponível
        user_id = getattr(request.state, 'user_id', '')
        user_id_var.set(user_id)
        
        # Marca início
        start_time = time.time()
        
        # Processa requisição
        response = await call_next(request)
        
        # Calcula duração
        duration_ms = (time.time() - start_time) * 1000
        
        # Log da requisição
        self.logger.log_request(
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
            client_ip=request.client.host,
            user_agent=request.headers.get('user-agent', ''),
            query_params=dict(request.query_params)
        )
        
        # Adiciona request ID ao header da resposta
        response.headers['X-Request-Id'] = request_id
        
        return response