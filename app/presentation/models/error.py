from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict

class ErrorResponse(BaseModel):
    code: str = Field(
        ...,
        description="Stable error code for API contracts",
        examples=["validation_error", "rate_limited", "internal_error"],
    )
    
    message: str = Field(
        ...,
        description="Human-readable error message for display to user",
        examples=["Validation error in request data", "Rate limit exceeded"],
    )

    trace_id: Optional[str] = Field(
        None,
        description="Request tracing ID (matches X-Request-ID header)",
        examples=["a3f1a2c8-2d3e-4b78-9b3d-5a6f7e8d9c0a"],
    )

    details: Optional[Any] = Field(
        None,
        description="Additional error details (when applicable)",
        examples=[
            [
                {
                    "loc": ["body", "email"],

                    "msg": "field required",

                    "type": "value_error.missing",
                }
            ]
        ],
    )

    retryable: Optional[bool] = Field(
        None,
        description="Whether the request can be retried",
        examples=[True, False],
    )

    retry_after: Optional[int] = Field(
        None,
        description="Seconds to wait before retrying (for rate limits)",
        examples=[60, 300],
    )

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "code": "internal_error",
                "message": "An unexpected error occurred. Please try again later.",
                "trace_id": "a3f1a2c8-2d3e-4b78-9b3d-5a6f7e8d9c0a",
                "details": None,
                "retryable": True,
            }
        }
    )