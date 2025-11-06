from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from typing import Dict, AsyncIterator, Any
import logging
import json
import asyncio
import threading
from datetime import datetime

from app.models.chat import ChatRequest, ChatResponse, ChatHistoryResponse, ChatHistoryMessage, SourceDocument
from app.services.rag_service import RAGService
from app.models.error import ErrorResponse
from app.api.deps import get_rag_service, get_conversation_service
from app.services.conversation_service import ConversationService
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
        200: {
            "description": "Resposta gerada com sucesso",
            "content": {
                "application/json": {
                    "example": {"persisted": false, "answer": "Para resetar sua senha...",
                        "sources": [
                            {
                                "id": "123",
                                "title": "Como Resetar Senha",
                                "category": "Email",
                                "score": 0.89,
                                "snippet": "Para resetar sua senha, acesse o portal..."
                            }
                        ],
                        "model_used": "llama3.1:8b",
                        "confidence": 0.82,
                        "timestamp": "2025-10-30T10:30:00"
                    }
                }
            }
        },
        400: {"description": "Dados invÃ¡lidos", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse}
    }
)
async def chat(
        request: ChatRequest,
        rag_service: RAGService = Depends(get_rag_service),
        conv_service: ConversationService = Depends(get_conversation_service),
        current_user = Depends(get_optional_user)
) -> ChatResponse:
    try:
        logger.info(
            f"Nova requisiÃ§Ã£o de chat | "
            f"session_id={request.session_id} | "
            f"question_length={len(request.question)}"
        )

        if len(request.question.strip()) < 3:
            logger.warning(f"Pergunta muito curta: '{request.question}'")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Pergunta muito curta. Digite pelo menos 3 caracteres."
            )

        # Define/garante a sessÃ£o
        import uuid as _uuid
        session_id = request.session_id or str(_uuid.uuid4())
        conv_service.ensure_session(session_id, user_id=str(current_user['id']) if current_user else None)
        conv_service.add_user_message(session_id, request.question)

        # Buscar histÃ³rico anterior Ã  pergunta atual
        try:
            history_rows = conv_service.get_history(session_id=session_id, limit=200)
        except Exception:
            history_rows = []

        response = await rag_service.generate_answer(request.question, history_rows=history_rows if current_user else None)
        persisted = bool(current_user and session_id)
        if persisted:
            response.session_id = session_id
        response.persisted = persisted

        logger.info(
            f"Resposta gerada | "
            f"sources={len(response.sources)} | "
            f"answer_length={len(response.answer)}"
        )

                # Persistir resposta do assistente apenas autenticado`n        if current_user and session_id:`n            try:`n                sources_json = json.dumps([s.model_dump() for s in response.sources], ensure_ascii=False)`n                conv_service.add_assistant_message(`n                    session_id=session_id,`n                    answer=response.answer,`n                    sources_json=sources_json,`n                    model_used=response.model_used,`n                    confidence=getattr(response, 'confidence', None),`n                )`n            except Exception as _e:`n                logger.warning(f"Falha ao persistir histórico: {_e}")`n        return response

    except ValueError as e:
        logger.warning(f"Erro de validaÃ§Ã£o: {e}")
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
    "/stream",
    summary="Chat com streaming (tempo real)",
    description="""
    Retorna a resposta em tempo real (Server-Sent Events).

    Ãštil para criar interfaces que mostram a resposta sendo
    "digitada" token a token.

    Formato: Server-Sent Events (SSE)

    Eventos enviados:
    - sources: Documentos fonte encontrados
    - token: Delta de conteÃºdo do modelo
    - ping: Heartbeat periÃ³dico para manter a conexÃ£o
    - metadata: InformaÃ§Ãµes finais (modelo, timestamp)
    - done: Fim da resposta
    - error: Se houver erro
    """,
    responses={
        200: {
            "description": "Stream de resposta",
            "content": {
                "text/event-stream": {
                    "example": """data: {\"type\":\"sources\",\"sources\":[...]}\n\n"""
                }
            }
        },
        400: {"description": "Dados invÃ¡lidos", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse}
    },
    tags=["Chat"]
)
async def chat_stream(
        request: ChatRequest,
        rag_service: RAGService = Depends(get_rag_service),
        conv_service: ConversationService = Depends(get_conversation_service),
        current_user = Depends(get_optional_user)
) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        try:
            logger.info(f"Iniciando streaming | session_id={request.session_id}")

            question = request.question
            if not question or len(question.strip()) < 3:
                yield f"data: {json.dumps({"type":"error","message":"Pergunta muito curta."}, ensure_ascii=False)}\n\n"
                return

            # SessÃ£o
            import uuid as _uuid
            session_id = request.session_id or str(_uuid.uuid4())
            conv_service.ensure_session(session_id, user_id=str(current_user['id']) if current_user else None)
            # Buscar histÃ³rico antes de salvar a pergunta atual
            try:
                history_rows = conv_service.get_history(session_id=session_id, limit=200)
            except Exception:
                history_rows = []
            conv_service.add_user_message(session_id, question)

            # RecuperaÃ§Ã£o (RAG)
            adaptive = rag_service._get_adaptive_params(question)
            expanded_q = rag_service._expand_query(question)
            q_vec = rag_service.embedding_service.encode_text(expanded_q)
            docs = rag_service.vector_store.search_hybrid(
                query_text=expanded_q,
                query_vector=q_vec,
                limit=adaptive["top_k"],
                score_threshold=adaptive["min_score"]
            )

            # Fontes (com snippet limpo)
            import re
            from html import unescape as _unescape
            def _mk_snippet(text: str):
                if not isinstance(text, str) or not text.strip():
                    return None
                t = text.strip()
                if "<" in t and ">" in t:
                    t = re.sub(r"<[^>]+>", " ", t)
                    t = _unescape(t)
                t = re.sub(r"\b(?:alt|width|height|src|href|style|class)=(?:\"[^\"]*\"|'[^']*')", " ", t, flags=re.IGNORECASE)
                t = re.sub(r"\S*send\.php\?docid=\d+\S*", " ", t, flags=re.IGNORECASE)
                t = re.sub(r"\s+", " ", t).strip()
                return (t[:240].rstrip() + "...") if len(t) > 240 else t

            src_list = []
            for d in docs:
                try:
                    score = float(d.get("score", 0.0))
                except Exception:
                    score = 0.0
                src_list.append({
                    "id": str(d.get("id")),
                    "title": d.get("title"),
                    "category": d.get("category"),
                    "score": max(0.0, min(1.0, score)),
                    "snippet": _mk_snippet(d.get("content"))
                })
            yield f"data: {json.dumps({"type":"sources","sources": src_list}, ensure_ascii=False)}\n\n"

            # Se nÃ£o houver docs: fallback sem LLM streaming
            if not docs:
                fb = rag_service._generate_no_context_response(question)
                words = fb.answer.split()
                for i, w in enumerate(words):
                    yield f"data: {json.dumps({"type":"token","content": w + (" " if i < len(words)-1 else "")}, ensure_ascii=False)}\n\n"
                meta_fb = {"type": "metadata", "model_used": fb.model_used, "timestamp": fb.timestamp.isoformat(), "confidence": 0.0}
                if current_user and session_id:
                    meta_fb["session_id"] = session_id
                    meta_fb["persisted"] = True
                else:
                    meta_fb["persisted"] = False
                yield f"data: {json.dumps(meta_fb, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({"type":"done"})}\n\n"
                return

            context = rag_service._build_context(docs)
            history_str = rag_service._build_history(history_rows) if current_user else ""
            prompt = rag_service._build_prompt(question, context, history=history_str)
            system_prompt = rag_service._get_system_prompt()

            loop = asyncio.get_event_loop()
            queue: asyncio.Queue = asyncio.Queue()
            done_event = asyncio.Event()

            def _producer():
                try:
                    import ollama as _ol
                    for chunk in _ol.chat(
                        model=rag_service.model,
                        messages=[{'role':'system','content': system_prompt}, {'role':'user','content': prompt}],
                        options={'temperature': 0.2, 'top_p': 0.9, 'seed': 42},
                        stream=True,
                    ):
                        piece = (chunk.get('message') or {}).get('content')
                        if piece:
                            asyncio.run_coroutine_threadsafe(queue.put(("token", piece)), loop)
                    asyncio.run_coroutine_threadsafe(queue.put(("_done", None)), loop)
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(queue.put(("_error", str(e))), loop)

            threading.Thread(target=_producer, daemon=True).start()

            async def _heartbeat():
                try:
                    while not done_event.is_set():
                        await asyncio.sleep(15)
                        await queue.put(("ping", None))
                except asyncio.CancelledError:
                    return

            hb_task = asyncio.create_task(_heartbeat())

            full_answer_parts = []
            while True:
                kind, data = await queue.get()
                if kind == "token":
                    full_answer_parts.append(data)
                    yield f"data: {json.dumps({"type":"token","content": data}, ensure_ascii=False)}\n\n"
                elif kind == "ping":
                    yield f"data: {json.dumps({"type":"ping"})}\n\n"
                elif kind == "_error":
                    done_event.set()
                    hb_task.cancel()
                    logger.error(f"Erro no streaming LLM: {data}")
                    yield f"data: {json.dumps({"type":"error","message":"Erro ao gerar resposta."}, ensure_ascii=False)}\n\n"
                    break
                elif kind == "_done":
                    done_event.set()
                    hb_task.cancel()
                    # Persistir resposta completa na sessÃ£o
                    try:
                        assembled = "".join(full_answer_parts)
                        conv_service.add_assistant_message(
                            session_id=session_id,
                            answer=assembled,
                            sources_json=json.dumps(src_list, ensure_ascii=False),
                            model_used=rag_service.model,
                            confidence=0.0,
                        )
                    except Exception as _e:
                        logger.warning(f"Falha ao persistir histÃ³rico (stream): {_e}")

                    meta = {"type": "metadata", "model_used": rag_service.model, "timestamp": datetime.now().isoformat(), "confidence": 0.0}
                    if current_user and session_id:
                        meta["session_id"] = session_id
                    yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
                    yield f"data: {json.dumps({"type":"done"})}\n\n"
                    break
        except Exception as e:
            logger.error(f"Erro no streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({"type":"error","message":"Erro ao gerar resposta. Tente novamente."}, ensure_ascii=False)}\n\n"

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
    summary="Verificar saÃºde do serviÃ§o de chat",
    description="Health check do serviÃ§o de chat"
)
async def health_check() -> Dict[str, str]:
    return {
        "status": "healthy",
        "service": "chat"
    }

