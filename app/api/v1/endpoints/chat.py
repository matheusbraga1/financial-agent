from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import Dict, AsyncIterator, Any
import logging
import json
import asyncio

from app.models.chat import ChatRequest, ChatResponse
from app.services.rag_service import RAGService
from app.api.deps import get_rag_service

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post(
    "/chat",
    response_model=ChatResponse,
    status_code=status.HTTP_200_OK,
    summary="Enviar pergunta para o assistente",
    description="Recebe uma pergunta e retorna resposta baseada na base de conhecimento",
    responses={
        200: {
            "description": "Resposta gerada com sucesso",
            "content": {
                "application/json": {
                    "example": {
                        "answer": "Para resetar sua senha...",
                        "sources": [
                            {
                                "id": "123",
                                "title": "Como Resetar Senha",
                                "category": "Email",
                                "score": 0.89
                            }
                        ],
                        "model_used": "llama3.1:8b",
                        "timestamp": "2025-10-30T10:30:00"
                    }
                }
            }
        },
        400: {"description": "Dados inválidos"},
        500: {"description": "Erro interno do servidor"}
    }
)
async def chat(
        request: ChatRequest,
        rag_service: RAGService = Depends(get_rag_service)
) -> ChatResponse:
    try:
        logger.info(
            f"Nova requisição de chat | "
            f"session_id={request.session_id} | "
            f"question_length={len(request.question)}"
        )

        # Validação adicional
        if len(request.question.strip()) < 3:
            logger.warning(f"Pergunta muito curta: '{request.question}'")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pergunta muito curta. Digite pelo menos 3 caracteres."
            )

        # Gerar resposta
        response = rag_service.generate_answer(request.question)

        logger.info(
            f"Resposta gerada | "
            f"sources={len(response.sources)} | "
            f"answer_length={len(response.answer)}"
        )

        return response

    except ValueError as e:
        logger.warning(f"Erro de validação: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )

    except HTTPException:
        raise

    except Exception as e:
        logger.error(f"Erro ao processar chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar sua pergunta. Tente novamente."
        )


@router.post(
    "/chat/stream",
    summary="Chat com streaming (tempo real)",
    description="""
    Retorna a resposta em tempo real (Server-Sent Events).

    Útil para criar interfaces que mostram a resposta sendo
    "digitada" palavra por palavra, como ChatGPT.

    **Formato:** Server-Sent Events (SSE)

    **Eventos enviados:**
    - `sources`: Documentos fonte encontrados
    - `token`: Cada palavra da resposta
    - `done`: Fim da resposta
    - `error`: Se houver erro
    """,
    responses={
        200: {
            "description": "Stream de resposta",
            "content": {
                "text/event-stream": {
                    "example": """data: {"type":"sources","sources":[...]}\n\ndata: {"type":"token","content":"Para "}\n\ndata: {"type":"token","content":"resetar "}\n\ndata: {"type":"done"}\n\n"""
                }
            }
        }
    },
    tags=["Chat"]
)
async def chat_stream(
        request: ChatRequest,
        rag_service: RAGService = Depends(get_rag_service)
) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        try:
            logger.info(f"Iniciando streaming | session_id={request.session_id}")

            response = rag_service.generate_answer(request.question)

            sources_data = {
                "type": "sources",
                "sources": [
                    {
                        "id": source.id,
                        "title": source.title,
                        "category": source.category,
                        "score": source.score
                    }
                    for source in response.sources
                ]
            }
            yield f"data: {json.dumps(sources_data, ensure_ascii=False)}\n\n"

            await asyncio.sleep(0.1)

            words = response.answer.split()
            for i, word in enumerate(words):
                token_data = {
                    "type": "token",
                    "content": word + (" " if i < len(words) - 1 else "")
                }
                yield f"data: {json.dumps(token_data, ensure_ascii=False)}\n\n"

                await asyncio.sleep(0.03)

            metadata_data = {
                "type": "metadata",
                "model_used": response.model_used,
                "timestamp": response.timestamp.isoformat()
            }
            yield f"data: {json.dumps(metadata_data, ensure_ascii=False)}\n\n"

            done_data = {"type": "done"}
            yield f"data: {json.dumps(done_data)}\n\n"

            logger.info(f"Streaming concluído | session_id={request.session_id}")

        except Exception as e:
            logger.error(f"Erro no streaming: {e}", exc_info=True)
            error_data = {
                "type": "error",
                "message": "Erro ao gerar resposta. Tente novamente."
            }
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@router.get(
    "/health",
    response_model=Dict[str, str],
    summary="Verificar saúde do serviço de chat",
    description="Health check do serviço de chat"
)
async def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "chat"
    }


@router.get(
    "/models",
    summary="Listar modelos disponíveis",
    description="Retorna informações sobre os modelos LLM e embedding disponíveis"
)
async def list_models() -> Dict[str, Any]:
    from app.core.config import get_settings
    settings = get_settings()

    return {
        "llm": {
            "model": settings.ollama_model,
            "host": settings.ollama_host,
            "type": "local"
        },
        "embedding": {
            "model": settings.embedding_model,
            "dimension": settings.embedding_dimension,
            "type": "sentence-transformer"
        },
        "search": {
            "top_k": settings.top_k_results,
            "min_score": settings.min_similarity_score
        }
    }


@router.post(
    "/feedback",
    status_code=status.HTTP_201_CREATED,
    summary="Enviar feedback sobre resposta",
    description="Permite que usuários avaliem a qualidade das respostas (👍👎)",
    tags=["Chat"]
)
async def submit_feedback(
        session_id: str,
        message_id: str,
        rating: str,
        comment: str = None
) -> Dict[str, str]:
    logger.info(
        f"Feedback recebido | "
        f"session={session_id} | "
        f"message={message_id} | "
        f"rating={rating} | "
        f"comment={comment}"
    )

    return {
        "status": "received",
        "message": "Obrigado pelo feedback!"
    }