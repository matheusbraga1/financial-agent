"""Hybrid search strategy combining vector and text-based retrieval.

This module implements a sophisticated hybrid search that combines:
- Vector similarity (semantic search)
- BM25 text search (lexical search)
- Title boosting (exact matches)
- Category overlap
- Feedback signals (helpful votes, usage)
"""

import logging
import re
from typing import List, Dict, Any, Optional, Set
from app.shared.utils.text_processing import normalize_text, extract_words

logger = logging.getLogger(__name__)


class HybridSearchStrategy:
    """Hybrid search combining vector and text-based retrieval."""

    def __init__(
        self,
        vector_weight: float = 0.40,
        text_weight: float = 0.30,
        title_weight: float = 0.30,
        category_weight: float = 0.10,
    ):
        """Initialize hybrid search strategy.

        Args:
            vector_weight: Weight for vector similarity score
            text_weight: Weight for text overlap score
            title_weight: Weight for title overlap boost
            category_weight: Weight for category overlap boost
        """
        self.vector_weight = vector_weight
        self.text_weight = text_weight
        self.title_weight = title_weight
        self.category_weight = category_weight

        logger.info(
            f"HybridSearchStrategy initialized: "
            f"vector={vector_weight}, text={text_weight}, "
            f"title={title_weight}, category={category_weight}"
        )

    def _calculate_feedback_boost(self, payload: Optional[Dict[str, Any]]) -> float:
        """Calculate boost based on user feedback signals.

        Args:
            payload: Document payload with feedback data

        Returns:
            Boost value between -0.2 and 0.2
        """
        if not payload:
            return 0.0

        helpful = float(payload.get("helpful_votes", 0) or 0)
        complaints = float(payload.get("complaints", 0) or 0)
        usage = float(payload.get("usage_count", 0) or 0)

        if helpful == 0 and complaints == 0 and usage == 0:
            return 0.0

        # Feedback component: helpful vs complaints
        feedback_component = (helpful - complaints) / max(5.0, helpful + complaints + 1.0)

        # Popularity component: usage count
        popularity_component = min(0.1, usage / 500.0)

        boost = feedback_component + popularity_component

        # Clamp to reasonable range
        return max(-0.2, min(0.2, boost))

    def _calculate_text_score(
        self,
        query_words: Set[str],
        query_content_words: Set[str],
        document_text: str,
    ) -> float:
        """Calculate text overlap score using word sets.

        Args:
            query_words: All words from query
            query_content_words: Content words from query (no stopwords)
            document_text: Document text to compare

        Returns:
            Text similarity score (0-1)
        """
        doc_norm = normalize_text(document_text)
        doc_words = set(re.findall(r"\w+", doc_norm))

        # Use content words if available, else all words
        overlap_base = query_content_words if query_content_words else query_words

        if not overlap_base:
            return 0.0

        overlap_ratio = len(overlap_base.intersection(doc_words)) / len(overlap_base)

        # Heuristic scoring
        score = max(0.0, min(1.0, 0.2 + 0.8 * overlap_ratio))

        return score

    def _calculate_title_boost(
        self,
        query_content_words: Set[str],
        title: str,
    ) -> float:
        """Calculate boost for title matches.

        Args:
            query_content_words: Content words from query
            title: Document title

        Returns:
            Title boost (0-0.8)
        """
        title_normalized = normalize_text(title)
        title_words = set(re.findall(r"\w+", title_normalized))

        if not query_content_words or not title_words:
            return 0.0

        overlap = query_content_words.intersection(title_words)
        overlap_ratio = len(overlap) / len(query_content_words)

        if overlap_ratio > 0:
            boost = overlap_ratio * 0.8
            logger.debug(
                f"Title '{title}' has {overlap_ratio:.1%} overlap -> boost={boost:.2f}"
            )
            return boost

        return 0.0

    def _calculate_category_boost(
        self,
        query_content_words: Set[str],
        category: str,
    ) -> float:
        """Calculate boost for category matches.

        Args:
            query_content_words: Content words from query
            category: Document category

        Returns:
            Category boost (0-1)
        """
        if not category:
            return 0.0

        # Category-specific stopwords
        stopwords = {
            "e", "de", "do", "da", "das", "dos", "para", "em",
            "no", "na", "nas", "nos", "por", "um", "uma",
            "o", "a", "os", "as", "internas", "internos", "geral",
        }

        category_norm = normalize_text(category)
        cat_tokens = set(re.findall(r"\w+", category_norm)) - stopwords

        if not cat_tokens:
            return 0.0

        overlap = query_content_words.intersection(cat_tokens)
        overlap_ratio = len(overlap) / max(1, len(cat_tokens))

        # Limit boost to avoid dominating final score
        return max(0.0, min(1.0, overlap_ratio))

    def combine_results(
        self,
        query_text: str,
        vector_results: List[Any],
        text_results: List[Any],
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """Combine vector and text search results with hybrid scoring.

        Args:
            query_text: Original query text
            vector_results: Results from vector search
            text_results: Results from text/BM25 search
            score_threshold: Minimum score threshold

        Returns:
            Combined and scored documents
        """
        # Normalize query
        query_normalized = normalize_text(query_text)
        query_words = set(re.findall(r"\w+", query_normalized))

        # Extract content words (no stopwords)
        stopwords_q = {
            "a", "o", "as", "os", "um", "uma", "uns", "umas",
            "de", "do", "da", "dos", "das",
            "e", "em", "no", "na", "nos", "nas",
            "para", "por", "com", "sem", "ao", "aos",
            "que", "como", "ser", "estar", "ter", "fazer",
            "nao", "duvida", "duvidas", "pergunta", "perguntas",
        }
        query_content_words = query_words - stopwords_q

        # Special handling for VPN queries
        has_vpn = "vpn" in query_words

        # Combine results
        combined_scores: Dict[str, Dict[str, Any]] = {}

        # Process vector results
        for result in vector_results:
            doc_id = result.id
            combined_scores[doc_id] = {
                "vector_score": result.score,
                "text_score": 0.0,
                "title_boost": 0.0,
                "category_boost": 0.0,
                "payload": result.payload,
            }

        # Process text results
        for point in text_results:
            doc_id = point.id
            payload = point.payload

            # Calculate text score
            text_for_overlap = payload.get("search_text") or (
                (payload.get("title") or "") + " " + (payload.get("content") or "")
            )
            text_norm = normalize_text(text_for_overlap)
            text_words = set(re.findall(r"\w+", text_norm))

            overlap_base = query_content_words if query_content_words else query_words
            overlap_ratio = (
                len(overlap_base.intersection(text_words)) / len(overlap_base)
                if overlap_base else 0.0
            )

            text_score = max(0.0, min(1.0, 0.2 + 0.8 * overlap_ratio))

            # VPN-specific penalty
            if has_vpn and not ({"vpn", "virtual", "remoto", "forticlient", "anyconnect"} & text_words):
                text_score *= 0.5

            if doc_id in combined_scores:
                combined_scores[doc_id]["text_score"] = text_score
            else:
                combined_scores[doc_id] = {
                    "vector_score": 0.0,
                    "text_score": text_score,
                    "title_boost": 0.0,
                    "category_boost": 0.0,
                    "payload": payload,
                }

        # Calculate title and category boosts
        for doc_id, scores in combined_scores.items():
            title = scores["payload"].get("title", "")
            category = scores["payload"].get("category", "")

            scores["title_boost"] = self._calculate_title_boost(query_content_words, title)
            scores["category_boost"] = self._calculate_category_boost(query_content_words, category)

        # Calculate final scores
        final_results: List[Dict[str, Any]] = []
        for doc_id, scores in combined_scores.items():
            # Weighted combination
            final_score = (
                (scores["vector_score"] * self.vector_weight) +
                (scores["text_score"] * self.text_weight) +
                (scores["title_boost"] * self.title_weight) +
                (scores["category_boost"] * self.category_weight)
            )

            # Add feedback boost
            final_score += self._calculate_feedback_boost(scores["payload"])

            # Clamp to [0, 1]
            final_score = max(0.0, min(1.0, final_score))

            # Apply threshold
            if score_threshold is None or final_score >= score_threshold:
                final_results.append({
                    "id": doc_id,
                    "score": final_score,
                    "title": scores["payload"].get("title"),
                    "category": scores["payload"].get("category"),
                    "content": scores["payload"].get("content"),
                    "metadata": scores["payload"].get("metadata", {}),
                })

        # Sort by score
        final_results.sort(key=lambda x: x["score"], reverse=True)

        logger.debug(
            f"Hybrid search combined {len(final_results)} documents "
            f"from {len(vector_results)} vector + {len(text_results)} text results"
        )

        return final_results

    def apply_anchor_gating(
        self,
        query_text: str,
        documents: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Apply anchor term gating to filter irrelevant documents.

        Args:
            query_text: Original query
            documents: Documents to filter

        Returns:
            Filtered documents containing anchor terms
        """
        query_normalized = normalize_text(query_text)
        query_words = set(re.findall(r"\w+", query_normalized))

        # Stopwords to exclude from anchors
        anchor_stop = {
            "rede", "conectar", "conexao", "acessar", "acesso",
            "gerenciador", "aplicativo", "dispositivo",
            "empresa", "corporativa", "sistema", "plataforma",
        }

        # Extract anchor terms (content words minus stopwords)
        query_content_words = extract_words(query_text, remove_stopwords=True)
        anchors = {w for w in query_content_words if w not in anchor_stop}

        if not anchors:
            return documents

        def doc_has_anchor(doc: Dict[str, Any]) -> bool:
            """Check if document contains any anchor term."""
            text = f"{doc.get('title', '')} {doc.get('content', '')}"
            norm = normalize_text(text)
            tokens = set(re.findall(r"\w+", norm))
            return bool(anchors & tokens)

        # Check if any document has anchors
        any_with_anchor = any(doc_has_anchor(d) for d in documents)

        if any_with_anchor:
            filtered = [d for d in documents if doc_has_anchor(d)]
            if filtered:
                logger.debug(
                    f"Anchor gating applied - kept {len(filtered)}/{len(documents)} documents"
                )
                return filtered

        return documents
