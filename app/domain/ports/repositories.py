from typing import Protocol, Optional, List, Dict, Any
from datetime import datetime

class ConversationRepositoryPort(Protocol):
    def create_session(
        self, 
        session_id: str, 
        user_id: Optional[str] = None
    ) -> None:
        ...
    
    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        ...
    
    def add_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        answer: Optional[str] = None,
        sources: Optional[str] = None,
        model: Optional[str] = None,
        confidence: Optional[float] = None,
    ) -> int:
        ...
    
    def get_history(
        self, 
        session_id: str, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        ...
    
    def get_message_by_id(self, message_id: int) -> Optional[Dict[str, Any]]:
        ...
    
    def add_feedback(
        self,
        session_id: str,
        message_id: int,
        rating: str,
        comment: Optional[str] = None,
    ) -> int:
        ...
    
    def get_user_sessions(
        self, 
        user_id: str, 
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        ...
    
    def delete_session(self, session_id: str) -> bool:
        ...


class UserRepositoryPort(Protocol):
    def create_user(
        self,
        username: str,
        email: str,
        hashed_password: str,
        is_active: bool = True,
        is_admin: bool = False,
    ) -> int:
        ...
    
    def get_user_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        ...
    
    def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        ...
    
    def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        ...
    
    def update_user(self, user_id: int, **fields) -> bool:
        ...
    
    def delete_user(self, user_id: int) -> bool:
        ...