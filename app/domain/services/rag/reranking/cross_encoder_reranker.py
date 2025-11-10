"""CrossEncoder reranking for document retrieval.

Uses a CrossEncoder model to rerank documents based on semantic similarity
to the query, improving precision over pure vector search.
"""

import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    """Reranks documents using CrossEncoder for better precision.

    The CrossEncoder model scores (query, document) pairs directly,
    which is more accurate than comparing embeddings separately.
    """

    def __init__(self, model_name: str = "cross-encoder/ms-marco-MiniLM-L-6-v2"):
        """Initialize CrossEncoder reranker.

        Args:
            model_name: HuggingFace model name for CrossEncoder
        """
        self._model = None
        self._model_name = model_name
        self._enabled = True
        logger.info(f"CrossEncoderReranker initialized (lazy loading: {model_name})")

    def _load_model(self):
        """Lazy load the CrossEncoder model."""
        if self._model is None and self._enabled:
            try:
                from sentence_transformers import CrossEncoder

                logger.info(f"Loading CrossEncoder model: {self._model_name}")
                self._model = CrossEncoder(self._model_name)
                logger.info("CrossEncoder loaded successfully")
            except Exception as e:
                logger.warning(f"Failed to load CrossEncoder: {e}. Reranking disabled.")
                self._enabled = False
        return self._model

    def is_enabled(self) -> bool:
        """Check if reranking is enabled."""
        return self._enabled

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        original_weight: float = 0.3,
        rerank_weight: float = 0.7,
    ) -> List[Dict[str, Any]]:
        """Rerank documents using CrossEncoder.

        Args:
            query: User query
            documents: List of documents to rerank
            original_weight: Weight for original retrieval score (0-1)
            rerank_weight: Weight for reranking score (0-1)

        Returns:
            Reranked list of documents with updated scores

        Note:
            Scores are normalized to [0, 1] range and clamped.
        """
        model = self._load_model()
        if model is None or not documents:
            return documents

        # Prepare (query, doc) pairs for CrossEncoder
        pairs = []
        for doc in documents:
            content_preview = doc.get("content", "")[:500] if doc.get("content") else ""
            text = f"{doc.get('title', '')}. {content_preview}"
            pairs.append([query, text])

        try:
            # Get raw scores from CrossEncoder
            rerank_scores = model.predict(pairs)

            # Normalize scores to [0, 1] using sigmoid
            import numpy as np
            normalized_scores = 1 / (1 + np.exp(-np.array(rerank_scores)))

            logger.debug(
                f"CrossEncoder scores - Original: min={rerank_scores.min():.2f}, "
                f"max={rerank_scores.max():.2f}"
            )
            logger.debug(
                f"Normalized scores: min={normalized_scores.min():.2f}, "
                f"max={normalized_scores.max():.2f}"
            )

            # Combine original and reranking scores
            for doc, score in zip(documents, normalized_scores):
                original_score = doc.get("score", 0.0)
                combined_score = (original_score * original_weight) + (float(score) * rerank_weight)
                doc["score"] = max(0.0, min(1.0, combined_score))

            # Sort by new scores
            documents.sort(key=lambda x: x.get("score", 0.0), reverse=True)

            logger.debug(
                f"Reranking completed - {len(documents)} documents reordered"
            )

        except Exception as e:
            logger.warning(f"Error during reranking: {e}. Returning original order.")

        return documents
