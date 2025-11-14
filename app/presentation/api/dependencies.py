from typing import Optional
from functools import lru_cache
import logging

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from app.infrastructure.config.settings import get_settings

from app.domain.services.rag.query_processor import QueryProcessor
from app.domain.services.rag.domain_classifier import DomainClassifier
from app.domain.services.rag.confidence_scorer import ConfidenceScorer
from app.domain.services.rag.answer_generator import AnswerGenerator
from app.domain.services.rag.document_retriever import DocumentRetriever
from app.domain.services.rag.memory_manager import MemoryManager
from app.domain.services.documents.document_processor import DocumentProcessor

from app.domain.services.rag.reranking.cross_encoder_reranker import CrossEncoderReranker
from app.domain.services.rag.clarifier import Clarifier
from app.domain.services.rag.hybrid_search import HybridSearchStrategy

from app.infrastructure.adapters.llm.groq_adapter import GroqAdapter
from app.infrastructure.adapters.llm.ollama_adapter import OllamaAdapter
from app.infrastructure.adapters.llm.hybrid_llm_adapter import HybridLLMAdapter
from app.infrastructure.adapters.embeddings.sentence_transformer_adapter import SentenceTransformerAdapter
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter

from app.infrastructure.repositories.conversation_repository import conversation_repository
from app.infrastructure.repositories.user_repository import user_repository

from app.application.use_cases.chat.generate_answer_use_case import GenerateAnswerUseCase
from app.application.use_cases.chat.stream_answer_use_case import StreamAnswerUseCase
from app.application.use_cases.chat.manage_conversation_use_case import ManageConversationUseCase
from app.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase

logger = logging.getLogger(__name__)

security = HTTPBearer()

@lru_cache()
def get_embeddings_adapter() -> SentenceTransformerAdapter:
    settings = get_settings()
    
    logger.info("Inicializando SentenceTransformerAdapter (singleton)")
    
    return SentenceTransformerAdapter(
        model_name=settings.embedding_model,
        device="cpu",
        normalize=True,
    )

@lru_cache()
def get_vector_store_adapter() -> QdrantAdapter:
    settings = get_settings()
    
    logger.info("Inicializando QdrantAdapter (singleton)")
    
    return QdrantAdapter(
        host=settings.qdrant_host,
        port=settings.qdrant_port,
        collection_name=settings.qdrant_collection,
        vector_size=settings.embedding_dimension,
    )

@lru_cache()
def get_llm_adapter():
    settings = get_settings()
    provider = settings.llm_provider.lower()
    
    logger.info(f"Inicializando LLM adapter: provider={provider}")
    
    if provider == "groq":
        if not settings.groq_api_key:
            raise ValueError("GROQ_API_KEY não configurada")
        
        return GroqAdapter(
            api_key=settings.groq_api_key,
            model=settings.groq_model,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            timeout=settings.groq_timeout,
            max_tokens=settings.groq_max_tokens,
        )
    
    elif provider == "ollama":
        return OllamaAdapter(
            host=settings.ollama_host,
            model=settings.ollama_model,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            timeout=settings.ollama_timeout,
        )
    
    else:
        groq_adapter = None
        ollama_adapter = None
        
        if settings.groq_api_key:
            try:
                groq_adapter = GroqAdapter(
                    api_key=settings.groq_api_key,
                    model=settings.groq_model,
                    temperature=settings.llm_temperature,
                    top_p=settings.llm_top_p,
                    timeout=settings.groq_timeout,
                    max_tokens=settings.groq_max_tokens,
                )
            except Exception as e:
                logger.warning(f"Falha ao inicializar Groq: {e}")
        
        ollama_adapter = OllamaAdapter(
            host=settings.ollama_host,
            model=settings.ollama_model,
            temperature=settings.llm_temperature,
            top_p=settings.llm_top_p,
            timeout=settings.ollama_timeout,
        )
        
        return HybridLLMAdapter(
            groq_adapter=groq_adapter,
            ollama_adapter=ollama_adapter,
            prefer_groq=True,
        )

@lru_cache()
def get_query_processor() -> QueryProcessor:
    logger.debug("Criando QueryProcessor")
    return QueryProcessor()

@lru_cache()
def get_domain_classifier() -> DomainClassifier:
    logger.debug("Criando DomainClassifier")
    return DomainClassifier()

@lru_cache()
def get_confidence_scorer() -> ConfidenceScorer:
    logger.debug("Criando ConfidenceScorer")
    return ConfidenceScorer()

@lru_cache()
def get_answer_generator() -> AnswerGenerator:
    logger.debug("Criando AnswerGenerator")
    return AnswerGenerator()

@lru_cache()
def get_cross_encoder_reranker() -> Optional[CrossEncoderReranker]:
    settings = get_settings()
    
    if not settings.enable_reranking:
        logger.info("Reranking desabilitado via config")
        return None
    
    try:
        logger.info("Inicializando CrossEncoderReranker (singleton)")
        return CrossEncoderReranker(
            model_name="cross-encoder/ms-marco-MiniLM-L-6-v2",
            device="cpu",
        )
    except Exception as e:
        logger.error(f"Erro ao carregar CrossEncoderReranker: {e}")
        logger.warning("Continuando sem reranking")
        return None

@lru_cache()
def get_hybrid_search_strategy() -> HybridSearchStrategy:
    logger.debug("Criando HybridSearchStrategy")
    return HybridSearchStrategy(
        vector_weight=0.7,
        text_weight=0.3,
        rrf_k=60,
    )

