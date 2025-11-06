from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    app_name: str = "Chat IA GLPI"
    app_version: str = "1.0.0"
    debug: bool = False

    host: str = "0.0.0.0"
    port: int = 8000

    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "artigos_glpi"

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"

    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dimension: int = 384

    top_k_results: int = 10
    min_similarity_score: float = 0.18

    log_level: str = "INFO"

    # Auth/JWT
    jwt_secret: str = "change-me-in-.env"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 60

    glpi_db_host: str = "localhost"
    glpi_db_port: int = 3306
    glpi_db_name: str = "glpi"
    glpi_db_user: str = "glpi"
    glpi_db_password: str = "glpi_password"
    glpi_db_prefix: str = "glpi_"

    glpi_sync_interval_hours: int = 24
    glpi_min_content_length: int = 50

    class Config:
        env_file = ".env"
        case_sensitive = False

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
