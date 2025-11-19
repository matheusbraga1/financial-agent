from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, validator
from functools import lru_cache
import os

class Settings(BaseSettings):
    app_name: str = "Financial Agent"
    app_version: str = "2.0.0"
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
    groq_max_tokens: int = 2048

    ollama_host: str = "http://localhost:11434"
    ollama_model: str = "qwen2.5:3b"
    ollama_timeout: int = 120

    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_dimension: int = 1024

    top_k_results: int = 15
    min_similarity_score: float = 0.12
    fallback_min_score: float = 0.05
    enable_query_expansion: bool = True
    enable_clarification: bool = True
    enable_reranking: bool = True

    cross_encoder_model: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    reranking_original_weight: float = 0.3
    reranking_cross_encoder_weight: float = 0.7

    mmr_lambda: float = 0.7

    hybrid_vector_weight: float = 0.7
    hybrid_text_weight: float = 0.3
    hybrid_rrf_k: int = 60

    anchor_gating_threshold: float = 0.3

    log_level: str = "INFO"
    log_format: str = "json"


    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""
    redis_ssl: bool = False
    redis_max_connections: int = 50
    cache_default_ttl: int = 3600


    jwt_secret: str = Field(
        default="dev-secret-key-change-in-production-min-32-chars",
        description="JWT secret key - MUST be set via JWT_SECRET env var in production"
    )
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7


    rate_limit_enabled: bool = True
    rate_limit_requests: int = 50
    rate_limit_window: int = 60
    rate_limit_strategy: str = "sliding_window"

    password_hash_iterations: int = 200_000
    password_hash_iterations_dev: int = 50_000

    glpi_db_host: str = "localhost"
    glpi_db_port: int = 3306
    glpi_db_name: str = "glpi"
    glpi_db_user: str = "glpi"
    glpi_db_password: str = Field(
        default="",
        description="GLPI database password - MUST be set via GLPI_DB_PASSWORD env var"
    )
    glpi_db_prefix: str = "glpi_"

    @validator('jwt_secret')
    def validate_jwt_secret(cls, v, values):
        if len(v) < 32:
            raise ValueError(
                'JWT_SECRET must be at least 32 characters long. '
                'Please set a strong secret via environment variable.'
            )

        if not values.get('debug', False) and v == "dev-secret-key-change-in-production-min-32-chars":
            raise ValueError(
                'SECURITY ERROR: Cannot use default JWT_SECRET in production! '
                'Set JWT_SECRET environment variable with a secure random value. '
                'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
            )

        return v

    @validator('glpi_db_password')
    def validate_glpi_password(cls, v, values):
        if not v and not values.get('debug', False):
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                "GLPI_DB_PASSWORD is not set. "
                "GLPI functionality may not work correctly."
            )
        return v
    
    glpi_sync_interval_hours: int = 24
    glpi_min_content_length: int = 50
    
    chat_history_max_messages: int = 8
    chat_history_retention_days: int = 90
    chat_history_purge_interval_sec: int = 3600
    
    stream_finalize_timeout: float = 1.0
    
    cors_origins: str = "*"
    
    chunk_size: int = 1000
    chunk_overlap: int = 200
    min_chunk_size: int = 100
    
    qa_memory_min_confidence: float = 0.55
    qa_memory_min_answer_length: int = 40
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )

@lru_cache()
def get_settings() -> Settings:
    return Settings()

settings = get_settings()