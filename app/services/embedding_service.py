from sentence_transformers import SentenceTransformer
from typing import List
import logging

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class EmbeddingService:
    _instance = None
    _model = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._model is None:
            logger.info(f"Carregando modelo de embedding: {settings.embedding_model}")
            self._model = SentenceTransformer(settings.embedding_model)
            logger.info("Modelo carregado com sucesso")

    def encode_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            raise ValueError("Texto não pode estar vazio")

        logger.debug(f"Gerando embedding para texto de {len(text)} caracteres")
        vector = self._model.encode(text).tolist()
        return vector

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        logger.debug(f"Gerando embeddings em batch para {len(texts)} textos")
        vectors = self._model.encode(texts).tolist()
        return vectors

    def encode_document(self, title: str, content: str, title_weight: int = 3) -> List[float]:
        if not title or not content:
            raise ValueError("Título e conteúdo não podem estar vazios")

        # Combinar título (com peso) + conteúdo
        combined_text = " ".join([title] * title_weight) + ". " + content

        logger.debug(f"Gerando embedding para documento: {title[:50]}...")
        return self.encode_text(combined_text)

embedding_service = EmbeddingService()