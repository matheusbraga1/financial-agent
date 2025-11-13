from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import Dict, Any
import logging
import json

from app.models.chat import (
    ChatRequest,
    ChatResponse,
    ChatHistoryResponse,
    ChatHistoryMessage,
    SourceDocument,
    SessionInfo,
    SessionsResponse,
)
from app.models.error import ErrorResponse
from app.api.deps import get_conversation_repo, get_chat_usecase, get_vector_store
from app.domain.ports import ConversationPort, VectorStorePort
from app.api.security import get_current_user, get_optional_user

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Enviar pergunta para o assistente",
    responses={
        200: {"description": "Resposta gerada com sucesso"},
        400: {"description": "Dados inválidos", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
)
async def chat(
    request: ChatRequest,
    usecase = Depends(get_chat_usecase),
    current_user = Depends(get_optional_user),
) -> ChatResponse:
    try:
        logger.info(
            f"Nova requisição de chat | session_id={request.session_id} | question_length={len(request.question)}"
        )

        if len(request.question.strip()) < 3:
            logger.warning(f"Pergunta muito curta: '{request.question}'")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pergunta muito curta. Digite pelo menos 3 caracteres.",
            )

        response = await usecase.answer(
            question=request.question,
            session_id=request.session_id,
            current_user=current_user,
        )
        logger.info(
            f"Resposta gerada | sources={len(response.sources)} | answer_length={len(response.answer)}"
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
        400: {"description": "Dados inválidos", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
    tags=["Chat"],
)
async def chat_stream(
    request: ChatRequest,
    usecase = Depends(get_chat_usecase),
    current_user = Depends(get_optional_user),
) -> StreamingResponse:
    logger.info(
        f"Nova requisição de chat stream | session_id={request.session_id} | "
        f"question_length={len(request.question) if request.question else 0}"
    )

    async def generate():
        try:
            if not request.question:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Pergunta não pode estar vazia.'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            if len(request.question.strip()) < 3:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Pergunta muito curta. Digite pelo menos 3 caracteres.'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'type': 'done'})}\n\n"
                return

            async for chunk in usecase.stream_sse(
                question=request.question,
                session_id=request.session_id,
                current_user=current_user,
            ):
                yield chunk

        except HTTPException as http_err:
            logger.warning(f"Erro HTTP no streaming: {http_err.detail}")
            yield f"data: {json.dumps({'type': 'error', 'message': http_err.detail}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except ValueError as val_err:
            logger.warning(f"Erro de validação no streaming: {val_err}")
            yield f"data: {json.dumps({'type': 'error', 'message': str(val_err)}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Erro inesperado no streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Erro ao gerar resposta. Tente novamente.'}, ensure_ascii=False)}\n\n"
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

@router.get(
    "/health",
    response_model=Dict[str, str],
    summary="Verificar saúde do serviço de chat",
)
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "chat"}

@router.get(
    "/models",
    summary="Listar modelos disponíveis",
)
async def list_models() -> Dict[str, Any]:
    from app.core.config import get_settings

    settings = get_settings()
    return {
        "llm": {
            "model": settings.ollama_model,
            "host": settings.ollama_host,
            "type": "local",
        },
        "embedding": {
            "model": settings.embedding_model,
            "dimension": settings.embedding_dimension,
            "type": "sentence-transformer",
        },
        "search": {
            "top_k": settings.top_k_results,
            "min_score": settings.min_similarity_score,
        },
    }

@router.post(
    "/feedback",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar feedback sobre resposta",
    description="Permite que usuários avaliem a qualidade das respostas",
    tags=["Chat"],
)
async def submit_feedback(
    session_id: str,
    message_id: str,
    rating: str,
    comment: str | None = None,
    conv_repo: ConversationPort = Depends(get_conversation_repo),
    vector_store: VectorStorePort = Depends(get_vector_store),
) -> Dict[str, str]:
    try:
        msg_id_int = int(message_id)
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="message_id inválido",
        )

    record = conv_repo.get_message_by_id(msg_id_int)
    if not record or record.get("session_id") != session_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Mensagem não encontrada para esta sessão",
        )

    conv_repo.add_feedback(session_id=session_id, message_id=msg_id_int, rating=rating, comment=comment)

    doc_ids: list[str] = []
    sources_json = record.get("sources_json")
    if sources_json:
        try:
            parsed = json.loads(sources_json)
            if isinstance(parsed, list):
                doc_ids = [str(src.get("id")) for src in parsed if src.get("id")]
        except Exception:
            pass

    helpful_values = {"positivo", "positive", "helpful", "bom", "boa", "upvote"}
    helpful = rating.strip().lower() in helpful_values if rating else False

    try:
        vector_store.apply_feedback(doc_ids, helpful)
    except Exception as err:
        logger.warning(f"Não foi possível aplicar feedback aos documentos: {err}")

    logger.info(
        f"Feedback recebido | session={session_id} | message={message_id} | rating={rating} | comment={comment}"
    )
    return {"status": "received", "message": "Obrigado pelo feedback!"}


