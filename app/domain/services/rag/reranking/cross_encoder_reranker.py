from typing import List, Dict, Any, Optional
import logging
import torch
from sentence_transformers import CrossEncoder

logger = logging.getLogger(__name__)


class CrossEncoderReranker:
    _model_cache: Dict[str, CrossEncoder] = {}

    def __init__(
        self,
        model_name: str = "jinaai/jina-reranker-v2-base-multilingual",
        device: str = "cpu",
    ):
        self.model_name = model_name
        self.device = device

        if model_name not in self._model_cache:
            logger.info(f"Carregando cross-encoder: {model_name}")

            try:
                if "jina" in model_name.lower():
                    # Força float32 para evitar erro "Got unsupported ScalarType BFloat16"
                    self._model_cache[model_name] = CrossEncoder(
                        model_name,
                        device=device,
                        max_length=512,
                        trust_remote_code=True,
                        automodel_args={"dtype": torch.float32},
                    )
                else:
                    self._model_cache[model_name] = CrossEncoder(
                        model_name,
                        device=device,
                        max_length=512,
                    )
                logger.info(f"Cross-encoder carregado: {model_name}")
            except Exception as e:
                logger.error(f"Erro ao carregar cross-encoder: {e}")
                raise

        self.model = self._model_cache[model_name]

    def rerank(
        self,
        query: str,
        documents: List[Dict[str, Any]],
        top_k: Optional[int] = None,
        original_weight: float = 0.3,
        rerank_weight: float = 0.7,
    ) -> List[Dict[str, Any]]:
        if not documents:
            return []

        if len(documents) == 1:
            return documents

        try:
            pairs = []
            for doc in documents:
                title = doc.get("title", "")
                content = doc.get("content", "")

                doc_text = f"{title} {content}"[:500]

                pairs.append([query, doc_text])

            logger.debug(f"Reranking {len(pairs)} documentos com cross-encoder")

            rerank_scores = self.model.predict(
                pairs,
                show_progress_bar=False,
                batch_size=32,
            )

            import numpy as np
            normalized_rerank_scores = 1 / (1 + np.exp(-rerank_scores))

            reranked_docs = []

            for i, doc in enumerate(documents):
                original_score = doc.get("score", 0.0)
                rerank_score = float(normalized_rerank_scores[i])

                combined_score = (
                    original_weight * original_score +
                    rerank_weight * rerank_score
                )

                reranked_doc = doc.copy()
                reranked_doc["score"] = combined_score
                reranked_doc["original_score"] = original_score
                reranked_doc["rerank_score"] = rerank_score

                reranked_docs.append(reranked_doc)

            reranked_docs.sort(key=lambda x: x["score"], reverse=True)

            if top_k:
                reranked_docs = reranked_docs[:top_k]

            if len(reranked_docs) >= 3:
                logger.debug(
                    f"Reranking concluído - top 3: "
                    f"1) {reranked_docs[0].get('title', '')[:30]} (score: {reranked_docs[0]['score']:.3f}), "
                    f"2) {reranked_docs[1].get('title', '')[:30]} (score: {reranked_docs[1]['score']:.3f}), "
                    f"3) {reranked_docs[2].get('title', '')[:30]} (score: {reranked_docs[2]['score']:.3f})"
                )

            return reranked_docs

        except Exception as e:
            logger.error(f"Erro no reranking: {e}", exc_info=True)
            return documents