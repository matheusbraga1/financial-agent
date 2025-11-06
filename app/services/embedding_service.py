from sentence_transformers import SentenceTransformer
from typing import List
import logging
from functools import lru_cache
import hashlib

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class EmbeddingService:
    _instance = None
    _model = None
    _cache_hits = 0
    _cache_misses = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._model is None:
            logger.info(f"Carregando modelo de embedding: {settings.embedding_model}")
            self._model = SentenceTransformer(settings.embedding_model)
            logger.info("Modelo carregado com sucesso")

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
        """
        self._cache_misses += 1
        logger.debug(f"Cache miss - Gerando embedding para texto de {len(normalized_text)} caracteres")
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
            "hit_rate": cache_info.hits / (cache_info.hits + cache_info.misses) if (cache_info.hits + cache_info.misses) > 0 else 0
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

embedding_service = EmbeddingService()