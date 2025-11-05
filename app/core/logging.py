import logging
import sys
from app.core.config import get_settings

settings = get_settings()

def setup_logging():
    log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    log_level = getattr(logging, settings.log_level.upper(), logging.INFO)

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter(log_format))

    logging.root.setLevel(log_level)
    logging.root.addHandler(handler)

    logging.getLogger("uvicorn").setLevel(log_level)
    logging.getLogger("fastapi").setLevel(log_level)

    logging.info(f"Logging configurado - Nível: {settings.log_level}")