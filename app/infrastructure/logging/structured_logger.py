import logging
import json
import sys
from typing import Any, Dict, Optional
from datetime import datetime
import traceback
from contextvars import ContextVar
from pythonjsonlogger import jsonlogger

request_id_var: ContextVar[str] = ContextVar('request_id', default='')
user_id_var: ContextVar[str] = ContextVar('user_id', default='')


class LogSymbols:
    """Símbolos para facilitar visualização dos logs."""

    # Status
    SUCCESS = "✓"
    ERROR = "✗"
    WARNING = "⚠"
    INFO = "ℹ"

    # Operações
    START = "→"
    END = "←"
    PROCESS = "⚙"

    # Recursos
    DATABASE = "🗄"
    API = "🌐"
    AUTH = "🔐"
    CACHE = "💾"
    LLM = "🤖"
    SEARCH = "🔍"
    USER = "👤"
    SESSION = "📝"
    MESSAGE = "💬"

class ReadableFormatter(logging.Formatter):
    """Custom formatter that displays structured data in a readable format."""

    def format(self, record):
        # Base message
        base = f"{self.formatTime(record)} | {record.levelname:8} | {record.getMessage()}"

        # Add extra fields in a readable way
        extra_fields = []
        skip_fields = {'message', 'asctime', 'created', 'filename', 'funcName',
                      'levelname', 'levelno', 'lineno', 'module', 'msecs',
                      'name', 'pathname', 'process', 'processName', 'relativeCreated',
                      'stack_info', 'thread', 'threadName', 'exc_info', 'exc_text',
                      'msg', 'args', 'timestamp', 'request_id', 'user_id'}

        for key, value in record.__dict__.items():
            if key not in skip_fields and not key.startswith('_'):
                if isinstance(value, float):
                    extra_fields.append(f"{key}={value:.2f}")
                elif isinstance(value, (list, dict)):
                    continue  # Skip complex objects for readability
                elif value is not None and value != '':
                    extra_fields.append(f"{key}={value}")

        if extra_fields:
            base += f" | {', '.join(extra_fields)}"

        return base


