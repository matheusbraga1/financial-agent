"""Vector Store Service - Refactored with clean architecture.

This service orchestrates:
- QdrantAdapter: Pure Qdrant operations
- HybridSearchStrategy: Search scoring logic
- CrossEncoderReranker: Result reranking
- MMR Diversification: Result diversity

All business logic is now separated from infrastructure code.
"""

import logging
import uuid
from typing import List, Dict, Any, Optional

from app.core.config import get_settings
from app.models.document import DocumentCreate
from app.infrastructure.adapters.vector_store import QdrantAdapter
from app.domain.services.rag.retrieval import HybridSearchStrategy, apply_mmr_diversification
from app.domain.services.rag.reranking import CrossEncoderReranker

logger = logging.getLogger(__name__)
settings = get_settings()


class VectorStoreService:
    """Vector store service with clean separation of concerns.

    Responsibilities:
    - Document storage and retrieval
    - Hybrid search orchestration
    - Reranking and diversification
    - Usage tracking and feedback
    """

    def __init__(
        self,
        qdrant_adapter: Optional[QdrantAdapter] = None,
        search_strategy: Optional[HybridSearchStrategy] = None,
        reranker: Optional[CrossEncoderReranker] = None,
        enable_reranking: bool = True,
    ):
        """Initialize vector store service.

        Args:
            qdrant_adapter: Qdrant client adapter
            search_strategy: Hybrid search strategy
            reranker: CrossEncoder reranker
            enable_reranking: Enable/disable reranking
        """
        # Dependency injection with sensible defaults
        self.qdrant = qdrant_adapter or QdrantAdapter()
        self.search = search_strategy or HybridSearchStrategy()
        self.reranker = reranker or CrossEncoderReranker()
        self.enable_reranking = enable_reranking and getattr(settings, "enable_reranking", True)

        logger.info(
            f"VectorStoreService initialized (reranking: {self.enable_reranking})"
        )

    @property
    def collection_name(self) -> str:
        """Get collection name from adapter."""
        return self.qdrant.collection_name

    @property
    def client(self):
        """Get underlying Qdrant client for direct operations."""
        return self.qdrant.client

    def _ensure_collection(self) -> None:
        """Ensure collection exists (delegates to adapter)."""
        self.qdrant.ensure_collection()

    def add_document(
        self,
        document: DocumentCreate,
        vector: List[float],
        document_id: Optional[str] = None,
    ) -> str:
        """Add document to vector store.

        Args:
            document: Document to add
            vector: Embedding vector
            document_id: Optional document ID (generates UUID if None)

        Returns:
            Document ID
        """
        doc_id = document_id or str(uuid.uuid4())

        metadata = document.metadata or {}

        # Build search text for BM25 (title weighted 3x)
        search_text = f"{document.title} {document.title} {document.title} {document.content}"

        # Handle departments field
        departments = metadata.get("departments") or (
            [metadata.get("department")] if metadata.get("department") else []
        )

        # Build payload
        payload = {
            "title": document.title,
            "category": document.category,
            "content": document.content,
            "search_text": search_text,
            "metadata": metadata,
            "department": metadata.get("department"),
            "departments": departments,
            "doc_type": metadata.get("doc_type"),
            "tags": metadata.get("tags", []),
            "source_id": metadata.get("source_id"),
            "origin": metadata.get("origin"),
            "confidence": metadata.get("confidence"),
            # Feedback fields
            "helpful_votes": int(metadata.get("helpful_votes", 0) or 0),
            "complaints": int(metadata.get("complaints", 0) or 0),
            "usage_count": int(metadata.get("usage_count", 0) or 0),
            "last_used_at": metadata.get("last_used_at"),
        }

        self.qdrant.upsert_point(doc_id, vector, payload)

        logger.info(f"Document '{document.title}' added with ID: {doc_id}")
        return doc_id

    def search_similar(
        self,
        query_vector: List[float],
        limit: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Pure vector similarity search.

        Args:
            query_vector: Query embedding
            limit: Max results
            score_threshold: Min score

        Returns:
            List of matching documents
        """
        limit = limit or settings.top_k_results
        score_threshold = score_threshold or settings.min_similarity_score

        results = self.qdrant.vector_search(
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold,
        )

        documents = []
        for result in results:
            documents.append({
                "id": result.id,
                "score": result.score,
                "title": result.payload.get("title"),
                "category": result.payload.get("category"),
                "content": result.payload.get("content"),
                "metadata": result.payload.get("metadata", {}),
            })

        logger.debug(f"Found {len(documents)} similar documents")
        return documents

    def search_hybrid(
        self,
        query_text: str,
        query_vector: List[float],
        limit: Optional[int] = None,
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Hybrid search: vector + text + reranking + diversification.

        This is the main search method that combines all strategies.

        Args:
            query_text: Query text
            query_vector: Query embedding
            limit: Max results
            score_threshold: Min score

        Returns:
            List of relevant, diverse, reranked documents
        """
        limit = limit or settings.top_k_results
        initial_limit = max(limit * 3, 20)

        # 1. Retrieve from both vector and text indexes
        vector_results = self.qdrant.vector_search(
            query_vector=query_vector,
            limit=initial_limit,
        )

        text_results = self.qdrant.text_search(
            query_text=query_text,
            limit=initial_limit,
        )

        if not vector_results and not text_results:
            logger.warning("No results from vector or text search")
            return []

        # 2. Combine results with hybrid scoring
        combined = self.search.combine_results(
            query_text=query_text,
            vector_results=vector_results,
            text_results=text_results,
            score_threshold=score_threshold,
        )

        logger.debug(
            f"Hybrid search combined to {len(combined)} documents "
            f"(before diversification/reranking)"
        )

        # 3. Apply MMR diversification
        diversified = apply_mmr_diversification(
            documents=combined,
            lambda_param=0.7,
            max_results=initial_limit,
        )

        # 4. Apply reranking if enabled
        if self.enable_reranking and len(diversified) > 1:
            reranked = self.reranker.rerank(
                query=query_text,
                documents=diversified[:initial_limit],
            )
            logger.debug("Reranking applied with CrossEncoder")
        else:
            reranked = diversified

        # 5. Apply anchor gating (filter by key terms)
        filtered = self.search.apply_anchor_gating(
            query_text=query_text,
            documents=reranked,
        )

        # 6. Apply final score threshold
        final_min = score_threshold if score_threshold is not None else 0.0
        final_results = [d for d in filtered if d.get("score", 0.0) >= final_min]

        # 7. Deduplicate by (title, category)
        seen_keys = set()
        deduped: List[Dict[str, Any]] = []

        for doc in final_results:
            title_norm = (doc.get("title") or "").strip().lower()
            category_norm = (doc.get("category") or "").strip().lower()
            key = (title_norm, category_norm)

            if title_norm and key in seen_keys:
                continue

            if title_norm:
                seen_keys.add(key)

            deduped.append(doc)

        final = deduped[:limit]

        logger.info(
            f"Hybrid search complete: {len(final)} final results "
            f"(from {len(combined)} initial)"
        )

        return final

    def get_collection_info(self) -> Dict[str, Any]:
        """Get collection statistics."""
        return self.qdrant.get_collection_info()

    def record_usage(self, doc_ids: List[str]) -> None:
        """Record document usage."""
        self.qdrant.increment_usage(doc_ids)

    def apply_feedback(self, doc_ids: List[str], helpful: bool) -> None:
        """Apply user feedback to documents."""
        self.qdrant.record_feedback(doc_ids, helpful)


# Singleton removed - use dependency injection via get_vector_store() in api/deps.py
# For backward compatibility during migration
_global_instance = None


def get_vector_store_instance() -> VectorStoreService:
    global _global_instance
    if _global_instance is None:
        _global_instance = VectorStoreService()
    return _global_instance
