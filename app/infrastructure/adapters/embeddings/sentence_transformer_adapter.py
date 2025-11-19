from typing import List, Dict
import logging
from functools import lru_cache
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

class SentenceTransformerAdapter:
    _model_cache: Dict[str, SentenceTransformer] = {}

    def __init__(
        self,
        model_name: str = "intfloat/multilingual-e5-large",
        device: str = "cpu",
        normalize: bool = True,
    ):
        self.model_name = model_name
        self.device = device
        self.normalize = normalize

        if model_name not in self._model_cache:
            logger.info(f"Carregando modelo de embeddings: {model_name}")

            self._model_cache[model_name] = SentenceTransformer(
                model_name,
                device=device,
            )

            logger.info(f"Modelo carregado: {model_name} ({device})")

        self.model = self._model_cache[model_name]

    @lru_cache(maxsize=1024)
    def encode_text(self, text: str) -> List[float]:
        if not text or not text.strip():
            return [0.0] * self.model.get_sentence_embedding_dimension()

        embedding = self.model.encode(
            text,
            normalize_embeddings=self.normalize,
            show_progress_bar=False,
        )

        return embedding.tolist()

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        if not texts:
            return []

        clean_texts = [
            text if text and text.strip() else " "
            for text in texts
        ]

        embeddings = self.model.encode(
            clean_texts,
            normalize_embeddings=self.normalize,
            show_progress_bar=len(texts) > 100,
            batch_size=32,
        )

        return embeddings.tolist()

    def encode_document(
        self,
        title: str,
        content: str,
        title_weight: int = 3
    ) -> List[float]:
        title_repeated = " ".join([title] * title_weight)
        combined_text = f"{title_repeated} {content}"

        return self.encode_text(combined_text)

    def get_dimension(self) -> int:
        return self.model.get_sentence_embedding_dimension()
