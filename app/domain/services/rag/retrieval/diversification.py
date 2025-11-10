"""MMR (Maximal Marginal Relevance) diversification for search results.

MMR balances relevance and diversity to avoid returning too many similar documents.
"""

import logging
from typing import List, Dict, Any, Set
from app.shared.utils.text_processing import normalize_text
import re

logger = logging.getLogger(__name__)


def _jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """Calculate Jaccard similarity between two sets.

    Args:
        set_a: First set of words
        set_b: Second set of words

    Returns:
        Jaccard similarity score (0-1)
    """
    if not set_a or not set_b:
        return 0.0

    intersection = len(set_a.intersection(set_b))
    union = len(set_a.union(set_b))

    return intersection / union if union else 0.0


def _extract_word_set(document: Dict[str, Any]) -> Set[str]:
    """Extract normalized word set from document.

    Args:
        document: Document dict with 'title' and 'content'

    Returns:
        Set of normalized words
    """
    title = document.get("title", "") or ""
    content = document.get("content", "") or ""
    text = f"{title} {content}"

    normalized = normalize_text(text)
    return set(re.findall(r"\w+", normalized))


def apply_mmr_diversification(
    documents: List[Dict[str, Any]],
    lambda_param: float = 0.7,
    max_results: int = 20,
) -> List[Dict[str, Any]]:
    """Apply MMR (Maximal Marginal Relevance) for diversity.

    MMR selects documents that are relevant but also diverse from
    already selected documents, preventing redundant results.

    Args:
        documents: List of candidate documents (sorted by relevance)
        lambda_param: Balance between relevance (1.0) and diversity (0.0)
                     Default 0.7 = 70% relevance, 30% diversity
        max_results: Maximum number of documents to return

    Returns:
        Diversified list of documents

    Algorithm:
        MMR = λ * Relevance - (1-λ) * max_similarity_to_selected
    """
    if not documents:
        return []

    if len(documents) <= 1:
        return documents

    logger.debug(
        f"Applying MMR diversification: {len(documents)} candidates, "
        f"lambda={lambda_param}, max={max_results}"
    )

    # Precompute word sets for all candidates
    candidate_wordsets = {
        doc["id"]: _extract_word_set(doc)
        for doc in documents
    }

    # Track selected documents
    selected: List[Dict[str, Any]] = []
    remaining = documents.copy()
    k = min(max_results, len(documents))

    while remaining and len(selected) < k:
        best_doc = None
        best_score = float("-inf")

        for candidate in remaining:
            relevance = candidate.get("score", 0.0)

            # First document: pure relevance
            if not selected:
                diversity_penalty = 0.0
            else:
                # Calculate max similarity to already selected documents
                cand_words = candidate_wordsets[candidate["id"]]
                max_similarity = max(
                    _jaccard_similarity(cand_words, candidate_wordsets[sel["id"]])
                    for sel in selected
                )
                diversity_penalty = max_similarity

            # MMR score
            mmr_score = (lambda_param * relevance) - ((1 - lambda_param) * diversity_penalty)

            if mmr_score > best_score:
                best_score = mmr_score
                best_doc = candidate

        if best_doc is not None:
            selected.append(best_doc)
            remaining.remove(best_doc)

    logger.debug(
        f"MMR diversification complete: selected {len(selected)}/{len(documents)} documents"
    )

    return selected
