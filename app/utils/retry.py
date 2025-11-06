from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log
)
import logging

logger = logging.getLogger(__name__)

def retry_on_connection_error(max_attempts: int = 3):
    """
    Decorator para retry em erros de conexão.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ConnectionError, TimeoutError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )

def retry_on_any_error(max_attempts: int = 3):
    """
    Decorator para retry em qualquer exceção.
    """
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )

def retry_database_operation(max_attempts: int = 3):
    """
    Decorator específico para operações de banco de dados.
    """
    from sqlalchemy.exc import OperationalError, DBAPIError

    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=1, max=5),
        retry=retry_if_exception_type((OperationalError, DBAPIError)),
        before_sleep=before_sleep_log(logger, logging.WARNING)
    )
