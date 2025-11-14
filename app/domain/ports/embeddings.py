from typing import Protocol, List

class EmbeddingsPort(Protocol):
    def encode_text(self, text: str) -> List[float]:
        ...
    
    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        ...
    
    def encode_document(
        self, 
        title: str, 
        content: str, 
        title_weight: int = 3
    ) -> List[float]:
        ...