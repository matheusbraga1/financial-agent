from fastapi import Depends

from app.domain.ports import (
    RAGPort,
    VectorStorePort,
    EmbeddingsPort,
    ConversationPort,
    LLMPort,
)
from app.services.user_service import user_service, UserService
from app.repositories.sqlite_conversation_repository import conversation_repository
from app.application.chat_usecase import ChatUseCase


def get_embedding_service() -> EmbeddingsPort:
    # Import lazy para evitar custo em endpoints que não usam embeddings
    from app.services.embedding_service import embedding_service
    yield embedding_service


def get_vector_store() -> VectorStorePort:
    # Import lazy para evitar inicialização desnecessária
    from app.services.vector_store_service import vector_store_service
    yield vector_store_service


def get_llm() -> LLMPort:
    """
    Get LLM provider based on configuration.

    Supports:
    - 'groq': Groq API only (fast)
    - 'ollama': Ollama only (local)
    - 'hybrid': Groq with Ollama fallback (recommended)
    """
    from app.core.config import get_settings
    from app.infrastructure.llm import GroqAdapter, OllamaAdapter, HybridLLMService

    settings = get_settings()
    provider = settings.llm_provider.lower()

    if provider == "groq":
        # Groq only
        yield GroqAdapter(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            timeout=settings.groq_timeout,
        )
    elif provider == "ollama":
        # Ollama only
        yield OllamaAdapter(
            host=settings.ollama_host,
            model=settings.ollama_model,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            timeout=settings.ollama_timeout,
        )
    else:
        # Hybrid (default): Groq first, Ollama fallback
        groq = None
        ollama = None

        if settings.groq_api_key:
            groq = GroqAdapter(
                api_key=settings.groq_api_key,
                model=settings.groq_model,
                temperature=settings.llm_temperature,
                top_p=settings.llm_top_p,
                timeout=settings.groq_timeout,
            )

        ollama = OllamaAdapter(
            host=settings.ollama_host,
            model=settings.ollama_model,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            timeout=settings.ollama_timeout,
        )

        yield HybridLLMService(
            groq_adapter=groq,
            ollama_adapter=ollama,
            prefer_groq=True,
        )


def get_rag_service(
    emb: EmbeddingsPort = Depends(get_embedding_service),
    vs: VectorStorePort = Depends(get_vector_store),
    llm: LLMPort = Depends(get_llm),
) -> RAGPort:
    # Import lazy para evitar custo em endpoints que não usam RAG
    # RAG Service com melhorias multi-domínio de precisão integradas
    from app.services.rag_service import RAGService
    yield RAGService(embedding_service=emb, vector_store=vs, llm=llm)


def get_conversation_repo() -> ConversationPort:
    yield conversation_repository


def get_user_service() -> UserService:
    yield user_service


def get_chat_usecase(
    rag: RAGPort = Depends(get_rag_service),
    conv: ConversationPort = Depends(get_conversation_repo),
):
    yield ChatUseCase(rag=rag, conversations=conv)
