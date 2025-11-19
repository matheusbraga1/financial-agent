from typing import List, Dict, Any, Optional
import logging
import re

logger = logging.getLogger(__name__)

class HybridSearchStrategy:
    def __init__(
        self,
        vector_weight: float = 0.7,
        text_weight: float = 0.3,
        rrf_k: int = 60,
    ):
        self.vector_weight = vector_weight
        self.text_weight = text_weight
        self.rrf_k = rrf_k
        
        total = vector_weight + text_weight
        self.vector_weight = vector_weight / total
        self.text_weight = text_weight / total
        
        logger.info(
            f"HybridSearchStrategy inicializada: "
            f"vector_weight={self.vector_weight:.2f}, "
            f"text_weight={self.text_weight:.2f}, "
            f"rrf_k={rrf_k}"
        )
    
    def combine_results(
        self,
        query_text: str,
        vector_results: List[Any],
        text_results: List[Any],
        score_threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        docs_by_id: Dict[str, Dict[str, Any]] = {}
        
        for rank, result in enumerate(vector_results, start=1):
            doc_id = str(result.id) if hasattr(result, 'id') else str(result.get('id'))
            
            if hasattr(result, 'payload'):
                payload = result.payload
            else:
                payload = result
            
            docs_by_id[doc_id] = {
                "id": doc_id,
                "title": payload.get("title", ""),
                "content": payload.get("content", ""),
                "category": payload.get("category", ""),
                "metadata": payload.get("metadata", {}),
                "vector_score": float(result.score) if hasattr(result, 'score') else float(result.get('score', 0.0)),
                "vector_rank": rank,
                "text_score": 0.0,
                "text_rank": 0,
            }
        
        for rank, result in enumerate(text_results, start=1):
            doc_id = str(result.id) if hasattr(result, 'id') else str(result.get('id'))
            
            if doc_id in docs_by_id:
                docs_by_id[doc_id]["text_score"] = float(result.score) if hasattr(result, 'score') else float(result.get('score', 0.0))
                docs_by_id[doc_id]["text_rank"] = rank
            else:
                if hasattr(result, 'payload'):
                    payload = result.payload
                else:
                    payload = result
                
                docs_by_id[doc_id] = {
                    "id": doc_id,
                    "title": payload.get("title", ""),
                    "content": payload.get("content", ""),
                    "category": payload.get("category", ""),
                    "metadata": payload.get("metadata", {}),
                    "vector_score": 0.0,
                    "vector_rank": 0,
                    "text_score": float(result.score) if hasattr(result, 'score') else float(result.get('score', 0.0)),
                    "text_rank": rank,
                }
        
        for doc_id, doc in docs_by_id.items():
            vector_rank = doc["vector_rank"]
            text_rank = doc["text_rank"]
            
            vector_rrf = 1.0 / (self.rrf_k + vector_rank) if vector_rank > 0 else 0.0
            text_rrf = 1.0 / (self.rrf_k + text_rank) if text_rank > 0 else 0.0
            
            rrf_score = (
                self.vector_weight * vector_rrf +
                self.text_weight * text_rrf
            )
            
            doc["rrf_score"] = rrf_score
            
            doc["score"] = min(1.0, (
                0.5 * rrf_score * 100 +
                0.3 * doc["vector_score"] +
                0.2 * doc["text_score"]
            ))
        
        sorted_docs = sorted(
            docs_by_id.values(),
            key=lambda x: x["score"],
            reverse=True
        )
        
        if score_threshold is not None:
            sorted_docs = [
                doc for doc in sorted_docs
                if doc["score"] >= score_threshold
            ]
        
        logger.debug(
            f"Hybrid search combinou {len(vector_results)} vetoriais + "
            f"{len(text_results)} textuais = {len(sorted_docs)} resultados finais"
        )
        
        return sorted_docs
    
    def apply_anchor_gating(
        self,
        query_text: str,
        documents: List[Dict[str, Any]],
        threshold: float = 0.3,
    ) -> List[Dict[str, Any]]:
        if not documents:
            return []
        
        keywords = self._extract_query_keywords(query_text)
        
        if not keywords:
            return documents
        
        logger.debug(f"Anchor gating com keywords: {keywords}")
        
        filtered_docs = []
        
        for doc in documents:
            doc_text = f"{doc.get('title', '')} {doc.get('content', '')}".lower()
            
            matches = sum(1 for kw in keywords if kw in doc_text)
            match_ratio = matches / len(keywords)
            
            if match_ratio >= threshold:
                filtered_docs.append(doc)
            else:
                logger.debug(
                    f"Documento filtrado por anchor gating: '{doc.get('title', '')[:40]}' "
                    f"(match_ratio={match_ratio:.2f})"
                )
        
        logger.debug(
            f"Anchor gating: {len(documents)} docs -> {len(filtered_docs)} docs "
            f"(threshold={threshold})"
        )
        
        return filtered_docs
    
    def _extract_query_keywords(self, query: str) -> List[str]:
        stop_words = {
            "o", "a", "os", "as", "um", "uma", "uns", "umas",
            "de", "da", "do", "das", "dos",
            "em", "no", "na", "nos", "nas",
            "para", "por", "com", "sem", "sobre",
            "é", "são", "está", "estão", "foi", "eram",
            "que", "qual", "quais", "como", "onde", "quando",
            "me", "te", "se", "nos", "lhe", "lhes",
            "meu", "teu", "seu", "nosso", "vosso",
            "este", "esse", "aquele", "isto", "isso", "aquilo",
            "e", "ou", "mas", "pois", "porém", "contudo",
        }
        
        query_clean = re.sub(r'[^\w\s]', ' ', query.lower())
        words = query_clean.split()
        
        keywords = [
            word for word in words
            if len(word) >= 3 and word not in stop_words
        ]
        
        return keywords