def get_clarifier(
    llm: HybridLLMAdapter = Depends(get_llm_adapter),
) -> Clarifier:
    settings = get_settings()
    
    logger.debug("Criando Clarifier")
    
    llm_service = llm if settings.enable_clarification else None
    
    return Clarifier(llm_service=llm_service)

def get_document_retriever(
    embeddings: SentenceTransformerAdapter = Depends(get_embeddings_adapter),
    vector_store: QdrantAdapter = Depends(get_vector_store_adapter),
    reranker: Optional[CrossEncoderReranker] = Depends(get_cross_encoder_reranker),
) -> DocumentRetriever:
    logger.debug("Criando DocumentRetriever")
    return DocumentRetriever(
        embeddings_port=embeddings,
        vector_store_port=vector_store,
        reranker=reranker,
    )

def get_memory_manager(
    embeddings: SentenceTransformerAdapter = Depends(get_embeddings_adapter),
    vector_store: QdrantAdapter = Depends(get_vector_store_adapter),
) -> MemoryManager:
    settings = get_settings()
    
    logger.debug("Criando MemoryManager")
    return MemoryManager(
        embeddings_port=embeddings,
        vector_store_port=vector_store,
        min_confidence=settings.qa_memory_min_confidence,
        min_answer_length=settings.qa_memory_min_answer_length,
    )

@lru_cache()
def get_document_processor() -> DocumentProcessor:
    settings = get_settings()
    
    logger.debug("Criando DocumentProcessor")
    return DocumentProcessor(
        chunk_size=settings.chunk_size,
        chunk_overlap=settings.chunk_overlap,
        min_chunk_size=settings.min_chunk_size,
    )

def get_generate_answer_use_case(
    query_processor: QueryProcessor = Depends(get_query_processor),
    domain_classifier: DomainClassifier = Depends(get_domain_classifier),
    document_retriever: DocumentRetriever = Depends(get_document_retriever),
    confidence_scorer: ConfidenceScorer = Depends(get_confidence_scorer),
    answer_generator: AnswerGenerator = Depends(get_answer_generator),
    memory_manager: MemoryManager = Depends(get_memory_manager),
    clarifier: Clarifier = Depends(get_clarifier),
    llm: HybridLLMAdapter = Depends(get_llm_adapter),
) -> GenerateAnswerUseCase:
    logger.debug("Criando GenerateAnswerUseCase")
    
    return GenerateAnswerUseCase(
        query_processor=query_processor,
        domain_classifier=domain_classifier,
        document_retriever=document_retriever,
        confidence_scorer=confidence_scorer,
        answer_generator=answer_generator,
        memory_manager=memory_manager,
        clarifier=clarifier,
        llm_port=llm,
    )

def get_stream_answer_use_case(
    query_processor: QueryProcessor = Depends(get_query_processor),
    domain_classifier: DomainClassifier = Depends(get_domain_classifier),
    document_retriever: DocumentRetriever = Depends(get_document_retriever),
    confidence_scorer: ConfidenceScorer = Depends(get_confidence_scorer),
    answer_generator: AnswerGenerator = Depends(get_answer_generator),
    memory_manager: MemoryManager = Depends(get_memory_manager),
    clarifier: Clarifier = Depends(get_clarifier),  # ✅ NOVO
    llm: HybridLLMAdapter = Depends(get_llm_adapter),
) -> StreamAnswerUseCase:
    logger.debug("Criando StreamAnswerUseCase")
    
    return StreamAnswerUseCase(
        query_processor=query_processor,
        domain_classifier=domain_classifier,
        document_retriever=document_retriever,
        confidence_scorer=confidence_scorer,
        answer_generator=answer_generator,
        memory_manager=memory_manager,
        clarifier=clarifier,
        llm_port=llm,
    )

def get_manage_conversation_use_case(
    vector_store: QdrantAdapter = Depends(get_vector_store_adapter),
) -> ManageConversationUseCase:
    logger.debug("Criando ManageConversationUseCase")
    
    return ManageConversationUseCase(
        conversation_repository_port=conversation_repository,
        vector_store_port=vector_store,
    )

def get_ingest_document_use_case(
    document_processor: DocumentProcessor = Depends(get_document_processor),
    embeddings: SentenceTransformerAdapter = Depends(get_embeddings_adapter),
    vector_store: QdrantAdapter = Depends(get_vector_store_adapter),
) -> IngestDocumentUseCase:
    logger.debug("Criando IngestDocumentUseCase")

    return IngestDocumentUseCase(
        document_processor=document_processor,
        embeddings_port=embeddings,
        vector_store_port=vector_store,
    )

def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(
        HTTPBearer(auto_error=False)
    ),
) -> Optional[dict]:
    if not credentials:
        return None

    try:
        return get_current_user(credentials)
    except HTTPException:
        return None

def get_conversation_repository():
    return conversation_repository


def get_user_repository():
    return user_repository


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    user_repo = Depends(get_user_repository),
) -> dict:
    from app.presentation.api.security import decode_access_token

    token = credentials.credentials

    try:
        payload = decode_access_token(token)

        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token inválido ou expirado",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user_id = int(payload["sub"])
        user = user_repo.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Usuário não encontrado",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user["is_active"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Usuário inativo",
            )

        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao validar token: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Erro ao validar autenticação",
            headers={"WWW-Authenticate": "Bearer"},
        )


def get_current_admin_user(
    current_user: dict = Depends(get_current_user),
) -> dict:
    if not current_user.get("is_admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso negado: privilégios de administrador necessários",
        )

    return current_user


def get_vector_store():
    return get_vector_store_adapter()