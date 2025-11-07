from __future__ import annotations

from typing import List, Dict, Any

from app.domain.ports import EmbeddingsPort, VectorStorePort


class Retriever:
    def __init__(self, embeddings: EmbeddingsPort, vector_store: VectorStorePort) -> None:
        self._emb = embeddings
        self._vs = vector_store

    def retrieve(
        self,
        question_text: str,
        top_k: int,
        min_score: float,
    ) -> List[Dict[str, Any]]:
        q_vec = self._emb.encode_text(question_text)
        docs = self._vs.search_hybrid(
            query_text=question_text,
            query_vector=q_vec,
            limit=top_k,
            score_threshold=min_score,
        )
        return docs or []

