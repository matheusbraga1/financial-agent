from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, Distance, VectorParams, TextIndexParams, TokenizerType, Filter, FieldCondition, MatchText
from typing import List, Dict, Any, Optional
import logging
import uuid

from app.core.config import get_settings
from app.models.document import DocumentCreate

logger = logging.getLogger(__name__)
settings = get_settings()

class VectorStoreService:
    def __init__(self):
        logger.info(f"Conectando ao Qdrant em {settings.qdrant_host}:{settings.qdrant_port}")
        try:
            self.client = QdrantClient(
                host=settings.qdrant_host,
                port=settings.qdrant_port,
                timeout=10
            )
            self.collection_name = settings.qdrant_collection
            self._ensure_collection()
            logger.info("✓ Qdrant conectado com sucesso")

            self._cross_encoder = None
            self._reranking_enabled = getattr(settings, 'enable_reranking', True)

        except Exception as e:
            logger.error(f"✗ Falha ao conectar no Qdrant: {e}")
            raise ConnectionError(f"Não foi possível conectar ao Qdrant: {e}")

    def _get_cross_encoder(self):
        """Lazy loading do CrossEncoder."""
        if self._cross_encoder is None and self._reranking_enabled:
            try:
                from sentence_transformers import CrossEncoder
                logger.info("Carregando CrossEncoder para reranking...")
                self._cross_encoder = CrossEncoder('cross-encoder/ms-marco-MiniLM-L-6-v2')
                logger.info("✓ CrossEncoder carregado com sucesso")
            except Exception as e:
                logger.warning(f"Falha ao carregar CrossEncoder: {e}. Reranking desabilitado.")
                self._reranking_enabled = False
        return self._cross_encoder

    def _ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        exists = any(col.name == self.collection_name for col in collections)

        if not exists:
            logger.info(f"Criando collection: {self.collection_name}")
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(
                    size=settings.embedding_dimension,
                    distance=Distance.COSINE
                )
            )

            self.client.create_payload_index(
                collection_name=self.collection_name,
                field_name="search_text",
                field_schema=TextIndexParams(
                    type="text",
                    tokenizer=TokenizerType.WORD,
                    min_token_len=2,
                    max_token_len=20,
                    lowercase=True
                )
            )

            logger.info("Collection criada com sucesso")
        else:
            logger.info(f"Collection '{self.collection_name}' já existe")

    def add_document(
            self,
            document: DocumentCreate,
            vector: List[float],
            document_id: Optional[str] = None
    ) -> str:
        doc_id = document_id or str(uuid.uuid4())

        search_text = f"{document.title} {document.title} {document.title} {document.content}"

        point = PointStruct(
            id=doc_id,
            vector=vector,
            payload={
                "title": document.title,
                "category": document.category,
                "content": document.content,
                "search_text": search_text,
                "metadata": document.metadata or {}
            }
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

        logger.info(f"Documento '{document.title}' adicionado com ID: {doc_id}")
        return doc_id

    def search_similar(
            self,
            query_vector: List[float],
            limit: int = None,
            score_threshold: float = None
    ) -> List[Dict[str, Any]]:
        limit = limit or settings.top_k_results
        score_threshold = score_threshold or settings.min_similarity_score

        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit,
            score_threshold=score_threshold
        )

        documents = []
        for result in results:
            documents.append({
                "id": result.id,
                "score": result.score,
                "title": result.payload.get("title"),
                "category": result.payload.get("category"),
                "content": result.payload.get("content"),
                "metadata": result.payload.get("metadata", {})
            })

        logger.debug(f"Encontrados {len(documents)} documentos similares")
        return documents

    def search_hybrid(
            self,
            query_text: str,
            query_vector: List[float],
            limit: int = None,
            score_threshold: float = None
    ) -> List[Dict[str, Any]]:
        """
        Busca híbrida: combina busca vetorial + BM25 textual + boost de título.

        Args:
            query_text: Texto da pergunta (para BM25)
            query_vector: Vetor da pergunta (para busca semântica)
            limit: Número de resultados
            score_threshold: Score mínimo

        Returns:
            List[Dict]: Documentos encontrados (rerankeados)
        """
        limit = limit or settings.top_k_results

        initial_limit = max(limit * 3, 20)

        vector_results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=initial_limit,
            with_payload=True
        )

        text_results = self.client.scroll(
            collection_name=self.collection_name,
            scroll_filter=Filter(
                must=[
                    FieldCondition(
                        key="search_text",
                        match=MatchText(text=query_text)
                    )
                ]
            ),
            limit=initial_limit,
            with_payload=True,
            with_vectors=False
        )[0]

        import unicodedata
        import re
        def normalize_text(text):
            if not text:
                return ""
            nfd = unicodedata.normalize('NFD', text)
            text_without_accents = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
            return text_without_accents.lower().strip()

        query_normalized = normalize_text(query_text)
        query_words = set(re.findall(r'\w+', query_normalized))

        combined_scores = {}

        for result in vector_results:
            doc_id = result.id
            combined_scores[doc_id] = {
                "vector_score": result.score,
                "text_score": 0,
                "title_boost": 0,
                "payload": result.payload
            }

        for point in text_results:
            doc_id = point.id
            if doc_id in combined_scores:
                combined_scores[doc_id]["text_score"] = 0.6
            else:
                combined_scores[doc_id] = {
                    "vector_score": 0,
                    "text_score": 0.6,
                    "title_boost": 0,
                    "payload": point.payload
                }

        for doc_id, scores in combined_scores.items():
            title = scores["payload"].get("title", "")
            title_normalized = normalize_text(title)
            title_words = set(re.findall(r'\w+', title_normalized))

            if query_words and title_words:
                overlap = query_words.intersection(title_words)
                overlap_ratio = len(overlap) / len(query_words)

                if overlap_ratio > 0:
                    scores["title_boost"] = overlap_ratio * 0.8
                    logger.debug(f"Título '{title}' tem {overlap_ratio:.1%} overlap → boost={scores['title_boost']:.2f}")

        final_results = []
        for doc_id, scores in combined_scores.items():
            final_score = (
                (scores["vector_score"] * 0.40) +
                (scores["text_score"] * 0.30) +
                (scores["title_boost"] * 0.30)
            )

            final_score = max(0.0, min(1.0, final_score))

            if score_threshold is None or final_score >= score_threshold:
                final_results.append({
                    "id": doc_id,
                    "score": final_score,
                    "title": scores["payload"].get("title"),
                    "category": scores["payload"].get("category"),
                    "content": scores["payload"].get("content"),
                    "metadata": scores["payload"].get("metadata", {})
                })

        final_results.sort(key=lambda x: x["score"], reverse=True)

        logger.debug(f"Busca híbrida: {len(final_results)} documentos antes do reranking")

        if self._reranking_enabled and len(final_results) > 1:
            final_results = self._rerank_results(query_text, final_results[:initial_limit])
            logger.debug(f"Reranking aplicado com CrossEncoder")

        return final_results[:limit]

    def _rerank_results(self, query: str, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Reranqueia documentos usando CrossEncoder para maior precisão.

        Args:
            query: Query do usuário
            documents: Lista de documentos recuperados

        Returns:
            Lista de documentos reranqueados
        """
        cross_encoder = self._get_cross_encoder()
        if cross_encoder is None:
            return documents

        pairs = []
        for doc in documents:
            content_preview = doc["content"][:500] if doc["content"] else ""
            text = f"{doc['title']}. {content_preview}"
            pairs.append([query, text])

        try:
            rerank_scores = cross_encoder.predict(pairs)

            import numpy as np
            normalized_rerank_scores = 1 / (1 + np.exp(-np.array(rerank_scores)))

            logger.debug(f"Scores originais do CrossEncoder: min={rerank_scores.min():.2f}, max={rerank_scores.max():.2f}")
            logger.debug(f"Scores normalizados: min={normalized_rerank_scores.min():.2f}, max={normalized_rerank_scores.max():.2f}")

            for doc, score in zip(documents, normalized_rerank_scores):
                original_score = doc["score"]
                doc["score"] = (original_score * 0.3) + (float(score) * 0.7)

                doc["score"] = max(0.0, min(1.0, doc["score"]))

            documents.sort(key=lambda x: x["score"], reverse=True)

            logger.debug(f"Reranking concluído - scores atualizados e normalizados")
        except Exception as e:
            logger.warning(f"Erro ao aplicar reranking: {e}")

        return documents

    def get_collection_info(self) -> Dict[str, Any]:
        """Retorna informações sobre a collection."""
        info = self.client.get_collection(self.collection_name)
        return {
            "name": self.collection_name,
            "vectors_count": info.points_count,
            "vector_size": info.config.params.vectors.size
        }

vector_store_service = VectorStoreService()