@router.get(
    "/sessions",
    response_model=SessionsResponse,
    summary="Listar sessões do usuário",
    responses={
        200: {"description": "Lista de sessões"},
        401: {"description": "Não autenticado", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
    tags=["Chat"],
)
async def list_sessions(
    limit: int = 100,
    conv_service: ConversationPort = Depends(get_conversation_repo),
    current_user = Depends(get_current_user),
) -> SessionsResponse:
    from datetime import datetime as _dt
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
        logger.info(f"Listando sessões para user_id={user_id}")

        sessions_data = conv_service.get_user_sessions(
            user_id=user_id, limit=max(1, min(limit, 500))
        )

        sessions = []
        for row in sessions_data:
            try:
                created_at = _dt.fromisoformat(row["created_at"]) if row.get("created_at") else _dt.now()
            except Exception:
                created_at = _dt.now()
                
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

        logger.info(f"Retornando {len(sessions)} sessões para user_id={user_id}")
        return SessionsResponse(sessions=sessions, total=len(sessions))

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
        204: {"description": "Sessão deletada com sucesso"},
        401: {"description": "Não autenticado", "model": ErrorResponse},
        403: {"description": "Sem permissão para deletar esta sessão", "model": ErrorResponse},
        404: {"description": "Sessão não encontrada", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
    tags=["Chat"],
)
async def delete_session(
    session_id: str,
    conv_service: ConversationPort = Depends(get_conversation_repo),
    current_user = Depends(get_current_user),
):
    try:
        logger.info(f"Tentativa de deletar sessão {session_id} por user_id={current_user['id']}")

        conv = conv_service.get_conversation(session_id)
        if not conv:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sessão não encontrada",
            )

        owner_id = conv.get("user_id")
        current_id = str(current_user["id"])
        is_admin = bool(current_user.get("is_admin"))

        if owner_id:
            try:
                owner_id_cmp = int(owner_id) if owner_id else None
                current_id_cmp = int(current_user["id"]) if current_user.get("id") else None
            except (ValueError, TypeError):
                owner_id_cmp = str(owner_id)
                current_id_cmp = str(current_user["id"])

            if owner_id_cmp != current_id_cmp and not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sem permissão para deletar esta sessão",
                )
        else:
            if not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sessão sem proprietário. Apenas administradores podem deletar",
                )

        deleted = conv_service.delete_conversation(session_id)
        if not deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Sessão não encontrada",
            )

        logger.info(f"Sessão {session_id} deletada com sucesso por user_id={current_id}")
        return None  # 204 No Content

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao deletar sessão: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao deletar sessão",
        )

@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Consultar histórico de conversa",
    responses={
        200: {"description": "Histórico da sessão"},
        400: {"description": "Dados inválidos", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
    tags=["Chat"],
)
async def get_history(
    session_id: str,
    limit: int = 100,
    conv_service: ConversationPort = Depends(get_conversation_repo),
    current_user = Depends(get_current_user),
) -> ChatHistoryResponse:
    import json as _json
    from datetime import datetime as _dt

    if not session_id or len(session_id.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="session_id inválido"
        )

    try:
        conv = conv_service.get_conversation(session_id)
        owner = conv.get("user_id") if conv else None
        is_admin = bool(current_user.get("is_admin"))

        if owner:
            try:
                owner_id = int(owner) if owner else None
                current_id = int(current_user["id"]) if current_user.get("id") else None
            except (ValueError, TypeError):
                owner_id = str(owner)
                current_id = str(current_user["id"])

            if owner_id != current_id and not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sem acesso ao histórico desta sessão",
                )
        else:
            if not is_admin:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sessão sem proprietário. Apenas administradores podem consultar",
                )

        rows = conv_service.get_history(
            session_id=session_id, limit=max(1, min(limit, 500))
        )
        messages: list[ChatHistoryMessage] = []
        for r in rows:
            ts = None
            try:
                ts = _dt.fromisoformat(r.get("timestamp")) if r.get("timestamp") else None
            except Exception:
                ts = None

            role = r.get("role")
            if role == "user":
                messages.append(
                    ChatHistoryMessage(
                        role="user", content=r.get("content"), timestamp=ts, message_id=r.get("id")
                    )
                )
            else:
                sources = None
                sj = r.get("sources_json")
                if sj:
                    try:
                        parsed = _json.loads(sj)
                        if isinstance(parsed, list):
                            sources = []
                            for it in parsed:
                                try:
                                    sources.append(SourceDocument(**it))
                                except Exception:
                                    sources.append(
                                        SourceDocument(
                                            id=str(it.get("id")),
                                            title=it.get("title") or "",
                                            category=it.get("category") or "",
                                            score=float(it.get("score", 0.0)),
                                            snippet=it.get("snippet"),
                                        )
                                    )
                    except Exception:
                        sources = None

                messages.append(
                    ChatHistoryMessage(
                        role="assistant",
                        message_id=r.get("id"),
                        answer=r.get("answer"),
                        sources=sources,
                        model_used=r.get("model_used"),
                        confidence=r.get("confidence"),
                        timestamp=ts,
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
