from sentence_transformers import SentenceTransformer
from typing import List
import logging
from functools import lru_cache

from app.core.config import get_settings


logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingService:
    """Embedding service with shared model across instances.

    The heavy SentenceTransformer model is shared via class variable
    to avoid memory overhead, while allowing multiple service instances
    for dependency injection.
    """
    # Shared model across all instances (loaded once)
    _shared_model = None
    _model_name = None

    def __init__(self, model_name: str = None):
        """Initialize embedding service.

        Args:
            model_name: Model name (defaults to settings)
        """
        model_name = model_name or settings.embedding_model

        # Lazy load the shared model if needed
        if EmbeddingService._shared_model is None or EmbeddingService._model_name != model_name:
            logger.info(f"Carregando modelo de embedding: {model_name}")
            EmbeddingService._shared_model = SentenceTransformer(model_name)
            EmbeddingService._model_name = model_name
            logger.info("Modelo carregado com sucesso")

        self._model = EmbeddingService._shared_model

    def encode_text(self, text: str, use_cache: bool = True) -> List[float]:
        """
        Gera embedding para um texto com suporte a cache.

        Args:
            text: Texto para gerar embedding
            use_cache: Se True, usa cache LRU para textos repetidos

        Returns:
            List[float]: Vetor de embedding
        """
        if not text or not text.strip():
            raise ValueError("Texto não pode estar vazio")

        if use_cache:
            normalized_text = text.strip().lower()
            cached_result = self._encode_text_cached(normalized_text)
            return list(cached_result)

        logger.debug(f"Gerando embedding para texto de {len(text)} caracteres (sem cache)")
        vector = self._model.encode(text).tolist()
        return vector

    @lru_cache(maxsize=1000)
    def _encode_text_cached(self, normalized_text: str) -> tuple:
        """
        Método interno com cache LRU para embeddings.
        Retorna tuple para ser hashable pelo lru_cache.

        Note: Cache statistics are tracked by lru_cache itself via cache_info()
        """
        logger.debug(
            f"Gerando embedding para texto de {len(normalized_text)} caracteres"
        )
        vector = self._model.encode(normalized_text).tolist()
        return tuple(vector)

    def get_cache_stats(self) -> dict:
        """Retorna estatísticas do cache."""
        cache_info = self._encode_text_cached.cache_info()
        return {
            "hits": cache_info.hits,
            "misses": cache_info.misses,
            "size": cache_info.currsize,
            "maxsize": cache_info.maxsize,
            "hit_rate": cache_info.hits
            / (cache_info.hits + cache_info.misses)
            if (cache_info.hits + cache_info.misses) > 0
            else 0,
        }

    def clear_cache(self):
        """Limpa o cache de embeddings."""
        self._encode_text_cached.cache_clear()
        logger.info("Cache de embeddings limpo")

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        logger.debug(f"Gerando embeddings em batch para {len(texts)} textos")
        vectors = self._model.encode(texts).tolist()
        return vectors

    def encode_document(self, title: str, content: str, title_weight: int = 3) -> List[float]:
        if not title or not content:
            raise ValueError("Título e conteúdo não podem estar vazios")

        combined_text = " ".join([title] * title_weight) + ". " + content

        logger.debug(f"Gerando embedding para documento: {title[:50]}...")
        return self.encode_text(combined_text)


# Singleton removed - use dependency injection via get_embedding_service() in api/deps.py
# For backward compatibility during migration, create instance if needed
_global_instance = None


def get_embedding_service_instance() -> EmbeddingService:
    """Get or create global embedding service instance.

    This is a temporary helper for backward compatibility.
    Prefer using FastAPI dependency injection via api/deps.py
    """
    global _global_instance
    if _global_instance is None:
        _global_instance = EmbeddingService()
    return _global_instance

