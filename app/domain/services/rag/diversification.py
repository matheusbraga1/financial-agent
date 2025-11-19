from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

def apply_mmr_diversification(
    documents: List[Dict[str, Any]],
    lambda_param: float = 0.7,
    max_results: Optional[int] = None,
) -> List[Dict[str, Any]]:
    if not documents or len(documents) <= 1:
        return documents
    
    if lambda_param >= 0.99:    
        return documents[:max_results] if max_results else documents
    
    logger.debug(
        f"Aplicando MMR diversification: {len(documents)} docs, "
        f"lambda={lambda_param}"
    )
    
    selected: List[Dict[str, Any]] = []
    
    candidates = documents.copy()
    
    if candidates:
        selected.append(candidates.pop(0))
    
    target_count = max_results if max_results else len(documents)
    
    while candidates and len(selected) < target_count:
        best_doc = None
        best_mmr_score = -float('inf')
        best_idx = -1
        
        for idx, candidate in enumerate(candidates):
            relevance = candidate.get("score", 0.0)
            
            max_similarity = 0.0
            for selected_doc in selected:
                similarity = _calculate_similarity(candidate, selected_doc)
                max_similarity = max(max_similarity, similarity)
            
            mmr_score = (
                lambda_param * relevance -
                (1 - lambda_param) * max_similarity
            )
            
            if mmr_score > best_mmr_score:
                best_mmr_score = mmr_score
                best_doc = candidate
                best_idx = idx
        
        if best_doc:
            selected.append(best_doc)
            candidates.pop(best_idx)
            
            logger.debug(
                f"MMR selecionou: '{best_doc.get('title', '')[:40]}' "
                f"(mmr_score={best_mmr_score:.3f})"
            )
    
    logger.debug(
        f"MMR diversification concluída: {len(selected)} docs selecionados"
    )
    
    return selected

def _calculate_similarity(doc1: Dict[str, Any], doc2: Dict[str, Any]) -> float:
    similarity = 0.0
    
    title1 = set(doc1.get("title", "").lower().split())
    title2 = set(doc2.get("title", "").lower().split())
    
    if title1 and title2:
        intersection = len(title1 & title2)
        union = len(title1 | title2)
        title_sim = intersection / union if union > 0 else 0.0
        similarity += 0.4 * title_sim
    
    if doc1.get("category") and doc2.get("category"):
        if doc1["category"].lower() == doc2["category"].lower():
            similarity += 0.3
    
    meta1 = doc1.get("metadata", {})
    meta2 = doc2.get("metadata", {})
    
    dept1 = meta1.get("department", "").lower()
    dept2 = meta2.get("department", "").lower()
    
    if dept1 and dept2 and dept1 == dept2:
        similarity += 0.2
    
    content1 = set(doc1.get("content", "")[:1000].lower().split())
    content2 = set(doc2.get("content", "")[:1000].lower().split())
    
    if content1 and content2:
        intersection = len(content1 & content2)
        union = len(content1 | content2)
        content_sim = intersection / union if union > 0 else 0.0
        similarity += 0.1 * content_sim
    
    return min(1.0, similarity)