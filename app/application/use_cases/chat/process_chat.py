from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import AsyncIterator, Optional, Dict, Any

from app.models.chat import ChatResponse
from app.domain.ports import RAGPort, ConversationPort


logger = logging.getLogger(__name__)


class ChatUseCase:
    """Aplica��o: orquestra o fluxo de chat, desacoplado de HTTP.

    - Garante/recupera sess�o e hist�rico
    - Invoca RAG para resposta completa ou streaming
    - Persiste hist�rico quando usu�rio autenticado
    """

    def __init__(self, rag: RAGPort, conversations: 'ConversationPort'):
        self._rag = rag
        self._conversations = conversations
        self._finalize_timeout = float(os.getenv("STREAM_FINALIZE_TIMEOUT", "0.25"))

    def _ensure_session(self, session_id: Optional[str], user_id: Optional[str]) -> str:
        sid = session_id or str(uuid.uuid4())
        try:
            self._conversations.ensure_session(sid, user_id=user_id)
        except Exception as e:
            logger.warning(f"Falha ao garantir sess�o {sid}: {e}")
        return sid

    def _get_history_rows(self, session_id: str, authenticated: bool) -> list[dict]:
        if not authenticated:
            return []
        try:
            return self._conversations.get_history(session_id=session_id, limit=200)
        except Exception:
            return []

    async def answer(
        self,
        question: str,
        session_id: Optional[str],
        current_user: Optional[Dict[str, Any]] = None,
    ) -> ChatResponse:
        user_id = str(current_user["id"]) if current_user else None
        session = self._ensure_session(session_id, user_id)
        try:
            if current_user:
                self._conversations.add_user_message(session, question)
        except Exception as e:
            logger.debug(f"N�o foi poss�vel registrar mensagem do usu�rio: {e}")

        history_rows = self._get_history_rows(session, authenticated=bool(current_user))

        resp = await self._rag.generate_answer(
            question=question,
            history_rows=history_rows if current_user else None,
        )

        resp.session_id = session if current_user else None
        resp.persisted = bool(current_user)

        if current_user:
            try:
                sources_json = json.dumps([s.model_dump() for s in resp.sources], ensure_ascii=False)
                message_id = self._conversations.add_assistant_message(
                    session_id=session,
                    answer=resp.answer,
                    sources_json=sources_json,
                    model_used=resp.model_used,
                    confidence=getattr(resp, "confidence", None),
                )
                resp.message_id = message_id
            except Exception as e:
                logger.warning(f"Falha ao persistir resposta (n�o bloqueante): {e}")
        else:
            resp.message_id = None

        return resp

    async def stream_sse(
        self,
        question: str,
        session_id: Optional[str],
        current_user: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """Gera eventos SSE: token, sources, metadata, done, error."""
        user_id = str(current_user["id"]) if current_user else None
        session = self._ensure_session(session_id, user_id)

        if current_user:
            try:
                self._conversations.add_user_message(session, question)
            except Exception:
                pass

        history_rows = self._get_history_rows(session, authenticated=bool(current_user))

        full_answer_parts: list[str] = []
        src_list: list[dict] | None = None
        confidence_score: float = 0.0
        message_id: Optional[int] = None
        finalize_task: Optional[asyncio.Task] = None

        try:
            async for kind, data in self._rag.stream_answer(
                question=question, history_rows=history_rows if current_user else None
            ):
                if kind == "token":
                    full_answer_parts.append(data)
                    yield f"data: {json.dumps({'type': 'token', 'content': data}, ensure_ascii=False)}\n\n"
                elif kind == "sources":
                    src_list = data
                    yield f"data: {json.dumps({'type': 'sources', 'sources': data}, ensure_ascii=False)}\n\n"
                elif kind == "confidence":
                    confidence_score = float(data)
                    yield f"data: {json.dumps({'type': 'confidence', 'score': confidence_score}, ensure_ascii=False)}\n\n"
                elif kind == "_error":
                    logger.error(f"Erro no streaming LLM: {data}")
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Erro ao gerar resposta.'}, ensure_ascii=False)}\n\n"
                    return
                elif kind == "_done":
                    break

            assembled = "".join(full_answer_parts)

            if assembled or (src_list and len(src_list) > 0):
                finalize_task = asyncio.create_task(
                    self._finalize_stream_result(
                        question=question,
                        session=session,
                        current_user=current_user,
                        assembled_answer=assembled,
                        sources=src_list or [],
                        confidence_score=confidence_score,
                    )
                )

                def _log_finalize(task: asyncio.Task) -> None:
                    try:
                        task.result()
                    except asyncio.CancelledError:
                        logger.debug("Finaliza��o do streaming cancelada (session_id=%s)", session)
                    except Exception as err:
                        logger.warning("Falha na finaliza��o ass�ncrona do streaming: %s", err)

                finalize_task.add_done_callback(_log_finalize)

                try:
                    message_id = await asyncio.wait_for(
                        asyncio.shield(finalize_task),
                        timeout=self._finalize_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.debug(
                        "Finaliza��o do streaming continuar� em background (session_id=%s)",
                        session,
                    )
                except Exception as finalize_err:
                    logger.warning(
                        "Erro ao finalizar streaming (session_id=%s): %s", session, finalize_err
                    )

            meta = {
                'type': 'metadata',
                'model_used': self._rag.model,
                'timestamp': __import__('datetime').datetime.now().isoformat(),
                'confidence': confidence_score,
                'message_id': message_id,
            }
            if current_user and session:
                meta['session_id'] = session
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Erro no streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Erro ao gerar resposta. Tente novamente.'}, ensure_ascii=False)}\n\n"

    async def _finalize_stream_result(
        self,
        *,
        question: str,
        session: Optional[str],
        current_user: Optional[Dict[str, Any]],
        assembled_answer: str,
        sources: list[dict],
        confidence_score: float,
    ) -> Optional[int]:
        """Persiste hist�rico e mem�ria sem bloquear o loop principal."""
        loop = asyncio.get_running_loop()
        message_id: Optional[int] = None
        should_persist = bool(current_user and session and assembled_answer)

        if should_persist:
            def _persist_message() -> Optional[int]:
                try:
                    sources_json = json.dumps(sources, ensure_ascii=False)
                    return self._conversations.add_assistant_message(
                        session_id=session,
                        answer=assembled_answer,
                        sources_json=sources_json,
                        model_used=self._rag.model,
                        confidence=confidence_score,
                    )
                except Exception as err:
                    logger.warning(f"Falha ao persistir hist�rico (stream): {err}")
                    return None

            message_id = await loop.run_in_executor(None, _persist_message)

        def _store_memory() -> None:
            if not assembled_answer:
                return
            store_fn = getattr(self._rag, "store_memory_from_sources", None)
            if not callable(store_fn):
                return
            try:
                store_fn(
                    question=question,
                    answer=assembled_answer,
                    sources=sources,
                    confidence=confidence_score,
                )
            except Exception as mem_err:
                logger.debug(f"N�o foi poss�vel armazenar mem�ria ap�s streaming: {mem_err}")

        await loop.run_in_executor(None, _store_memory)

        return message_id
