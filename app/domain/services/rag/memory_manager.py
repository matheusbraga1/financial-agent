from typing import List, Dict, Any, Optional
import hashlib
import uuid
import logging

logger = logging.getLogger(__name__)

class MemoryManager:
    def __init__(
        self,
        embeddings_port,
        vector_store_port,
        min_confidence: float = 0.55,
        min_answer_length: int = 40,
    ):
        self.embeddings = embeddings_port
        self.vector_store = vector_store_port
        self.min_confidence = min_confidence
        self.min_answer_length = min_answer_length
    
    def store_if_worthy(
        self,
        question: str,
        answer: str,
        source_documents: Optional[List[Dict[str, Any]]],
        detected_departments: Optional[List[str]],
        confidence: float,
    ) -> bool:
        if not question or not question.strip():
            logger.debug("Memória não armazenada: pergunta vazia")
            return False
        
        if not answer or not answer.strip():
            logger.debug("Memória não armazenada: resposta vazia")
            return False
        
        if confidence < self.min_confidence:
            logger.debug(
                f"Memória não armazenada: confiança baixa ({confidence:.2f} < {self.min_confidence})"
            )
            return False
        
        if len(answer.strip()) < self.min_answer_length:
            logger.debug(
                f"Memória não armazenada: resposta curta ({len(answer)} < {self.min_answer_length})"
            )
            return False
        
        primary_department = (detected_departments or ["Geral"])[0]
        
        metadata = {
            "doc_type": "qa_memory",
            "department": primary_department,
            "departments": detected_departments or ["Geral"],
            "tags": ["qa_memory"],
            "source_ids": [
                str(ref.get("id")) 
                for ref in (source_documents or []) 
                if ref.get("id")
            ],
            "source_titles": [
                str(ref.get("title")) 
                for ref in (source_documents or []) 
                if ref.get("title")
            ],
            "confidence": confidence,
            "origin": "chat_history",
        }
        
        memory_key = self._generate_memory_key(question)
        memory_id = str(uuid.uuid5(uuid.NAMESPACE_URL, memory_key))
        
        metadata["memory_key"] = memory_key
        
        try:
            title = question[:200]
            content = answer
            
            vector = self.embeddings.encode_document(title, content)
            
            self.vector_store.upsert(
                id=memory_id,
                vector=vector,
                metadata={
                    "title": title,
                    "category": primary_department or "QA Memory",
                    "content": content,
                    "metadata": metadata,
                },
            )
            
            logger.info(
                f"Memória QA armazenada: '{title[:50]}...' "
                f"(confidence: {confidence:.2f}, dept: {primary_department})"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao armazenar memória QA: {e}", exc_info=True)
            return False
    
    def _generate_memory_key(self, question: str) -> str:
        normalized = question.strip().lower()
        hash_digest = hashlib.sha256(normalized.encode('utf-8')).hexdigest()
        
        return f"qa_memory_{hash_digest[:24]}"