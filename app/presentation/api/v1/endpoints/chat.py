import logging
import json
from typing import Dict, Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status, Query
from fastapi.responses import StreamingResponse, JSONResponse

from app.presentation.models.chat_models import (
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    SessionsResponse,
    SessionInfo,
)
from app.presentation.api.dependencies import (
    get_generate_answer_use_case,
    get_stream_answer_use_case,
    get_manage_conversation_use_case,
    get_current_user,
    get_optional_user,
)
from app.application.use_cases.chat.generate_answer_use_case import GenerateAnswerUseCase
from app.application.use_cases.chat.stream_answer_use_case import StreamAnswerUseCase
from app.application.use_cases.chat.manage_conversation_use_case import ManageConversationUseCase

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
) -> ChatResponse:
    try:
        logger.info(
            f"Nova requisição de chat | session_id={request.session_id} | "
            f"question_length={len(request.question)} | "
            f"authenticated={current_user is not None}"
        )
        
        if len(request.question.strip()) < 3:
            logger.warning(f"Pergunta muito curta: '{request.question}'")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pergunta muito curta. Digite pelo menos 3 caracteres.",
            )
        
        user_id = str(current_user["id"]) if current_user else None
        session_id = manage_conversation_uc.ensure_session(
            session_id=request.session_id,
            user_id=user_id,
        )
        
        if current_user:
            manage_conversation_uc.add_user_message(session_id, request.question)
        
        history = manage_conversation_uc.get_history(
            session_id=session_id,
            user_id=user_id,
            limit=200,
        )
        
        result = await generate_answer_uc.execute(
            question=request.question,
            history=history if current_user else None,
        )
        
        response = ChatResponse(
            answer=result["answer"],
            sources=result["sources"],
            confidence=result["confidence"],
            model_used=result["model_used"],
            session_id=session_id,
            persisted=bool(current_user),
        )
        
        if current_user:
            message_id = manage_conversation_uc.add_assistant_message(
                session_id=session_id,
                answer=result["answer"],
                sources=result["sources"],
                model_used=result["model_used"],
                confidence=result["confidence"],
            )
            response.message_id = message_id
        
        logger.info(
            f"Resposta gerada | sources={len(result['sources'])} | "
            f"answer_length={len(result['answer'])} | "
            f"confidence={result['confidence']:.2f}"
        )
        
        return response
        
    except ValueError as e:
        logger.warning(f"Erro de validação: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao processar chat: {e}", exc_info=True)
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
) -> StreamingResponse:
    logger.info(
        f"Nova requisição de chat stream | session_id={request.session_id} | "
        f"question_length={len(request.question) if request.question else 0} | "
        f"authenticated={current_user is not None}"
    )
    
    async def generate():
        try:
            if not request.question:
                yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Pergunta não pode estar vazia.'}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            
            if len(request.question.strip()) < 3:
                yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Pergunta muito curta. Digite pelo menos 3 caracteres.'}}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return
            
            user_id = str(current_user["id"]) if current_user else None
            session_id = manage_conversation_uc.ensure_session(
                session_id=request.session_id,
                user_id=user_id,
            )
            
            if current_user:
                manage_conversation_uc.add_user_message(session_id, request.question)
            
            history = manage_conversation_uc.get_history(
                session_id=session_id,
                user_id=user_id,
                limit=200,
            )
            
            full_answer_parts = []
            sources_data = None
            confidence_value = 0.0
            message_id = None
            
            async for event_type, event_data in stream_answer_uc.execute(
                question=request.question,
                history=history if current_user else None,
            ):
                if event_type == "sources":
                    sources_data = event_data
                    yield f"data: {json.dumps({'type': 'sources', 'data': event_data}, ensure_ascii=False)}\n\n"
                
                elif event_type == "confidence":
                    confidence_value = event_data
                    yield f"data: {json.dumps({'type': 'confidence', 'data': event_data}, ensure_ascii=False)}\n\n"
                
                elif event_type == "token":
                    full_answer_parts.append(event_data)
                    yield f"data: {json.dumps({'type': 'token', 'data': event_data}, ensure_ascii=False)}\n\n"
                
                elif event_type == "_error":
                    logger.error(f"Erro no streaming: {event_data}")
                    yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Erro ao gerar resposta.'}}, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({'type': 'done'})}\n\n"
                    return
                
                elif event_type == "_done":
                    break
            
            assembled_answer = "".join(full_answer_parts)
            
            if current_user and assembled_answer:
                message_id = manage_conversation_uc.add_assistant_message(
                    session_id=session_id,
                    answer=assembled_answer,
                    sources=sources_data or [],
                    model_used="streaming",
                    confidence=confidence_value,
                )
            
            metadata = {
                'session_id': session_id,
                'message_id': message_id,
                'persisted': bool(current_user),
                'confidence': confidence_value,
                'timestamp': __import__('datetime').datetime.now().isoformat(),
            }
            
            yield f"data: {json.dumps({'type': 'metadata', 'data': metadata}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except HTTPException as http_err:
            logger.warning(f"Erro HTTP no streaming: {http_err.detail}")
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': http_err.detail}}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except ValueError as val_err:
            logger.warning(f"Erro de validação no streaming: {val_err}")
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': str(val_err)}}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Erro inesperado no streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'data': {'message': 'Erro ao gerar resposta. Tente novamente.'}}, ensure_ascii=False)}\n\n"
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
    status_code=status.HTTP_201_CREATED,
    summary="Enviar feedback sobre resposta",
    description="Permite avaliar a qualidade das respostas",
)
async def submit_feedback(
    session_id: str,
    message_id: str,
    rating: str,
    comment: Optional[str] = None,
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
) -> Dict[str, str]:
    try:
        msg_id_int = int(message_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message_id inválido",
        )
    
    success = manage_conversation_uc.add_feedback(
        session_id=session_id,
        message_id=msg_id_int,
        rating=rating,
        comment=comment,
    )
    
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mensagem não encontrada para esta sessão",
        )
    
    logger.info(
        f"Feedback recebido | session={session_id} | "
        f"message={message_id} | rating={rating}"
    )
    
    return {"status": "received", "message": "Obrigado pelo feedback!"}

