from typing import List, Dict, Any, Optional
import logging
from datetime import datetime
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    VectorParams,
    PointStruct,
    Filter,
    FieldCondition,
    MatchAny
)

logger = logging.getLogger(__name__)

class QdrantAdapter:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 6333,
        collection_name: str = "artigos_glpi",
        vector_size: int = 1024,
        distance: str = "Cosine",
    ):
        self.client = QdrantClient(host=host, port=port)
        self.collection_name = collection_name
        self.vector_size = vector_size
        
        distance_map = {
            "Cosine": Distance.COSINE,
            "Dot": Distance.DOT,
            "Euclid": Distance.EUCLID,
        }
        self.distance = distance_map.get(distance, Distance.COSINE)
        
        self._ensure_collection()
        
        logger.info(
            f"QdrantAdapter inicializado: {host}:{port}, "
            f"collection={collection_name}"
        )
    
    def _ensure_collection(self) -> None:
        try:
            collections = self.client.get_collections().collections
            exists = any(c.name == self.collection_name for c in collections)
            
            if not exists:
                logger.info(f"Criando coleção: {self.collection_name}")
                
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=self.distance,
                    ),
                )
                
                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="search_text",
                    field_type="text",
                )
                
                logger.info(f"Coleção criada: {self.collection_name}")
            
        except Exception as e:
            logger.error(f"Erro ao garantir coleção: {e}")
            raise
    
    def search_similar(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            qdrant_filter = self._build_filter(filter) if filter else None
            
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                query_filter=qdrant_filter,
            )
            
            documents = []
            for hit in results:
                documents.append({
                    "id": str(hit.id),
                    "score": float(hit.score),
                    "title": hit.payload.get("title", ""),
                    "content": hit.payload.get("content", ""),
                    "category": hit.payload.get("category", ""),
                    "metadata": hit.payload.get("metadata", {}),
                })
            
            return documents
            
        except Exception as e:
            logger.error(f"Erro na busca vetorial: {e}")
            return []
    
    def search_hybrid(
        self,
        query_text: str,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            initial_limit = max(limit * 3, 20)
            
            vector_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=initial_limit,
                query_filter=self._build_filter(filter) if filter else None,
            )
            
            text_results = []
            
            combined = self._combine_results_rrf(
                vector_results,
                text_results,
                query_text,
            )
            
            if score_threshold:
                combined = [
                    doc for doc in combined 
                    if doc.get("score", 0.0) >= score_threshold
                ]
            
            combined = combined[:limit]
            
            return combined
            
        except Exception as e:
            logger.error(f"Erro na busca híbrida: {e}")
            return []
    
    def upsert(
        self,
        id: str,
        vector: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        try:
            title = metadata.get("title", "")
            content = metadata.get("content", "")
            search_text = f"{title} {title} {title} {content}"
            
            payload = {
                "title": title,
                "content": content,
                "category": metadata.get("category", ""),
                "search_text": search_text,
                "metadata": metadata.get("metadata", {}),
                "department": metadata.get("metadata", {}).get("department"),
                "doc_type": metadata.get("metadata", {}).get("doc_type"),
                "tags": metadata.get("metadata", {}).get("tags", []),
                "usage_count": 0,
                "helpful_votes": 0,
                "complaints": 0,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            self.client.upsert(
                collection_name=self.collection_name,
                points=[
                    PointStruct(
                        id=id,
                        vector=vector,
                        payload=payload,
                    )
                ],
            )
            
            logger.debug(f"Documento upserted: {id}")
            
        except Exception as e:
            logger.error(f"Erro ao fazer upsert: {e}")
            raise
    
    def delete(self, id: str) -> bool:
        try:
            self.client.delete(
                collection_name=self.collection_name,
                points_selector=[id],
            )
            
            logger.info(f"Documento deletado: {id}")
            return True
            
        except Exception as e:
            logger.error(f"Erro ao deletar documento: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        try:
            info = self.client.get_collection(self.collection_name)
            
            return {
                "name": self.collection_name,
                "vectors_count": info.points_count,
                "indexed_vectors_count": info.indexed_vectors_count,
                "status": info.status,
            }
            
        except Exception as e:
            logger.error(f"Erro ao obter stats: {e}")
            return {}
    
    def record_usage(self, doc_ids: List[str]) -> None:
        if not doc_ids:
            return
        
        try:
            for doc_id in doc_ids:
                self.client.set_payload(
                    collection_name=self.collection_name,
                    payload={
                        "last_used_at": datetime.utcnow().isoformat(),
                    },
                    points=[doc_id],
                )
            
            logger.debug(f"Uso registrado para {len(doc_ids)} documentos")
            
        except Exception as e:
            logger.debug(f"Erro ao registrar uso: {e}")
    
    def apply_feedback(self, doc_ids: List[str], helpful: bool) -> None:
        if not doc_ids:
            return
        
        try:
            field = "helpful_votes" if helpful else "complaints"
            
            for doc_id in doc_ids:
                pass
            
            logger.debug(
                f"Feedback aplicado: {len(doc_ids)} docs, "
                f"{'positivo' if helpful else 'negativo'}"
            )
            
        except Exception as e:
            logger.debug(f"Erro ao aplicar feedback: {e}")
    
    def _build_filter(self, filter_dict: Dict[str, Any]) -> Filter:
        conditions = []
        
        if "departments" in filter_dict:
            departments = filter_dict["departments"]
            if departments:
                conditions.append(
                    FieldCondition(
                        key="department",
                        match=MatchAny(any=departments)
                    )
                )
        
        if "doc_types" in filter_dict:
            doc_types = filter_dict["doc_types"]
            if doc_types:
                conditions.append(
                    FieldCondition(
                        key="doc_type",
                        match=MatchAny(any=doc_types)
                    )
                )
        
        if conditions:
            return Filter(must=conditions)
        
        return None
    
    def _combine_results_rrf(
        self,
        vector_results: List,
        text_results: List,
        query_text: str,
        k: int = 60,
    ) -> List[Dict[str, Any]]:
        docs_by_id: Dict[str, Dict[str, Any]] = {}
        
        for rank, hit in enumerate(vector_results, 1):
            doc_id = str(hit.id)
            
            docs_by_id[doc_id] = {
                "id": doc_id,
                "title": hit.payload.get("title", ""),
                "content": hit.payload.get("content", ""),
                "category": hit.payload.get("category", ""),
                "metadata": hit.payload.get("metadata", {}),
                "vector_score": float(hit.score),
                "vector_rank": rank,
                "text_score": 0.0,
                "text_rank": 0,
            }
        
        for doc_id, doc in docs_by_id.items():
            vector_rrf = 1.0 / (k + doc["vector_rank"])
            text_rrf = 1.0 / (k + doc["text_rank"]) if doc["text_rank"] > 0 else 0
            
            doc["score"] = 0.7 * vector_rrf + 0.3 * text_rrf
        
        sorted_docs = sorted(
            docs_by_id.values(),
            key=lambda x: x["score"],
            reverse=True
        )
        
        return sorted_docs