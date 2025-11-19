from typing import Protocol, List, Dict, Any, Optional

class VectorStorePort(Protocol):
    def search_similar(
        self,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        ...
    
    def search_hybrid(
        self,
        query_text: str,
        query_vector: List[float],
        limit: int = 10,
        score_threshold: Optional[float] = None,
        filter: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        ...
    
    def upsert(
        self,
        id: str,
        vector: List[float],
        metadata: Dict[str, Any],
    ) -> None:
        ...
    
    def delete(self, id: str) -> bool:
        ...
    
    def get_stats(self) -> Dict[str, Any]:
        ...
    
    def record_usage(self, doc_ids: List[str]) -> None:
        ...
    
    def apply_feedback(self, doc_ids: List[str], helpful: bool) -> None:
        ...