@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Consultar histórico de conversa",
    responses={
        200: {"description": "Histórico da sessão"},
        400: {"description": "Dados inválidos"},
        403: {"description": "Sem permissão"},
        500: {"description": "Erro interno"},
    },
)
async def get_history(
    session_id: str,
    limit: int = Query(100, ge=1, le=500),
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> ChatHistoryResponse:
    import uuid
    from datetime import datetime as dt
    
    if not session_id or len(session_id.strip()) < 10:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id inválido"
        )
    
    try:
        uuid.UUID(session_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="session_id deve ser um UUID válido"
        )
    
    try:
        history_rows = manage_conversation_uc.get_history(
            session_id=session_id,
            user_id=str(current_user["id"]),
            limit=limit,
        )
        
        from app.presentation.models.chat_models import ChatHistoryMessage, SourceDocument
        
        messages = []
        for row in history_rows:
            role = row.get("role", "")
            
            timestamp = None
            if row.get("timestamp"):
                try:
                    timestamp = dt.fromisoformat(row["timestamp"])
                except (ValueError, TypeError):
                    pass
            
            if role == "user":
                messages.append(
                    ChatHistoryMessage(
                        role="user",
                        message_id=row.get("id"),
                        content=row.get("content"),
                        timestamp=timestamp,
                    )
                )
            else:
                sources = None
                sources_json = row.get("sources_json")
                if sources_json:
                    try:
                        parsed = json.loads(sources_json)
                        if isinstance(parsed, list):
                            sources = [SourceDocument(**src) for src in parsed]
                    except Exception:
                        pass
                
                messages.append(
                    ChatHistoryMessage(
                        role="assistant",
                        message_id=row.get("id"),
                        answer=row.get("answer"),
                        sources=sources,
                        model_used=row.get("model_used"),
                        confidence=row.get("confidence"),
                        timestamp=timestamp,
                    )
                )
        
        return ChatHistoryResponse(session_id=session_id, messages=messages)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter histórico: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter histórico",
        )

