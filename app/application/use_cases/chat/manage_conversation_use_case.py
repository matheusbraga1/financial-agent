from typing import Optional, List, Dict, Any
import uuid
import json
import logging

logger = logging.getLogger(__name__)

class ManageConversationUseCase:
    def __init__(
        self,
        conversation_repository_port,
        vector_store_port,
    ):
        self.conversations = conversation_repository_port
        self.vector_store = vector_store_port
    
    def ensure_session(
        self, 
        session_id: Optional[str], 
        user_id: Optional[str]
    ) -> str:
        sid = session_id or str(uuid.uuid4())
        
        try:
            self.conversations.create_session(sid, user_id=user_id)
        except Exception as e:
            logger.warning(f"Falha ao criar sessão {sid}: {e}")
        
        return sid
    
    def get_history(
        self, 
        session_id: str, 
        user_id: Optional[str] = None,
        limit: int = 200
    ) -> List[Dict[str, Any]]:
        if not user_id:
            return []
        
        try:
            return self.conversations.get_history(
                session_id=session_id,
                limit=limit
            )
        except Exception as e:
            logger.warning(f"Erro ao buscar histórico: {e}")
            return []
    
    def add_user_message(self, session_id: str, content: str) -> None:
        try:
            self.conversations.add_message(
                session_id=session_id,
                role="user",
                content=content,
            )
        except Exception as e:
            logger.debug(f"Não foi possível registrar mensagem do usuário: {e}")
    
    def add_assistant_message(
        self,
        session_id: str,
        answer: str,
        sources: List[Dict[str, Any]],
        model_used: Optional[str],
        confidence: Optional[float],
    ) -> Optional[int]:
        try:
            sources_json = json.dumps(sources, ensure_ascii=False)
            
            message_id = self.conversations.add_message(
                session_id=session_id,
                role="assistant",
                answer=answer,
                sources=sources_json,
                model=model_used,
                confidence=confidence,
            )
            
            return message_id
            
        except Exception as e:
            logger.warning(f"Falha ao persistir resposta: {e}")
            return None
    
    def add_feedback(
        self,
        session_id: str,
        message_id: int,
        rating: str,
        comment: Optional[str] = None,
    ) -> bool:
        try:
            self.conversations.add_feedback(
                session_id=session_id,
                message_id=message_id,
                rating=rating,
                comment=comment,
            )
            
            message = self.conversations.get_message_by_id(message_id)
            
            if message and message.get("sources_json"):
                doc_ids = self._extract_doc_ids(message["sources_json"])
                
                if doc_ids:
                    helpful = self._is_helpful_rating(rating)
                    
                    try:
                        self.vector_store.apply_feedback(doc_ids, helpful)
                    except Exception as e:
                        logger.warning(f"Falha ao aplicar feedback aos documentos: {e}")
            
            logger.info(
                f"Feedback registrado: session={session_id}, "
                f"message={message_id}, rating={rating}"
            )
            
            return True
            
        except Exception as e:
            logger.error(f"Erro ao adicionar feedback: {e}")
            return False
    
    def get_user_sessions(
        self, 
        user_id: str, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        try:
            return self.conversations.get_user_sessions(
                user_id=user_id,
                limit=limit
            )
        except Exception as e:
            logger.error(f"Erro ao listar sessões: {e}")
            return []
    
    def delete_session(self, session_id: str, user_id: str) -> bool:
        try:
            session = self.conversations.get_session(session_id)
            
            if not session:
                return False
            
            owner_id = session.get("user_id")
            if owner_id and str(owner_id) != str(user_id):
                logger.warning(
                    f"Usuário {user_id} tentou deletar sessão de outro usuário"
                )
                return False
            
            deleted = self.conversations.delete_session(session_id)
            
            if deleted:
                logger.info(f"Sessão {session_id} deletada por usuário {user_id}")
            
            return deleted
            
        except Exception as e:
            logger.error(f"Erro ao deletar sessão: {e}")
            return False
    
    def _extract_doc_ids(self, sources_json: str) -> List[str]:
        try:
            sources = json.loads(sources_json)
            
            if isinstance(sources, list):
                return [
                    str(src.get("id")) 
                    for src in sources 
                    if src.get("id")
                ]
        except Exception:
            pass
        
        return []
    
    def _is_helpful_rating(self, rating: str) -> bool:
        helpful_values = {
            "positivo", "positive", "helpful", 
            "bom", "boa", "upvote", "like"
        }
        
        return rating.strip().lower() in helpful_values if rating else False