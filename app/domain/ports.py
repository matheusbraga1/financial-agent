from __future__ import annotations

from typing import Protocol, List, Dict, Any, Optional, AsyncIterator, Tuple, Iterable

from app.models.chat import ChatResponse


class EmbeddingsPort(Protocol):
    def encode_text(self, text: str, use_cache: bool = True) -> List[float]:
        ...

    def encode_batch(self, texts: List[str]) -> List[List[float]]:
        ...

    def encode_document(self, title: str, content: str, title_weight: int = 3) -> List[float]:
        ...


class VectorStorePort(Protocol):
    def add_document(self, document, vector: List[float], document_id: Optional[str] = None) -> str:
        ...

    def search_similar(
        self,
        query_vector: List[float],
        limit: int | None = None,
        score_threshold: float | None = None,
    ) -> List[Dict[str, Any]]:
        ...

    def search_hybrid(
        self,
        query_text: str,
        query_vector: List[float],
        limit: int | None = None,
        score_threshold: float | None = None,
    ) -> List[Dict[str, Any]]:
        ...

    def get_collection_info(self) -> Dict[str, Any]:
        ...


class RAGPort(Protocol):
    model: str

    async def generate_answer(
        self,
        question: str,
        top_k: int | None = None,
        min_score: float | None = None,
        history_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatResponse:
        ...

    async def stream_answer(
        self,
        question: str,
        history_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Tuple[str, Any]]:
        ...


class LLMPort(Protocol):
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> str:
        ...

    def stream(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        options: Optional[Dict[str, Any]] = None,
    ) -> Iterable[str]:
        ...


# Conversas / histÃ³rico
class ConversationPort(Protocol):
    def ensure_session(self, session_id: str, user_id: Optional[str] = None) -> None:
        ...

    def get_conversation(self, session_id: str) -> Optional[Dict[str, Any]]:
        ...

    def add_user_message(self, session_id: str, content: str) -> None:
        ...

    def add_assistant_message(
        self,
        session_id: str,
        answer: str,
        sources_json: Optional[str],
        model_used: Optional[str],
        confidence: Optional[float],
    ) -> None:
        ...

    def get_history(self, session_id: str, limit: int = 100) -> List[Dict[str, Any]]:
        ...


# RAG subcomponentes (para SRP e fÃ¡cil substituiÃ§Ã£o)
class QueryExpanderPort(Protocol):
    def expand(self, question: str) -> str:
        ...

    def adaptive_params(self, question: str) -> Dict[str, Any]:
        ...


class RetrieverPort(Protocol):
    def retrieve(
        self,
        question_text: str,
        top_k: int,
        min_score: float,
    ) -> List[Dict[str, Any]]:
        ...


class AnswerFormatterPort(Protocol):
    def build_context(self, documents: List[Dict[str, Any]]) -> str:
        ...

    def build_prompt(self, question: str, context: str, history: str = "") -> str:
        ...

    def sanitize(self, text: str) -> str:
        ...


class ClarifierPort(Protocol):
    def maybe_clarify(self, question: str, documents: Optional[List[Dict[str, Any]]] = None) -> Optional[str]:
        """Retorna uma pergunta de esclarecimento se a pergunta original for genérica/ambígua.

        Caso contrário, retorna None.
        """
        ...