@router.get(
    "/models",
    summary="Listar modelos disponÃ­veis",
    description="Retorna informaÃ§Ãµes sobre os modelos LLM e embedding disponÃ­veis"
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
    description="Permite que usuÃ¡rios avaliem a qualidade das respostas",
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

@router.get(
    "/history",
    response_model=ChatHistoryResponse,
    summary="Consultar histÃ³rico de conversa",
    description="Retorna as mensagens de uma sessÃ£o de chat (user/assistant) em ordem cronolÃ³gica",
    responses={
        200: {"description": "HistÃ³rico da sessÃ£o"},
        400: {"description": "Dados invÃ¡lidos", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse}
    },
    tags=["Chat"]
)
async def get_history(
    session_id: str,
    limit: int = 100,
    conv_service: ConversationService = Depends(get_conversation_service),
    current_user = Depends(get_current_user)
) -> ChatHistoryResponse:
    import json as _json
    from datetime import datetime as _dt

    if not session_id or len(session_id.strip()) < 3:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="session_id invÃ¡lido")

    try:
        conv = conv_service.get_conversation(session_id)
        owner = (conv.get('user_id') if conv else None)
        is_admin = bool(current_user.get('is_admin'))
        if owner:
            if str(owner) != str(current_user['id']) and not is_admin:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Sem acesso ao histÃ³rico desta sessÃ£o")
        else:
            # sessÃµes antigas sem vÃ­nculo: somente admin
            if not is_admin:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="SessÃ£o sem proprietÃ¡rio. Apenas administradores podem consultar")
        rows = conv_service.get_history(session_id=session_id, limit=max(1, min(limit, 500)))
        messages: list[ChatHistoryMessage] = []
        for r in rows:
            ts = None
            try:
                ts = _dt.fromisoformat(r.get("timestamp")) if r.get("timestamp") else None
            except Exception:
                ts = None

            role = r.get("role")
            if role == "user":
                messages.append(ChatHistoryMessage(role="user", content=r.get("content"), timestamp=ts))
            else:
                sources = None
                sj = r.get("sources_json")
                if sj:
                    try:
                        parsed = _json.loads(sj)
                        # Normaliza lista de fontes para SourceDocument
                        if isinstance(parsed, list):
                            sources = []
                            for it in parsed:
                                try:
                                    sources.append(SourceDocument(**it))
                                except Exception:
                                    # Tenta mapear campos mÃ­nimos
                                    sources.append(SourceDocument(
                                        id=str(it.get("id")),
                                        title=it.get("title") or "",
                                        category=it.get("category") or "",
                                        score=float(it.get("score", 0.0)),
                                        snippet=it.get("snippet")
                                    ))
                    except Exception:
                        sources = None

                messages.append(ChatHistoryMessage(
                    role="assistant",
                    answer=r.get("answer"),
                    sources=sources,
                    model_used=r.get("model_used"),
                    confidence=r.get("confidence"),
                    timestamp=ts
                ))

        return ChatHistoryResponse(session_id=session_id, messages=messages)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao obter histÃ³rico: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Erro ao obter histÃ³rico")








