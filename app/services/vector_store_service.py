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
        except Exception as e:
            logger.error(f"✗ Falha ao conectar no Qdrant: {e}")
            raise ConnectionError(f"Não foi possível conectar ao Qdrant: {e}")

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
                "search_text": search_text,  # NOVO: Campo indexado
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
        Busca híbrida: combina busca vetorial + BM25 textual.

        Args:
            query_text: Texto da pergunta (para BM25)
            query_vector: Vetor da pergunta (para busca semântica)
            limit: Número de resultados
            score_threshold: Score mínimo

        Returns:
            List[Dict]: Documentos encontrados (rerankeados)
        """
        limit = limit or settings.top_k_results

        # Busca vetorial (semântica)
        vector_results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_vector,
            limit=limit * 2,  # Buscar mais para depois reranking
            with_payload=True
        )

        # Busca textual (BM25) - palavras-chave exatas
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
            limit=limit * 2,
            with_payload=True,
            with_vectors=False
        )[0]

        # Combinar e reranking
        combined_scores = {}

        # Pontos da busca vetorial
        for result in vector_results:
            doc_id = result.id
            combined_scores[doc_id] = {
                "vector_score": result.score,
                "text_score": 0,
                "payload": result.payload
            }

        # Adicionar pontos da busca textual
        for point in text_results:
            doc_id = point.id
            if doc_id in combined_scores:
                combined_scores[doc_id]["text_score"] = 0.3  # Boost fixo se encontrou
            else:
                combined_scores[doc_id] = {
                    "vector_score": 0,
                    "text_score": 0.3,
                    "payload": point.payload
                }

        # Score final: 70% vetorial + 30% textual
        final_results = []
        for doc_id, scores in combined_scores.items():
            final_score = (scores["vector_score"] * 0.7) + (scores["text_score"] * 0.3)

            if score_threshold is None or final_score >= score_threshold:
                final_results.append({
                    "id": doc_id,
                    "score": final_score,
                    "title": scores["payload"].get("title"),
                    "category": scores["payload"].get("category"),
                    "content": scores["payload"].get("content"),
                    "metadata": scores["payload"].get("metadata", {})
                })

        # Ordenar por score final
        final_results.sort(key=lambda x: x["score"], reverse=True)

        return final_results[:limit]

    def get_collection_info(self) -> Dict[str, Any]:
        """Retorna informações sobre a collection."""
        info = self.client.get_collection(self.collection_name)
        return {
            "name": self.collection_name,
            "vectors_count": info.points_count,
            "vector_size": info.config.params.vectors.size
        }

vector_store_service = VectorStoreService()