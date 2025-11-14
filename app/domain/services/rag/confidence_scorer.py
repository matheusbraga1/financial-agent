from typing import List, Dict, Any, Optional

class ConfidenceScorer:
    def __init__(
        self,
        weights: Optional[Dict[str, float]] = None,
        thresholds: Optional[Dict[str, float]] = None,
    ):
        self.weights = weights or {
            "document_score": 0.50,  
            "document_count": 0.20,  
            "domain_confidence": 0.15,
            "query_specificity": 0.15,
        }
        
        self.thresholds = thresholds or {
            "high": 0.75,
            "medium": 0.50,
            "low": 0.30,
        }
    
    def calculate(
        self,
        documents: List[Dict[str, Any]],
        query: str,
        domain_confidence: float = 0.0,
    ) -> Dict[str, Any]:
        if not documents:
            return self._no_documents_response()
        
        top_docs = documents[:3]
        avg_score = sum(d.get("score", 0.0) for d in top_docs) / len(top_docs)
        score_factor = avg_score * self.weights["document_score"]
        
        doc_count = len(documents)
        if doc_count >= 5:
            count_ratio = 1.0
        elif doc_count >= 3:
            count_ratio = 0.8
        elif doc_count >= 2:
            count_ratio = 0.5
        else:
            count_ratio = 0.3
        count_factor = count_ratio * self.weights["document_count"]
        
        domain_factor = domain_confidence * self.weights["domain_confidence"]
        
        query_words = len(query.split())
        if query_words >= 10:
            specificity = 1.0
        elif query_words >= 6:
            specificity = 0.7
        elif query_words >= 4:
            specificity = 0.5
        else:
            specificity = 0.3
        specificity_factor = specificity * self.weights["query_specificity"]
        
        final_score = (
            score_factor + 
            count_factor + 
            domain_factor + 
            specificity_factor
        )
        final_score = min(1.0, max(0.0, final_score))
        
        level, message = self._get_level_and_message(final_score)
        
        return {
            "score": round(final_score, 3),
            "level": level,
            "message": message,
            "factors": {
                "document_score": round(score_factor, 3),
                "document_count": round(count_factor, 3),
                "domain_confidence": round(domain_factor, 3),
                "query_specificity": round(specificity_factor, 3),
            },
            "details": {
                "avg_doc_score": round(avg_score, 3),
                "num_documents": doc_count,
                "query_length": query_words,
            }
        }
    
    def _get_level_and_message(self, score: float) -> tuple[str, str]:
        if score >= self.thresholds["high"]:
            return (
                "high",
                "Alta confiança - Informação precisa encontrada"
            )
        elif score >= self.thresholds["medium"]:
            return (
                "medium",
                "Confiança média - Informação relevante encontrada"
            )
        elif score >= self.thresholds["low"]:
            return (
                "low",
                "Baixa confiança - Informação parcial disponível"
            )
        else:
            return (
                "very_low",
                "Confiança muito baixa - Informação limitada"
            )
    
    def _no_documents_response(self) -> Dict[str, Any]:
        return {
            "score": 0.0,
            "level": "none",
            "message": "Nenhum documento relevante encontrado",
            "factors": {
                "document_score": 0.0,
                "document_count": 0.0,
                "domain_confidence": 0.0,
                "query_specificity": 0.0,
            },
            "details": {
                "avg_doc_score": 0.0,
                "num_documents": 0,
                "query_length": 0,
            }
        }