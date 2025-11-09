"""Extensão do VectorStoreService com suporte multi-domínio."""

from typing import List, Dict, Any, Optional
import logging

from app.services.vector_store_service import VectorStoreService
from app.services.vector_store_domain_filters import VectorStoreDomainFilters
from qdrant_client.models import Filter, FieldCondition, MatchText
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class VectorStoreMultidomain(VectorStoreService):
    """
    Extensão do VectorStoreService com filtros por departamento e tipo de documento.

    Adiciona capacidade de filtrar resultados por:
    - Departamento (TI, RH, Financeiro, etc.)
    - Tipo de documento (article, policy, contract, etc.)
    """

    def __init__(self):
        super().__init__()
        self.filter_builder = VectorStoreDomainFilters()

    def search_hybrid_filtered(
        self,
        query_text: str,
        query_vector: List[float],
        limit: int | None = None,
        score_threshold: float | None = None,
        departments: Optional[List[str]] = None,
        doc_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Busca híbrida com filtros por departamento e tipo de documento.

        Args:
            query_text: Texto da pergunta (para BM25)
            query_vector: Vetor da pergunta (para busca semântica)
            limit: Número de resultados
            score_threshold: Score mínimo
            departments: Lista de departamentos para filtrar (ex: ["TI", "RH"])
            doc_types: Lista de tipos de documento (ex: ["article", "policy"])

        Returns:
            List[Dict]: Documentos encontrados (filtrados e reranqueados)
        """
        limit = limit or settings.top_k_results
        initial_limit = max(limit * 3, 20)

        # Construir filtro de departamento/doc_type
        dept_filter = self.filter_builder.build_department_filter(
            departments=departments,
            doc_types=doc_types
        )

        try:
            self._ensure_collection()

            # 1. Busca vetorial com filtro
            vector_results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_vector,
                query_filter=dept_filter,  # Aplicar filtro aqui
                limit=initial_limit,
                with_payload=True,
            )

            # 2. Busca textual com filtro
            # Construir filtro combinado (texto + departamento)
            text_filter_conditions = [
                FieldCondition(key="search_text", match=MatchText(text=query_text))
            ]

            # Adicionar condições de departamento ao filtro de texto
            if dept_filter and hasattr(dept_filter, 'must') and dept_filter.must:
                text_filter_conditions.extend(dept_filter.must)

            text_filter = Filter(must=text_filter_conditions)

            text_results = self.client.scroll(
                collection_name=self.collection_name,
                scroll_filter=text_filter,
                limit=initial_limit,
                with_payload=True,
                with_vectors=False,
            )[0]

        except Exception as e:
            logger.warning(f"Busca híbrida filtrada falhou (Qdrant offline?): {e}")
            return []

        # Log de debug
        if departments:
            logger.info(f"Busca filtrada por departamentos: {departments}")
        if doc_types:
            logger.info(f"Busca filtrada por tipos: {doc_types}")

        logger.debug(f"Vector results: {len(vector_results)}, Text results: {len(text_results)}")

        # Reutilizar toda a lógica de scoring híbrido do método pai
        # (copiar a lógica de combinação, MMR, reranking, etc.)

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

        stopwords_q = {
            "a", "o", "as", "os", "um", "uma", "uns", "umas", "de", "do", "da",
            "dos", "das", "e", "em", "no", "na", "nos", "nas", "para", "por",
            "com", "sem", "ao", "aos", "que", "como", "ser", "estar", "ter",
            "fazer", "nao", "duvida", "duvidas", "pergunta", "perguntas",
        }
        query_content_words = {w for w in query_words if w not in stopwords_q}

        combined_scores: Dict[str, Dict[str, Any]] = {}

        # Processar resultados vetoriais
        for result in vector_results:
            doc_id = result.id
            combined_scores[doc_id] = {
                "vector_score": result.score,
                "text_score": 0.0,
                "title_boost": 0.0,
                "payload": result.payload,
            }

        # Processar resultados textuais
        for point in text_results:
            doc_id = point.id
            payload = point.payload
            text_for_overlap = payload.get("search_text") or (
                (payload.get("title") or "") + " " + (payload.get("content") or "")
            )
            text_norm = normalize_text(text_for_overlap)
            text_words = set(re.findall(r"\w+", text_norm))

            overlap_base = query_content_words if query_content_words else query_words
            overlap_ratio = (
                len(overlap_base.intersection(text_words)) / len(overlap_base)
                if overlap_base
                else 0.0
            )
            heuristic_text_score = max(0.0, min(1.0, 0.2 + 0.8 * overlap_ratio))

            if doc_id in combined_scores:
                combined_scores[doc_id]["text_score"] = heuristic_text_score
            else:
                combined_scores[doc_id] = {
                    "vector_score": 0.0,
                    "text_score": heuristic_text_score,
                    "title_boost": 0.0,
                    "payload": payload,
                }

        # Title boost
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

        # Category boost
        stopwords = {
            "e", "de", "do", "da", "das", "dos", "para", "em", "no", "na",
            "nas", "nos", "por", "um", "uma", "o", "a", "os", "as",
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
            scores["category_boost"] = max(0.0, min(1.0, overlap_ratio))

        # Calcular score final
        final_results: List[Dict[str, Any]] = []
        for doc_id, scores in combined_scores.items():
            final_score = (
                (scores["vector_score"] * 0.40)
                + (scores["text_score"] * 0.30)
                + (scores["title_boost"] * 0.30)
                + (scores.get("category_boost", 0.0) * 0.10)
            )
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
                        "department": scores["payload"].get("department"),  # Incluir department
                        "doc_type": scores["payload"].get("doc_type"),  # Incluir doc_type
                    }
                )

        final_results.sort(key=lambda x: x["score"], reverse=True)

        # Aplicar reranking
        if self._reranking_enabled and len(final_results) > 1:
            final_results = self._rerank_results(query_text, final_results[:initial_limit])
            logger.debug("Reranking aplicado com CrossEncoder")

        # Enforce final score threshold
        final_min = score_threshold if score_threshold is not None else 0.0
        final_results = [d for d in final_results if d.get("score", 0.0) >= final_min]

        # Deduplicate
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

        logger.info(f"Retornando {len(deduped[:limit])} documentos filtrados")
        return deduped[:limit]


# Instância singleton
vector_store_multidomain = VectorStoreMultidomain()
