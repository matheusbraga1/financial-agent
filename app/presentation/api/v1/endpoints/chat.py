import logging
import json
import hashlib
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from fastapi.responses import StreamingResponse, JSONResponse

from app.presentation.models.chat_models import (
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    SessionsResponse,
    SessionInfo,
)
from app.presentation.api.responses import ApiResponse
from app.presentation.api.dependencies import (
    get_generate_answer_use_case,
    get_stream_answer_use_case,
    get_manage_conversation_use_case,
    get_current_user,
    get_optional_user,
    get_cache_service,
    get_structured_logger,
)
from app.application.use_cases.chat.generate_answer_use_case import GenerateAnswerUseCase
from app.application.use_cases.chat.stream_answer_use_case import StreamAnswerUseCase
from app.application.use_cases.chat.manage_conversation_use_case import ManageConversationUseCase
from app.infrastructure.cache import CacheService
from app.infrastructure.logging import StructuredLogger

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Enviar pergunta ao assistente",
    responses={
        200: {"description": "Resposta gerada com sucesso"},
        400: {"description": "Dados inválidos"},
        500: {"description": "Erro interno do servidor"},
    },
)
async def chat(
    request: ChatRequest,
    generate_answer_uc: GenerateAnswerUseCase = Depends(get_generate_answer_use_case),
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
    cache_service: CacheService = Depends(get_cache_service),
    structured_logger: StructuredLogger = Depends(get_structured_logger),
) -> ChatResponse:
    """
    Endpoint de chat síncrono com suporte a cache.
    
    Features:
    - Cache Redis para queries anônimas (30min TTL)
    - Histórico de conversação para usuários autenticados
    - Logging estruturado com contexto
    """
    try:
        structured_logger.info(
            "Nova requisição de chat",
            session_id=request.session_id,
            question_length=len(request.question),
            authenticated=current_user is not None
        )
        
        # Validação básica
        if len(request.question.strip()) < 3:
            structured_logger.warning(
                "Pergunta muito curta rejeitada",
                question=request.question[:50]
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pergunta muito curta. Digite pelo menos 3 caracteres.",
            )
        
        # Cache para usuários anônimos
        cache_key = None
        if not current_user:
            cache_key = f"chat:{hashlib.md5(request.question.lower().strip().encode()).hexdigest()}"
            cached_response = cache_service.get(cache_key)
            
            if cached_response:
                structured_logger.info(
                    "Resposta recuperada do cache",
                    cache_key=cache_key,
                    cache_hit=True
                )
                return ChatResponse(**cached_response)
        
        # Gerenciar sessão
        user_id = str(current_user["id"]) if current_user else None
        session_id = manage_conversation_uc.ensure_session(
            session_id=request.session_id,
            user_id=user_id,
        )
        
        # Adicionar mensagem do usuário (apenas autenticados)
        if current_user:
            manage_conversation_uc.add_user_message(session_id, request.question)
        
        # Recuperar histórico
        history = manage_conversation_uc.get_history(
            session_id=session_id,
            user_id=user_id,
            limit=200,
        )
        
        # Gerar resposta
        result = await generate_answer_uc.execute(
            question=request.question,
            history=history if current_user else None,
        )
        
        # Criar resposta
        response = ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            confidence=result["confidence"],
            model_used=result["model_used"],
            session_id=session_id,
            persisted=bool(current_user),
        )
        
        # Persistir resposta (apenas autenticados)
        if current_user:
            message_id = manage_conversation_uc.add_assistant_message(
                session_id=session_id,
                answer=result["answer"],
                sources=result["sources"],
                model_used=result["model_used"],
                confidence=result["confidence"],
            )
            response.message_id = message_id
        else:
            # Cachear resposta para queries anônimas
            try:
                cache_service.set(
                    cache_key,
                    response.dict(),
                    ttl=1800  # 30 minutos
                )
                structured_logger.info(
                    "Resposta armazenada no cache",
                    cache_key=cache_key,
                    ttl=1800
                )
            except Exception as e:
                logger.warning(f"Falha ao cachear resposta: {e}")
        
        structured_logger.info(
            "Resposta gerada com sucesso",
            sources_count=len(result['sources']),
            answer_length=len(result['answer']),
            confidence=round(result['confidence'], 2),
            cached=False
        )
        
        return response
        
    except ValueError as e:
        structured_logger.warning("Erro de validação", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        structured_logger.error(
            "Erro ao processar chat",
            error=str(e),
            exc_info=True
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar sua pergunta. Tente novamente.",
        )


@router.post(
    "/stream",
    summary="Chat com streaming (tempo real)",
    responses={
        200: {"description": "Stream de resposta"},
        400: {"description": "Dados inválidos"},
        500: {"description": "Erro interno do servidor"},
    },
)
async def chat_stream(
    request: ChatRequest,
    stream_answer_uc: StreamAnswerUseCase = Depends(get_stream_answer_use_case),
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
    cache_service: CacheService = Depends(get_cache_service),
    structured_logger: StructuredLogger = Depends(get_structured_logger),
) -> StreamingResponse:
    """
    Endpoint de chat com streaming SSE.
    
    Features:
    - Streaming em tempo real via Server-Sent Events
    - Cache opcional para queries anônimas
    - Logging estruturado
    """
    structured_logger.info(
        "Nova requisição de chat stream",
        session_id=request.session_id,
        question_length=len(request.question) if request.question else 0,
        authenticated=current_user is not None
    )
    
    async def generate():
        try:
            # Validação básica
            if not request.question or len(request.question.strip()) < 3:
                structured_logger.warning("Pergunta inválida no streaming")
                yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Pergunta muito curta ou vazia.'}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            
            # Verificar cache para usuários anônimos
            cache_key = None
            if not current_user:
                cache_key = f"chat_stream:{hashlib.md5(request.question.lower().strip().encode()).hexdigest()}"
                cached_response = cache_service.get(cache_key)
                
                if cached_response:
                    structured_logger.info(
                        "Resposta em stream recuperada do cache",
                        cache_key=cache_key
                    )
                    # Enviar resposta cacheada como stream
                    yield f"data: {json.dumps({'type': 'start'}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'token', 'data': cached_response['answer']}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'sources', 'data': cached_response['sources']}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'metadata', 'data': {'confidence': cached_response['confidence'], 'model_used': cached_response['model_used'], 'from_cache': True}}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return
            
            # Gerenciar sessão
            user_id = str(current_user["id"]) if current_user else None
            session_id = manage_conversation_uc.ensure_session(
                session_id=request.session_id,
                user_id=user_id,
            )
            
            # Adicionar mensagem do usuário
            if current_user:
                manage_conversation_uc.add_user_message(session_id, request.question)
            
            # Recuperar histórico
            history = manage_conversation_uc.get_history(
                session_id=session_id,
                user_id=user_id,
                limit=200,
            )
            
            # Sinalizar início do stream
            yield f"data: {json.dumps({'type': 'start'}, ensure_ascii=False)}\n\n"
            
            # Coletar resposta completa para cache
            full_answer = ""
            sources = []
            confidence = 0.0
            model_used = ""
            
            # Stream da resposta
            async for chunk in stream_answer_uc.execute(
                question=request.question,
                history=history if current_user else None,
            ):
                chunk_type = chunk.get("type")
                
                if chunk_type == "token":
                    token = chunk.get("data", "")
                    full_answer += token
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                elif chunk_type == "sources":
                    sources = chunk.get("data", [])
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                elif chunk_type == "metadata":
                    metadata = chunk.get("data", {})
                    confidence = metadata.get("confidence", 0.0)
                    model_used = metadata.get("model_used", "unknown")
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                elif chunk_type == "error":
                    structured_logger.error(
                        "Erro durante streaming",
                        error=chunk.get("data", {}).get("message")
                    )
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                
                elif chunk_type == "done":
                    yield f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
            
            # Persistir mensagem do assistente (apenas autenticados)
            if current_user and full_answer:
                try:
                    manage_conversation_uc.add_assistant_message(
                        session_id=session_id,
                        answer=full_answer,
                        sources=sources,
                        model_used=model_used,
                        confidence=confidence,
                    )
                except Exception as e:
                    logger.warning(f"Falha ao persistir mensagem: {e}")
            
            # Cachear resposta para queries anônimas
            elif not current_user and cache_key and full_answer:
                try:
                    cache_data = {
                        "answer": full_answer,
                        "sources": sources,
                        "confidence": confidence,
                        "model_used": model_used,
                        "session_id": session_id,
                    }
                    cache_service.set(cache_key, cache_data, ttl=1800)
                    structured_logger.info(
                        "Resposta em stream armazenada no cache",
                        cache_key=cache_key
                    )
                except Exception as e:
                    logger.warning(f"Falha ao cachear stream: {e}")
            
            structured_logger.info(
                "Stream concluído com sucesso",
                answer_length=len(full_answer),
                sources_count=len(sources),
                confidence=round(confidence, 2)
            )
            
        except Exception as e:
            structured_logger.error(
                "Erro durante streaming",
                error=str(e),
                exc_info=True
            )
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Erro ao processar sua pergunta.'}}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post(
    "/feedback",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[Dict[str, str]],
    summary="Enviar feedback sobre resposta",
)
async def submit_feedback(
    session_id: str,
    message_id: int,
    rating: str,
    comment: Optional[str] = None,
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Optional[Dict[str, Any]] = Depends(get_optional_user),
    structured_logger: StructuredLogger = Depends(get_structured_logger),
) -> ApiResponse[Dict[str, str]]:
    """Submete feedback sobre uma resposta do assistente."""
    try:
        structured_logger.info(
            "Feedback recebido",
            session_id=session_id,
            message_id=message_id,
            rating=rating,
            authenticated=current_user is not None
        )
        
        manage_conversation_uc.add_feedback(
            session_id=session_id,
            message_id=message_id,
            rating=rating,
            comment=comment,
        )
        
        return ApiResponse(
            success=True,
            data={"message": "Feedback registrado com sucesso"},
            message="Obrigado pelo feedback!"
        )
        
    except Exception as e:
        structured_logger.error("Erro ao registrar feedback", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao registrar feedback",
        )


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Obter histórico de conversação",
)
async def get_history(
    session_id: str = Query(..., description="ID da sessão"),
    limit: int = Query(50, ge=1, le=200, description="Limite de mensagens"),
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Dict[str, Any] = Depends(get_current_user),
    structured_logger: StructuredLogger = Depends(get_structured_logger),
) -> ChatHistoryResponse:
    """Retorna histórico de conversação de uma sessão."""
    try:
        structured_logger.info(
            "Recuperando histórico",
            session_id=session_id,
            user_id=current_user["id"],
            limit=limit
        )
        
        history = manage_conversation_uc.get_history(
            session_id=session_id,
            user_id=str(current_user["id"]),
            limit=limit,
        )
        
        return ChatHistoryResponse(
            session_id=session_id,
            messages=history,
        )
        
    except Exception as e:
        structured_logger.error("Erro ao recuperar histórico", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao recuperar histórico",
        )


