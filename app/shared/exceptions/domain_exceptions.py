class DomainException(Exception):

    def __init__(self, message: str, code: str = "DOMAIN_ERROR"):
        self.message = message
        self.code = code
        super().__init__(self.message)


class ValidationException(DomainException):
    def __init__(self, message: str, field: str = None):
        self.field = field
        super().__init__(message, code="VALIDATION_ERROR")


class EntityNotFoundException(DomainException):
    def __init__(self, entity_type: str, entity_id: str):
        message = f"{entity_type} with ID '{entity_id}' not found"
        self.entity_type = entity_type
        self.entity_id = entity_id
        super().__init__(message, code="ENTITY_NOT_FOUND")


class BusinessRuleViolation(DomainException):
    def __init__(self, message: str, rule: str = None):
        self.rule = rule
        super().__init__(message, code="BUSINESS_RULE_VIOLATION")


class InsufficientDataException(DomainException):
    def __init__(self, message: str):
        super().__init__(message, code="INSUFFICIENT_DATA")
