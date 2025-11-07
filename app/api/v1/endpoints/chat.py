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
)
from app.models.error import ErrorResponse
from app.api.deps import get_conversation_repo, get_chat_usecase
from app.domain.ports import ConversationPort
from app.api.security import get_current_user, get_optional_user


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Enviar pergunta para o assistente",
    description="Recebe uma pergunta e retorna resposta baseada na base de conhecimento",
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
    description="Retorna a resposta em tempo real (Server-Sent Events)",
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
    async def generate():
        try:
            if not request.question or len(request.question.strip()) < 3:
                yield f"data: {json.dumps({'type': 'error', 'message': 'Pergunta muito curta.'}, ensure_ascii=False)}\n\n"
                return
            async for chunk in usecase.stream_sse(
                question=request.question,
                session_id=request.session_id,
                current_user=current_user,
            ):
                yield chunk
        except Exception as e:
            logger.error(f"Erro no streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Erro ao gerar resposta. Tente novamente.'}, ensure_ascii=False)}\n\n"

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
    description="Health check do serviço de chat",
)
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "chat"}


@router.get(
    "/models",
    summary="Listar modelos disponíveis",
    description="Retorna informações sobre os modelos LLM e embedding disponíveis",
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
) -> Dict[str, str]:
    logger.info(
        f"Feedback recebido | session={session_id} | message={message_id} | rating={rating} | comment={comment}"
    )
    return {"status": "received", "message": "Obrigado pelo feedback!"}


@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Consultar histórico de conversa",
    description="Retorna as mensagens de uma sessão de chat (user/assistant) em ordem cronológica",
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
            # Comparação segura de IDs (converte para int se possível)
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
                        role="user", content=r.get("content"), timestamp=ts
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