@router.get(
    "/sessions",
    response_model=SessionsResponse,
    summary="Listar sessões do usuário",
)
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Dict[str, Any] = Depends(get_current_user),
    structured_logger: StructuredLogger = Depends(get_structured_logger),
) -> SessionsResponse:
    """Lista todas as sessões do usuário autenticado."""
    try:
        structured_logger.info(
            "Listando sessões",
            user_id=current_user["id"],
            limit=limit,
            offset=offset
        )
        
        sessions = manage_conversation_uc.list_sessions(
            user_id=str(current_user["id"]),
            limit=limit,
            offset=offset,
        )
        
        session_infos = [
            SessionInfo(
                session_id=s["session_id"],
                created_at=s["created_at"],
                message_count=s.get("message_count", 0),
            )
            for s in sessions
        ]
        
        return SessionsResponse(sessions=session_infos)
        
    except Exception as e:
        structured_logger.error("Erro ao listar sessões", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar sessões",
        )


@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_200_OK,
    response_model=ApiResponse[Dict[str, str]],
    summary="Deletar sessão",
)
async def delete_session(
    session_id: str,
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Dict[str, Any] = Depends(get_current_user),
    structured_logger: StructuredLogger = Depends(get_structured_logger),
) -> ApiResponse[Dict[str, str]]:
    """Deleta uma sessão e todo seu histórico."""
    try:
        structured_logger.info(
            "Deletando sessão",
            session_id=session_id,
            user_id=current_user["id"]
        )
        
        manage_conversation_uc.delete_session(
            session_id=session_id,
            user_id=str(current_user["id"]),
        )
        
        return ApiResponse(
            success=True,
            data={"message": "Sessão deletada com sucesso"},
            message="Sessão e histórico removidos"
        )
        
    except Exception as e:
        structured_logger.error("Erro ao deletar sessão", error=str(e))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar sessão",
        )


@router.get(
    "/models",
    summary="Obter configuração de modelos",
)
async def get_models_config(
    structured_logger: StructuredLogger = Depends(get_structured_logger),
) -> Dict[str, Any]:
    """Retorna configuração dos modelos disponíveis."""
    from app.infrastructure.config.settings import get_settings
    
    settings = get_settings()
    
    structured_logger.info("Consultando configuração de modelos")
    
    return {
        "llm": {
            "provider": settings.llm_provider,
            "model": settings.groq_model if settings.llm_provider == "groq" else settings.ollama_model,
            "temperature": settings.llm_temperature,
        },
        "embeddings": {
            "model": settings.embedding_model,
            "dimension": settings.embedding_dimension,
        },
        "rag": {
            "top_k": settings.top_k_results,
            "min_similarity": settings.min_similarity_score,
            "reranking_enabled": settings.enable_reranking,
        }
    }