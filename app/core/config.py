from pydantic_settings import BaseSettings, SettingsConfigDict
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

    llm_provider: str = "hybrid"
    llm_temperature: float = 0.2
    llm_top_p: float = 0.9
    llm_seed: int = 42

    groq_api_key: str = ""
    groq_model: str = "llama-3.1-8b-instant"
    groq_timeout: int = 30
    groq_max_tokens: int = 2048  # Reduced from 4096 to avoid rate limits (6000 TPM free tier)

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "llama3.1:8b"
    ollama_timeout: int = 120

    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dimension: int = 1024

    top_k_results: int = 15
    min_similarity_score: float = 0.12
    fallback_min_score: float = 0.05
    enable_query_expansion: bool = True

    enable_clarification: bool = True
    enable_reranking: bool = True

    log_level: str = "INFO"

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

    password_hash_iterations: int = 200_000
    password_hash_iterations_dev: int = 50_000

    chat_history_max_messages: int = 8

    cors_origins: str = "*"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()
