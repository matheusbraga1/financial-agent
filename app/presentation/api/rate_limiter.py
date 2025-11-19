"""
Rate limiter configuration for the API.

This module provides a centralized rate limiter instance that can be
imported and used across different endpoints.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Request


def get_real_client_ip(request: Request) -> str:
    """
    Get real client IP considering proxy headers.

    Args:
        request: FastAPI Request object

    Returns:
        Client IP address as string
    """
    if x_forwarded_for := request.headers.get("X-Forwarded-For"):
        return x_forwarded_for.split(",")[0].strip()

    if x_real_ip := request.headers.get("X-Real-IP"):
        return x_real_ip.strip()

    return get_remote_address(request)


# Create a global limiter instance
limiter = Limiter(
    key_func=get_real_client_ip,
    default_limits=["50/minute"],
)
