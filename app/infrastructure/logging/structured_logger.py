import logging
import json
import sys
from typing import Any, Dict
from datetime import datetime
import traceback
from contextvars import ContextVar
from pythonjsonlogger import jsonlogger

request_id_var: ContextVar[str] = ContextVar('request_id', default='')
user_id_var: ContextVar[str] = ContextVar('user_id', default='')

class StructuredLogger:

    def __init__(
        self,
        name: str,
        level: str = "INFO",
        log_format: str = "json"
    ):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, level.upper()))

        self.logger.handlers.clear()

        handler = logging.StreamHandler(sys.stdout)

        if log_format == "json":
            formatter = jsonlogger.JsonFormatter(
                '%(timestamp)s %(level)s %(name)s %(message)s',
                rename_fields={'levelname': 'level'}
            )
        else:
            formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
        
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

        self.logger.propagate = False

    def _add_context(self, extra: Dict[str, Any]) -> Dict[str, Any]:
        context = {
            'timestamp': datetime.utcnow().isoformat(),
            'request_id': request_id_var.get(),
            'user_id': user_id_var.get(),
            **extra
        }
        return {k: v for k, v in context.items() if v}

    def debug(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.debug(message, extra=extra)
    
    def info(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.info(message, extra=extra)

    def warning(self, message: str, **kwargs):
        extra = self._add_context(kwargs)
        self.logger.warning(message, extra=extra)

    def error(self, message: str, exc_info=None, **kwargs):
        extra = self._add_context(kwargs)
        
        if exc_info:
            extra['stack_trace'] = traceback.format_exc()
        
        self.logger.error(message, extra=extra, exc_info=exc_info)

    def critical(self, message: str, exc_info=None, **kwargs):
        extra = self._add_context(kwargs)
        
        if exc_info:
            extra['stack_trace'] = traceback.format_exc()
        
        self.logger.critical(message, extra=extra, exc_info=exc_info)

    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        **kwargs
    ):
        self.info(
            f"HTTP Request",
            method=method,
            path=path,
            status_code=status_code,
            duration_ms=duration_ms,
            **kwargs
        )

    def log_database_query(
        self,
        query: str,
        duration_ms: float,
        rows_affected: int = 0,
        **kwargs
    ):
        self.debug(
            "Database Query",
            query=query[:200],
            duration_ms=duration_ms,
            rows_affected=rows_affected,
            **kwargs
        )
    
    def log_external_api_call(
        self,
        service: str,
        endpoint: str,
        method: str,
        status_code: int,
        duration_ms: float,
        **kwargs
    ):
        self.info(
            f"External API Call",
            service=service,
            endpoint=endpoint,
            method=method,
            status_code=status_code,
            duration_ms=duration_ms,
            **kwargs
        )