@router.get(
    "/sessions",
    response_model=SessionsResponse,
    summary="Listar sessões do usuário",
    responses={
        200: {"description": "Lista de sessões"},
        401: {"description": "Não autenticado"},
        500: {"description": "Erro interno"},
    },
)
async def list_sessions(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Dict[str, Any] = Depends(get_current_user),
) -> JSONResponse:
    from datetime import datetime as dt
    import re
    
    def sanitize_message_preview(text: str, max_length: int = 100) -> str:
        if not text:
            return "Nova conversa"
        
        text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'\*\*([^\*]+)\*\*', r'\1', text)
        text = re.sub(r'\*([^\*]+)\*', r'\1', text)
        text = re.sub(r'__([^_]+)__', r'\1', text)
        text = re.sub(r'_([^_]+)_', r'\1', text)
        text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
        text = re.sub(r'```[\s\S]*?```', '', text)
        text = re.sub(r'`([^`]+)`', r'\1', text)
        text = re.sub(r'<[^>]+>', '', text)
        text = re.sub(r'\n+', ' ', text)
        text = re.sub(r'\s+', ' ', text)
        text = text.strip()
        
        if len(text) > max_length:
            text = text[:max_length].rsplit(' ', 1)[0] + '...'
        
        return text or "Nova conversa"
    
    try:
        user_id = str(current_user["id"])
        logger.info(f"Listando sessões para user_id={user_id} (limit={limit}, offset={offset})")
        
        sessions_data = manage_conversation_uc.get_user_sessions(
            user_id=user_id,
            limit=max(1, min(limit + offset, 500)),
        )
        
        total = len(sessions_data)
        page = (offset // limit) + 1
        total_pages = (total + limit - 1) // limit if total > 0 else 1
        
        paginated_sessions = sessions_data[offset:offset + limit]
        
        sessions = []
        for row in paginated_sessions:
            try:
                created_at = dt.fromisoformat(row["created_at"]) if row.get("created_at") else dt.now()
            except (ValueError, TypeError) as e:
                logger.warning(f"Erro ao parsear timestamp: {e}")
                created_at = dt.now()
            
            raw_message = row.get("last_message", "Nova conversa")
            clean_message = sanitize_message_preview(raw_message)
            
            sessions.append(
                SessionInfo(
                    session_id=row["session_id"],
                    created_at=created_at,
                    message_count=row.get("message_count", 0),
                    last_message=clean_message,
                )
            )
        
        logger.info(f"Retornando {len(sessions)} sessões (página {page}/{total_pages})")
        
        response_data = SessionsResponse(sessions=sessions, total=total)
        
        return JSONResponse(
            content=response_data.model_dump(),
            headers={
                "X-Total-Count": str(total),
                "X-Page": str(page),
                "X-Page-Size": str(limit),
                "X-Total-Pages": str(total_pages),
            }
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao listar sessões: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao listar sessões",
        )

@router.delete(
    "/sessions/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Deletar sessão de chat",
    responses={
        204: {"description": "Sessão deletada"},
        401: {"description": "Não autenticado"},
        403: {"description": "Sem permissão"},
        404: {"description": "Sessão não encontrada"},
    },
)
async def delete_session(
    session_id: str,
    manage_conversation_uc: ManageConversationUseCase = Depends(get_manage_conversation_use_case),
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    try:
        logger.info(f"Deletando sessão {session_id} por user_id={current_user['id']}")
        
        deleted = manage_conversation_uc.delete_session(
            session_id=session_id,
            user_id=str(current_user["id"]),
        )
        
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sessão não encontrada",
            )
        
        logger.info(f"Sessão {session_id} deletada com sucesso")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao deletar sessão: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar sessão",
        )

@router.get(
    "/health",
    summary="Verificar saúde do serviço de chat",
)
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "chat"}

@router.get(
    "/models",
    summary="Listar modelos disponíveis",
)
async def list_models() -> Dict[str, Any]:
    from app.infrastructure.config.settings import get_settings
    
    settings = get_settings()
    
    return {
        "llm": {
            "provider": settings.llm_provider,
            "groq_model": settings.groq_model,
            "ollama_model": settings.ollama_model,
            "temperature": settings.llm_temperature,
        },
        "embedding": {
            "model": settings.embedding_model,
            "dimension": settings.embedding_dimension,
        },
        "rag": {
            "top_k": settings.top_k_results,
            "min_score": settings.min_similarity_score,
            "enable_reranking": settings.enable_reranking,
            "enable_clarification": settings.enable_clarification,
        },
    }