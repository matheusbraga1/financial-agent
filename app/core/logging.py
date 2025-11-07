import logging
import sys
from app.core.config import get_settings


settings = get_settings()


def setup_logging():
    log_format = "%(asctime)s - %(levelname)s - %(message)s"
    level_name = (settings.log_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format))

    logging.root.handlers = []
    logging.root.addHandler(handler)
    logging.root.setLevel(level)

    # Reduce noise from third-party libs if necessary
    logging.getLogger("uvicorn").setLevel(level)
    logging.getLogger("uvicorn.error").setLevel(level)
    logging.getLogger("uvicorn.access").setLevel(level)

    logging.info(f"Logging configurado - Nível: {level_name}")

