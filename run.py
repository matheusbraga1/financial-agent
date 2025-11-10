import uvicorn
from app.core.config import get_settings
from app.core.logging import setup_logging

settings = get_settings()

if __name__ == "__main__":
    setup_logging()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.log_level.lower(),
        log_config=None,
    )