class StructuredLogger:

    def __init__(
        self,
        name: str,
        level: str = "INFO",
        log_format: str = "readable"
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
        elif log_format == "readable":
            formatter = ReadableFormatter(datefmt='%H:%M:%S')
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

    # ===== AUTH OPERATIONS =====

    def log_auth_attempt(self, operation: str, username: str, **kwargs):
        """Log authentication attempt."""
        self.info(
            f"{LogSymbols.AUTH} AUTH {LogSymbols.START} {operation}",
            operation=operation,
            username=username,
            **kwargs
        )

    def log_auth_success(self, operation: str, user_id: int, username: str, **kwargs):
        """Log successful authentication."""
        self.info(
            f"{LogSymbols.AUTH} AUTH {LogSymbols.SUCCESS} {operation} successful",
            operation=operation,
            user_id=user_id,
            username=username,
            **kwargs
        )

    def log_auth_failure(self, operation: str, username: str, reason: str, **kwargs):
        """Log failed authentication."""
        self.warning(
            f"{LogSymbols.AUTH} AUTH {LogSymbols.ERROR} {operation} failed: {reason}",
            operation=operation,
            username=username,
            reason=reason,
            **kwargs
        )

    # ===== DATABASE OPERATIONS =====

    def log_db_operation(self, operation: str, table: str, **kwargs):
        """Log database operation."""
        self.debug(
            f"{LogSymbols.DATABASE} DB {operation} on {table}",
            operation=operation,
            table=table,
            **kwargs
        )

    def log_db_success(self, operation: str, table: str, affected: int = 0, **kwargs):
        """Log successful database operation."""
        self.info(
            f"{LogSymbols.DATABASE} DB {LogSymbols.SUCCESS} {operation} on {table} ({affected} rows)",
            operation=operation,
            table=table,
            rows_affected=affected,
            **kwargs
        )

    def log_db_error(self, operation: str, table: str, error: str, **kwargs):
        """Log database error."""
        self.error(
            f"{LogSymbols.DATABASE} DB {LogSymbols.ERROR} {operation} on {table}: {error}",
            operation=operation,
            table=table,
            error=error,
            **kwargs
        )

    # ===== CHAT/SESSION OPERATIONS =====

    def log_chat_request(self, session_id: str, question_length: int, authenticated: bool, **kwargs):
        """Log incoming chat request."""
        auth_status = f"{LogSymbols.USER} authenticated" if authenticated else "anonymous"
        self.info(
            f"{LogSymbols.MESSAGE} CHAT {LogSymbols.START} New request ({auth_status})",
            session_id=session_id,
            question_length=question_length,
            authenticated=authenticated,
            **kwargs
        )

    def log_chat_response(
        self,
        session_id: str,
        answer_length: int,
        sources_count: int,
        confidence: float,
        model_used: str,
        cached: bool = False,
        **kwargs
    ):
        """Log chat response."""
        cache_status = f"{LogSymbols.CACHE} from cache" if cached else "generated"
        self.info(
            f"{LogSymbols.MESSAGE} CHAT {LogSymbols.SUCCESS} Response sent ({cache_status})",
            session_id=session_id,
            answer_length=answer_length,
            sources_count=sources_count,
            confidence=round(confidence, 2),
            model_used=model_used,
            cached=cached,
            **kwargs
        )

    def log_session_created(self, session_id: str, user_id: Optional[str] = None, **kwargs):
        """Log session creation."""
        self.info(
            f"{LogSymbols.SESSION} SESSION {LogSymbols.SUCCESS} Created",
            session_id=session_id,
            user_id=user_id,
            **kwargs
        )

    def log_message_persisted(self, session_id: str, role: str, message_id: Optional[int] = None, **kwargs):
        """Log message persistence."""
        self.info(
            f"{LogSymbols.DATABASE} MESSAGE {LogSymbols.SUCCESS} Persisted ({role})",
            session_id=session_id,
            role=role,
            message_id=message_id,
            **kwargs
        )

    # ===== LLM OPERATIONS =====

    def log_llm_request(self, provider: str, model: str, prompt_length: int, **kwargs):
        """Log LLM request."""
        self.info(
            f"{LogSymbols.LLM} LLM {LogSymbols.START} Request to {provider}/{model}",
            provider=provider,
            model=model,
            prompt_length=prompt_length,
            **kwargs
        )

    def log_llm_response(self, provider: str, model: str, tokens: int, duration_ms: float, **kwargs):
        """Log LLM response."""
        self.info(
            f"{LogSymbols.LLM} LLM {LogSymbols.SUCCESS} Response from {provider}/{model} ({tokens} tokens, {duration_ms:.0f}ms)",
            provider=provider,
            model=model,
            tokens=tokens,
            duration_ms=duration_ms,
            **kwargs
        )

    def log_llm_fallback(self, from_provider: str, to_provider: str, reason: str, **kwargs):
        """Log LLM fallback."""
        self.warning(
            f"{LogSymbols.LLM} LLM {LogSymbols.WARNING} Fallback: {from_provider} → {to_provider} ({reason})",
            from_provider=from_provider,
            to_provider=to_provider,
            reason=reason,
            **kwargs
        )

    def log_llm_error(self, provider: str, model: str, error: str, **kwargs):
        """Log LLM error."""
        self.error(
            f"{LogSymbols.LLM} LLM {LogSymbols.ERROR} Error from {provider}/{model}: {error}",
            provider=provider,
            model=model,
            error=error,
            **kwargs
        )

    # ===== SEARCH/RAG OPERATIONS =====

    def log_search_start(self, query: str, top_k: int, **kwargs):
        """Log search start."""
        self.info(
            f"{LogSymbols.SEARCH} SEARCH {LogSymbols.START} Query: '{query[:50]}...' (top_k={top_k})",
            query=query[:100],
            top_k=top_k,
            **kwargs
        )

    def log_search_results(self, results_count: int, top_score: float, duration_ms: float, **kwargs):
        """Log search results."""
        self.info(
            f"{LogSymbols.SEARCH} SEARCH {LogSymbols.SUCCESS} Found {results_count} results (top_score={top_score:.2f}, {duration_ms:.0f}ms)",
            results_count=results_count,
            top_score=top_score,
            duration_ms=duration_ms,
            **kwargs
        )

    # ===== CACHE OPERATIONS =====

    def log_cache_hit(self, key: str, **kwargs):
        """Log cache hit."""
        self.info(
            f"{LogSymbols.CACHE} CACHE {LogSymbols.SUCCESS} Hit: {key[:50]}",
            cache_key=key,
            cache_hit=True,
            **kwargs
        )

    def log_cache_miss(self, key: str, **kwargs):
        """Log cache miss."""
        self.debug(
            f"{LogSymbols.CACHE} CACHE {LogSymbols.INFO} Miss: {key[:50]}",
            cache_key=key,
            cache_hit=False,
            **kwargs
        )

    def log_cache_set(self, key: str, ttl: int, **kwargs):
        """Log cache set."""
        self.debug(
            f"{LogSymbols.CACHE} CACHE {LogSymbols.SUCCESS} Set: {key[:50]} (TTL={ttl}s)",
            cache_key=key,
            ttl=ttl,
            **kwargs
        )