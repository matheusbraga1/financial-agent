class InfrastructureException(Exception):

    def __init__(self, message: str, code: str = "INFRASTRUCTURE_ERROR", original_error: Exception = None):
        self.message = message
        self.code = code
        self.original_error = original_error
        super().__init__(self.message)


class DatabaseException(InfrastructureException):
    def __init__(self, message: str, operation: str = None, original_error: Exception = None):
        self.operation = operation
        super().__init__(message, code="DATABASE_ERROR", original_error=original_error)


class VectorStoreException(InfrastructureException):
    def __init__(self, message: str, operation: str = None, original_error: Exception = None):
        self.operation = operation
        super().__init__(message, code="VECTOR_STORE_ERROR", original_error=original_error)


class ExternalServiceException(InfrastructureException):
    def __init__(self, service_name: str, message: str, original_error: Exception = None):
        self.service_name = service_name
        full_message = f"{service_name}: {message}"
        super().__init__(full_message, code="EXTERNAL_SERVICE_ERROR", original_error=original_error)


class LLMException(InfrastructureException):
    def __init__(self, provider: str, message: str, original_error: Exception = None):
        self.provider = provider
        full_message = f"LLM ({provider}): {message}"
        super().__init__(full_message, code="LLM_ERROR", original_error=original_error)


class ConnectionException(InfrastructureException):
    def __init__(self, service: str, message: str, original_error: Exception = None):
        self.service = service
        full_message = f"Connection to {service} failed: {message}"
        super().__init__(full_message, code="CONNECTION_ERROR", original_error=original_error)
