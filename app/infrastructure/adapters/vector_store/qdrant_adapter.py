import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from qdrant_client import QdrantClient
from qdrant_client.models import (
    PointStruct,
    Distance,
    VectorParams,
    TextIndexParams,
    TokenizerType,
    Filter,
    FieldCondition,
    MatchText,
)

from app.infrastructure.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class QdrantAdapter:
    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        collection_name: Optional[str] = None,
        vector_size: Optional[int] = None,
    ):
        self.host = host or settings.qdrant_host
        self.port = port or settings.qdrant_port
        self.collection_name = collection_name or settings.qdrant_collection
        self.vector_size = vector_size or settings.embedding_dimension

        logger.info(f"Initializing Qdrant client: {self.host}:{self.port}")

        self.client = QdrantClient(
            host=self.host,
            port=self.port,
            timeout=10,
        )

        logger.info(f"Qdrant adapter initialized for collection '{self.collection_name}'")

    def ensure_collection(self) -> None:
        try:
            collections = self.client.get_collections().collections
            exists = any(col.name == self.collection_name for col in collections)

            if not exists:
                logger.info(f"Creating collection: {self.collection_name}")

                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.vector_size,
                        distance=Distance.COSINE
                    ),
                )

                self.client.create_payload_index(
                    collection_name=self.collection_name,
                    field_name="search_text",
                    field_schema=TextIndexParams(
                        type="text",
                        tokenizer=TokenizerType.WORD,
                        min_token_len=2,
                        max_token_len=20,
                        lowercase=True,
                    ),
                )

                logger.info("Collection created successfully")
            else:
                logger.debug(f"Collection '{self.collection_name}' already exists")

        except Exception as e:
            logger.warning(f"Qdrant unavailable when ensuring collection: {e}")
            raise

    def upsert_point(
        self,
        point_id: str,
        vector: List[float],
        payload: Dict[str, Any],
    ) -> None:
        point = PointStruct(
            id=point_id,
            vector=vector,
            payload=payload,
        )

        self.client.upsert(
            collection_name=self.collection_name,
            points=[point]
        )

        logger.debug(f"Point upserted: {point_id}")

    def upsert_points(self, points: List[PointStruct]) -> None:
        if not points:
            return

        self.client.upsert(
            collection_name=self.collection_name,
            points=points
        )

        logger.debug(f"Batch upserted {len(points)} points")

    def vector_search(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
    ) -> List[Any]:
        try:
            self.ensure_collection()

            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
                with_payload=True,
            )

            logger.debug(f"Vector search returned {len(results)} results")
            return results

        except Exception as e:
            logger.warning(f"Vector search failed (Qdrant offline?): {e}")
            return []

    def text_search(
        self,
        query_text: str,
        limit: int = 10,
    ) -> List[Any]:
        try:
            self.ensure_collection()

            results, _next_offset = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[
                        FieldCondition(
                            key="search_text",
                            match=MatchText(text=query_text)
                        )
                    ]
                ),
                limit=limit,
                with_payload=True,
                with_vectors=False,
            )

            logger.debug(f"Text search returned {len(results)} results")
            return results

        except Exception as e:
            logger.warning(f"Text search failed (Qdrant offline?): {e}")
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
            self.ensure_collection()

            vector_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit * 2,
                score_threshold=score_threshold if score_threshold else 0.0,
                with_payload=True,
            )

            documents = []
            for result in vector_results:
                payload = result.payload or {}

                doc = {
                    "id": str(result.id),
                    "score": float(result.score),
                    "title": payload.get("title", ""),
                    "content": payload.get("content", ""),
                    "doc_type": payload.get("doc_type", ""),
                    "department": payload.get("department", ""),
                    "tags": payload.get("tags", []),
                    "created_at": payload.get("created_at", ""),
                    "updated_at": payload.get("updated_at", ""),
                    "usage_count": payload.get("usage_count", 0),
                    "helpful_votes": payload.get("helpful_votes", 0),
                }

                documents.append(doc)

            logger.debug(f"Hybrid search returned {len(documents)} results")
            return documents[:limit]

        except Exception as e:
            logger.warning(f"Hybrid search failed (Qdrant offline?): {e}")
            return []

    def retrieve_points(
        self,
        ids: List[str],
        with_payload: bool = True,
        with_vectors: bool = False,
    ) -> List[Any]:
        if not ids:
            return []

        try:
            points = self.client.retrieve(
                collection_name=self.collection_name,
                ids=ids,
                with_payload=with_payload,
                with_vectors=with_vectors,
            )
            return points

        except Exception as e:
            logger.debug(f"Failed to retrieve points: {e}")
            return []

    def update_payload(
        self,
        point_ids: List[str],
        payload: Dict[str, Any],
    ) -> None:
        if not point_ids or not payload:
            return

        try:
            self.client.set_payload(
                collection_name=self.collection_name,
                payload=payload,
                points=point_ids,
            )
            logger.debug(f"Updated payload for {len(point_ids)} points")

        except Exception as e:
            logger.debug(f"Failed to update payload: {e}")

    def increment_usage(self, point_ids: List[str]) -> None:
        if not point_ids:
            return

        unique_ids = list(dict.fromkeys(str(pid) for pid in point_ids if pid))
        if not unique_ids:
            return

        timestamp = datetime.utcnow().isoformat()

        try:
            for i in range(0, len(unique_ids), 64):
                batch = unique_ids[i:i+64]

                points = self.retrieve_points(batch, with_payload=True, with_vectors=False)

                for point in points:
                    current_usage = int((point.payload or {}).get("usage_count", 0) or 0)
                    new_usage = current_usage + 1

                    self.update_payload(
                        point_ids=[point.id],
                        payload={
                            "usage_count": new_usage,
                            "last_used_at": timestamp,
                        }
                    )

            logger.debug(f"Incremented usage for {len(unique_ids)} documents")

        except Exception as e:
            logger.debug(f"Failed to increment usage: {e}")

    def record_feedback(
        self,
        point_ids: List[str],
        helpful: bool,
    ) -> None:
        if not point_ids:
            return

        unique_ids = list(dict.fromkeys(str(pid) for pid in point_ids if pid))
        if not unique_ids:
            return

        field = "helpful_votes" if helpful else "complaints"

        try:
            for i in range(0, len(unique_ids), 64):
                batch = unique_ids[i:i+64]

                points = self.retrieve_points(batch, with_payload=True, with_vectors=False)

                for point in points:
                    current_value = int((point.payload or {}).get(field, 0) or 0)
                    new_value = current_value + 1

                    self.update_payload(
                        point_ids=[point.id],
                        payload={field: new_value}
                    )

            logger.debug(f"Recorded feedback for {len(unique_ids)} documents")

        except Exception as e:
            logger.debug(f"Failed to record feedback: {e}")

    def get_collection_info(self) -> Dict[str, Any]:
        name = self.collection_name
        vectors_count = None
        vector_size = None
        exists = None

        try:
            cnt = self.client.count(collection_name=name, exact=True)
            vectors_count = getattr(cnt, "count", None)
        except Exception:
            pass

        try:
            info = self.client.get_collection(name)
            cfg = getattr(info, "config", None)

            if isinstance(cfg, dict):
                params = cfg.get("params", {})
                vectors = params.get("vectors", {})
                vector_size = vectors.get("size")
            else:
                params = getattr(cfg, "params", None)
                vectors = getattr(params, "vectors", None)
                vector_size = getattr(vectors, "size", None) if vectors else None

        except Exception:
            pass

        try:
            colls = self.client.get_collections()
            exists = any(c.name == name for c in getattr(colls, "collections", []))
        except Exception:
            pass

        return {
            "name": name,
            "vectors_count": vectors_count,
            "vector_size": vector_size,
            "exists": exists,
        }

    def get_stats(self) -> Dict[str, Any]:
        info = self.get_collection_info()
        vectors_count = info.get("vectors_count", 0) or 0

        return {
            "name": info.get("name"),
            "vectors_count": vectors_count,
            "indexed_vectors_count": vectors_count,
            "status": "ok" if info.get("exists") else "not_found",
        }
