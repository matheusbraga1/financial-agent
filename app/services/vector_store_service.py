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
from typing import List, Dict, Any, Optional
from datetime import datetime
import logging
import uuid

from app.core.config import get_settings
from app.models.document import DocumentCreate


logger = logging.getLogger(__name__)
settings = get_settings()


class VectorStoreService:
    def __init__(self):
        logger.info(f"Preparando cliente Qdrant em {settings.qdrant_host}:{settings.qdrant_port}")
        # Observação: não chamamos o servidor aqui para não derrubar o startup da API
        # quando o Qdrant estiver offline. O readiness irá refletir o estado real.
        self.client = QdrantClient(
            host=settings.qdrant_host,
            port=settings.qdrant_port,
            timeout=10,
        )
        self.collection_name = settings.qdrant_collection
        self._cross_encoder = None
        self._reranking_enabled = getattr(settings, "enable_reranking", True)

    def _feedback_boost(self, payload: Optional[Dict[str, Any]]) -> float:
        if not payload:
            return 0.0
        helpful = float(payload.get("helpful_votes", 0) or 0)
        complaints = float(payload.get("complaints", 0) or 0)
        usage = float(payload.get("usage_count", 0) or 0)
        if helpful == 0 and complaints == 0 and usage == 0:
            return 0.0
        feedback_component = (helpful - complaints) / max(5.0, helpful + complaints + 1.0)
        popularity_component = min(0.1, usage / 500.0)
        boost = feedback_component + popularity_component
        return max(-0.2, min(0.2, boost))

    def _get_cross_encoder(self):
        """Lazy loading do CrossEncoder."""
        if self._cross_encoder is None and self._reranking_enabled:
            try:
                from sentence_transformers import CrossEncoder

                logger.info("Carregando CrossEncoder para reranking...")
                self._cross_encoder = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
                logger.info("CrossEncoder carregado com sucesso")
            except Exception as e:
                logger.warning(f"Falha ao carregar CrossEncoder: {e}. Reranking desabilitado.")
                self._reranking_enabled = False
        return self._cross_encoder

    def _ensure_collection(self) -> None:
        try:
            collections = self.client.get_collections().collections
            exists = any(col.name == self.collection_name for col in collections)

            if not exists:
                logger.info(f"Criando collection: {self.collection_name}")
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=settings.embedding_dimension, distance=Distance.COSINE
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

                logger.info("Collection criada com sucesso")
            else:
                logger.info(f"Collection '{self.collection_name}' já existe")
        except Exception as e:
            # Evita derrubar a API quando o Qdrant estiver offline. Chamadas de busca tratarão isso.
            logger.warning(f"Qdrant indisponível ao garantir collection: {e}")
            raise

    def add_document(
        self,
        document: DocumentCreate,
        vector: List[float],
        document_id: Optional[str] = None,
    ) -> str:
        doc_id = document_id or str(uuid.uuid4())

        metadata = document.metadata or {}
        # Cria um campo de texto para busca lexical
        search_text = f"{document.title} {document.title} {document.title} {document.content}"
        departments = metadata.get("departments") or (
            [metadata.get("department")] if metadata.get("department") else []
        )

        point = PointStruct(
            id=doc_id,
            vector=vector,
            payload={
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
                "helpful_votes": int(metadata.get("helpful_votes", 0) or 0),
                "complaints": int(metadata.get("complaints", 0) or 0),
                "usage_count": int(metadata.get("usage_count", 0) or 0),
                "last_used_at": metadata.get("last_used_at"),
            },
        )

        self.client.upsert(collection_name=self.collection_name, points=[point])

        logger.info(f"Documento '{document.title}' adicionado com ID: {doc_id}")
        return doc_id

    def search_similar(
        self,
        query_vector: List[float],
        limit: int | None = None,
        score_threshold: float | None = None,
    ) -> List[Dict[str, Any]]:
        limit = limit or settings.top_k_results
        score_threshold = score_threshold or settings.min_similarity_score

        try:
            # Garante collection sob demanda
            self._ensure_collection()
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=limit,
                score_threshold=score_threshold,
            )
        except Exception as e:
            logger.warning(f"Busca similar falhou (Qdrant offline?): {e}")
            return []

        documents = []
        for result in results:
            documents.append(
                {
                    "id": result.id,
                    "score": result.score,
                    "title": result.payload.get("title"),
                    "category": result.payload.get("category"),
                    "content": result.payload.get("content"),
                    "metadata": result.payload.get("metadata", {}),
                }
            )

        logger.debug(f"Encontrados {len(documents)} documentos similares")
        return documents

    def search_hybrid(
        self,
        query_text: str,
        query_vector: List[float],
        limit: int | None = None,
        score_threshold: float | None = None,
    ) -> List[Dict[str, Any]]:
        """
        Busca híbrida: combina busca vetorial + BM25 textual + boost de título.

        Args:
            query_text: Texto da pergunta (para BM25)
            query_vector: Vetor da pergunta (para busca semântica)
            limit: Número de resultados
            score_threshold: Score mínimo

        Returns:
            List[Dict]: Documentos encontrados (reranqueados)
        """
        limit = limit or settings.top_k_results
        initial_limit = max(limit * 3, 20)

        try:
            self._ensure_collection()
            vector_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                limit=initial_limit,
                with_payload=True,
            )

            text_results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=Filter(
                    must=[FieldCondition(key="search_text", match=MatchText(text=query_text))]
                ),
                limit=initial_limit,
                with_payload=True,
                with_vectors=False,
            )[0]
        except Exception as e:
            logger.warning(f"Busca híbrida falhou (Qdrant offline?): {e}")
            return []

        import unicodedata
        import re

        def normalize_text(text: str) -> str:
            if not text:
                return ""
            nfd = unicodedata.normalize("NFD", text)
            text_without_accents = "".join(
                char for char in nfd if unicodedata.category(char) != "Mn"
            )
            return text_without_accents.lower().strip()

        query_normalized = normalize_text(query_text)
        query_words = set(re.findall(r"\w+", query_normalized))
        # Conteúdo da query sem stopwords comuns, para sobreposições mais informativas
        # em texto e títulos
        stopwords_q = {
            "a",
            "o",
            "as",
            "os",
            "um",
            "uma",
            "uns",
            "umas",
            "de",
            "do",
            "da",
            "dos",
            "das",
            "e",
            "em",
            "no",
            "na",
            "nos",
            "nas",
            "para",
            "por",
            "com",
            "sem",
            "ao",
            "aos",
            "que",
            "como",
            "ser",
            "estar",
            "ter",
            "fazer",
            "nao",
            "duvida",
            "duvidas",
            "pergunta",
            "perguntas",
        }
        query_content_words = {w for w in query_words if w not in stopwords_q}
        q_has_vpn = "vpn" in query_words

        combined_scores: Dict[str, Dict[str, Any]] = {}

        for result in vector_results:
            doc_id = result.id
            combined_scores[doc_id] = {
                "vector_score": result.score,
                "text_score": 0.0,
                "title_boost": 0.0,
                "payload": result.payload,
            }

        for point in text_results:
            doc_id = point.id
            payload = point.payload
            text_for_overlap = payload.get("search_text") or (
                (payload.get("title") or "") + " " + (payload.get("content") or "")
            )
            text_norm = normalize_text(text_for_overlap)
            text_words = set(re.findall(r"\w+", text_norm))
            # Sobreposição usa apenas termos de conteúdo da query
            overlap_base = query_content_words if query_content_words else query_words
            overlap_ratio = (
                len(overlap_base.intersection(text_words)) / len(overlap_base)
                if overlap_base
                else 0.0
            )
            heuristic_text_score = max(0.0, min(1.0, 0.2 + 0.8 * overlap_ratio))
            # Penaliza textos que não contêm termos fortes quando a query tem 'vpn'
            if q_has_vpn and not ({"vpn", "virtual", "remoto", "forticlient", "anyconnect"} & text_words):
                heuristic_text_score *= 0.5

            if doc_id in combined_scores:
                combined_scores[doc_id]["text_score"] = heuristic_text_score
            else:
                combined_scores[doc_id] = {
                    "vector_score": 0.0,
                    "text_score": heuristic_text_score,
                    "title_boost": 0.0,
                    "payload": payload,
                }

        for doc_id, scores in combined_scores.items():
            title = scores["payload"].get("title", "")
            title_normalized = normalize_text(title)
            title_words = set(re.findall(r"\w+", title_normalized))
            overlap_base = query_content_words if query_content_words else query_words
            if overlap_base and title_words:
                overlap = overlap_base.intersection(title_words)
                overlap_ratio = len(overlap) / len(overlap_base)
                if overlap_ratio > 0:
                    scores["title_boost"] = overlap_ratio * 0.8
                    logger.debug(
                        f"Título '{title}' tem {overlap_ratio:.1%} de overlap -> boost={scores['title_boost']:.2f}"
                    )

        # Boost genérico por categoria: baseado em sobreposição léxica entre palavras da query e a categoria
        stopwords = {
            "e",
            "de",
            "do",
            "da",
            "das",
            "dos",
            "para",
            "em",
            "no",
            "na",
            "nas",
            "nos",
            "por",
            "um",
            "uma",
            "o",
            "a",
            "os",
            "as",
            "internas",
            "internos",
            "geral",
        }
        for doc_id, scores in combined_scores.items():
            category = scores["payload"].get("category", "") or ""
            category_norm = normalize_text(category)
            cat_tokens = set(re.findall(r"\w+", category_norm)) - stopwords
            if not cat_tokens:
                scores["category_boost"] = 0.0
                continue
            overlap = (
                query_content_words.intersection(cat_tokens)
                if query_content_words
                else query_words.intersection(cat_tokens)
            )
            overlap_ratio = len(overlap) / max(1, len(cat_tokens))
            # Limitamos o boost para evitar dominar o score final
            scores["category_boost"] = max(0.0, min(1.0, overlap_ratio))

        final_results: List[Dict[str, Any]] = []
        for doc_id, scores in combined_scores.items():
            final_score = (
                (scores["vector_score"] * 0.40)
                + (scores["text_score"] * 0.30)
                + (scores["title_boost"] * 0.30)
                + (scores.get("category_boost", 0.0) * 0.10)
            )
            final_score += self._feedback_boost(scores.get("payload"))
            final_score = max(0.0, min(1.0, final_score))
            if score_threshold is None or final_score >= score_threshold:
                final_results.append(
                    {
                        "id": doc_id,
                        "score": final_score,
                        "title": scores["payload"].get("title"),
                        "category": scores["payload"].get("category"),
                        "content": scores["payload"].get("content"),
                        "metadata": scores["payload"].get("metadata", {}),
                    }
                )

        final_results.sort(key=lambda x: x["score"], reverse=True)

        # Aplicar MMR simples para diversidade antes do reranking
        def jaccard(a: set, b: set) -> float:
            if not a or not b:
                return 0.0
            inter = len(a.intersection(b))
            union = len(a.union(b))
            return inter / union if union else 0.0

        import re as _re

        cand_wordsets: Dict[str, set] = {}
        for doc in final_results:
            text = f"{doc.get('title','')} {doc.get('content','')}"
            norm = normalize_text(text)
            cand_wordsets[doc["id"]] = set(_re.findall(r"\w+", norm))

        mmr_lambda = 0.7
        k = min(initial_limit, len(final_results))
        selected: List[Dict[str, Any]] = []
        remaining = final_results.copy()
        while remaining and len(selected) < k:
            best = None
            best_score = -1e9
            for cand in remaining:
                relevance = cand["score"]
                if not selected:
                    diversity_penalty = 0.0
                else:
                    max_sim = max(
                        jaccard(cand_wordsets[cand["id"]], cand_wordsets[s["id"]])
                        for s in selected
                    )
                    diversity_penalty = max_sim
                mmr_score = mmr_lambda * relevance - (1 - mmr_lambda) * diversity_penalty
                if mmr_score > best_score:
                    best_score = mmr_score
                    best = cand
            selected.append(best)
            remaining.remove(best)

        final_results = selected

        logger.debug(f"Busca híbrida: {len(final_results)} documentos antes do reranking")

        if self._reranking_enabled and len(final_results) > 1:
            final_results = self._rerank_results(query_text, final_results[:initial_limit])
            logger.debug("Reranking aplicado com CrossEncoder")

        # Gating por termos-âncora: prioriza docs com termos relevantes
        try:
            anchor_stop = {
                "rede",
                "conectar",
                "conexao",
                "acessar",
                "acesso",
                "gerenciador",
                "aplicativo",
                "dispositivo",
                "empresa",
                "corporativa",
                "sistema",
                "plataforma",
            }
            anchors = {w for w in query_words if w not in anchor_stop}
            if query_content_words:
                anchors = {w for w in query_content_words if w not in anchor_stop}

            def doc_has_anchor(doc) -> bool:
                text = f"{doc.get('title','')} {doc.get('content','')}"
                norm = normalize_text(text)
                tokens = set(_re.findall(r"\w+", norm))
                return bool(anchors & tokens)

            if anchors:
                any_with_anchor = any(doc_has_anchor(d) for d in final_results)
                if any_with_anchor:
                    filtered = [d for d in final_results if doc_has_anchor(d)]
                    if filtered:
                        logger.debug(
                            f"Anchor gating aplicado - mantidos {len(filtered)}/{len(final_results)}"
                        )
                        final_results = filtered
        except Exception as _e:
            logger.debug(f"Anchor gating falhou: {_e}")

        # Enforce final score threshold after reranking
        final_min = score_threshold if score_threshold is not None else 0.0
        final_results = [d for d in final_results if d.get("score", 0.0) >= final_min]

        # Deduplicate by normalized (title, category)
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

        return deduped[:limit]

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

            logger.debug(
                f"Scores originais do CrossEncoder: min={rerank_scores.min():.2f}, max={rerank_scores.max():.2f}"
            )
            logger.debug(
                f"Scores normalizados: min={normalized_rerank_scores.min():.2f}, max={normalized_rerank_scores.max():.2f}"
            )

            for doc, score in zip(documents, normalized_rerank_scores):
                original_score = doc["score"]
                doc["score"] = (original_score * 0.3) + (float(score) * 0.7)
                doc["score"] = max(0.0, min(1.0, doc["score"]))

            documents.sort(key=lambda x: x["score"], reverse=True)

            logger.debug("Reranking concluído - scores atualizados e normalizados")
        except Exception as e:
            logger.warning(f"Erro ao aplicar reranking: {e}")

        return documents

    def get_collection_info(self) -> Dict[str, Any]:
        """Retorna informações sobre a collection.

        Evita depender do parsing detalhado de config (que pode variar por versão)
        e usa o endpoint de contagem como fonte da verdade para `vectors_count`.
        """
        name = self.collection_name
        vectors_count = None
        vector_size = None
        exists = None

        # 1) Conta pontos de forma estável
        try:
            cnt = self.client.count(collection_name=name, exact=True)
            vectors_count = getattr(cnt, "count", None)
        except Exception:
            pass

        # 2) (Opcional) tenta extrair o tamanho do vetor; silencioso se falhar
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
                vector_size = getattr(vectors, "size", None) if vectors is not None else None
        except Exception:
            pass

        # 3) (Opcional) existência básica
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

    def _chunk_ids(self, ids: List[str], chunk_size: int = 64):
        for idx in range(0, len(ids), chunk_size):
            yield ids[idx : idx + chunk_size]

    def record_usage(self, doc_ids: List[str]) -> None:
        if not doc_ids:
            return
        unique_ids = [str(_id) for _id in dict.fromkeys(doc_ids) if _id]
        if not unique_ids:
            return
        timestamp = datetime.utcnow().isoformat()
        try:
            for batch in self._chunk_ids(unique_ids):
                try:
                    points = self.client.retrieve(
                        collection_name=self.collection_name,
                        ids=batch,
                        with_payload=True,
                        with_vectors=False,
                    )
                except Exception as err:
                    logger.debug(f"Não foi possível recuperar pontos para uso: {err}")
                    continue
                for point in points:
                    usage = int((point.payload or {}).get("usage_count", 0) or 0) + 1
                    self.client.set_payload(
                        collection_name=self.collection_name,
                        payload={"usage_count": usage, "last_used_at": timestamp},
                        points=[point.id],
                    )
        except Exception as err:
            logger.debug(f"Falha ao atualizar uso dos documentos: {err}")

    def apply_feedback(self, doc_ids: List[str], helpful: bool) -> None:
        if not doc_ids:
            return
        unique_ids = [str(_id) for _id in dict.fromkeys(doc_ids) if _id]
        if not unique_ids:
            return
        field = "helpful_votes" if helpful else "complaints"
        try:
            for batch in self._chunk_ids(unique_ids):
                try:
                    points = self.client.retrieve(
                        collection_name=self.collection_name,
                        ids=batch,
                        with_payload=True,
                        with_vectors=False,
                    )
                except Exception as err:
                    logger.debug(f"Não foi possível recuperar pontos para feedback: {err}")
                    continue
                for point in points:
                    current_payload = point.payload or {}
                    new_value = int(current_payload.get(field, 0) or 0) + 1
                    update = {field: new_value}
                    self.client.set_payload(
                        collection_name=self.collection_name,
                        payload=update,
                        points=[point.id],
                    )
        except Exception as err:
            logger.debug(f"Falha ao aplicar feedback nos documentos: {err}")


vector_store_service = VectorStoreService()
