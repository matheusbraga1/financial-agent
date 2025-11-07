from __future__ import annotations

import json
import logging
import uuid
from typing import AsyncIterator, Optional, Dict, Any

from app.models.chat import ChatResponse
from app.domain.ports import RAGPort, ConversationPort


logger = logging.getLogger(__name__)


class ChatUseCase:
    """Aplicação: orquestra o fluxo de chat, desacoplado de HTTP.

    - Garante/recupera sessão e histórico
    - Invoca RAG para resposta completa ou streaming
    - Persiste histórico quando usuário autenticado
    """

    def __init__(self, rag: RAGPort, conversations: 'ConversationPort'):
        self._rag = rag
        self._conversations = conversations

    def _ensure_session(self, session_id: Optional[str], user_id: Optional[str]) -> str:
        sid = session_id or str(uuid.uuid4())
        try:
            self._conversations.ensure_session(sid, user_id=user_id)
        except Exception as e:
            logger.warning(f"Falha ao garantir sessão {sid}: {e}")
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
            # registra pergunta do usuário se autenticado
            if current_user:
                self._conversations.add_user_message(session, question)
        except Exception as e:
            logger.debug(f"Não foi possível registrar mensagem do usuário: {e}")

        history_rows = self._get_history_rows(session, authenticated=bool(current_user))

        resp = await self._rag.generate_answer(
            question=question,
            history_rows=history_rows if current_user else None,
        )

        # anexa sessão e persisted
        resp.session_id = session if current_user else None
        resp.persisted = bool(current_user)

        # persiste resposta do assistente
        if current_user:
            try:
                sources_json = json.dumps([s.model_dump() for s in resp.sources], ensure_ascii=False)
                self._conversations.add_assistant_message(
                    session_id=session,
                    answer=resp.answer,
                    sources_json=sources_json,
                    model_used=resp.model_used,
                    confidence=getattr(resp, "confidence", None),
                )
            except Exception as e:
                logger.warning(f"Falha ao persistir resposta (não bloqueante): {e}")

        return resp

    async def stream_sse(
        self,
        question: str,
        session_id: Optional[str],
        current_user: Optional[Dict[str, Any]] = None,
    ) -> AsyncIterator[str]:
        """Gera eventos SSE: token, sources, metadata, done, error.

        A montagem de tokens é feita aqui para persistência ao final.
        """
        user_id = str(current_user["id"]) if current_user else None
        session = self._ensure_session(session_id, user_id)

        # registra pergunta do usuário se autenticado
        if current_user:
            try:
                self._conversations.add_user_message(session, question)
            except Exception:
                pass

        history_rows = self._get_history_rows(session, authenticated=bool(current_user))

        full_answer_parts: list[str] = []
        src_list: list[dict] | None = None

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
                elif kind == "_error":
                    logger.error(f"Erro no streaming LLM: {data}")
                    yield f"data: {json.dumps({'type': 'error', 'message': 'Erro ao gerar resposta.'}, ensure_ascii=False)}\n\n"
                    return
                elif kind == "_done":
                    break

            # persistência ao final, se autenticado
            if current_user and session:
                try:
                    assembled = "".join(full_answer_parts)
                    sources_json = json.dumps(src_list or [], ensure_ascii=False)
                    self._conversations.add_assistant_message(
                        session_id=session,
                        answer=assembled,
                        sources_json=sources_json,
                        model_used=self._rag.model,
                        confidence=0.0,
                    )
                except Exception as _e:
                    logger.warning(f"Falha ao persistir histórico (stream): {_e}")

            meta = {
                'type': 'metadata',
                'model_used': self._rag.model,
                'timestamp': __import__('datetime').datetime.now().isoformat(),
                'confidence': 0.0,
            }
            if current_user and session:
                meta['session_id'] = session
            yield f"data: {json.dumps(meta, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
        except Exception as e:
            logger.error(f"Erro no streaming: {e}", exc_info=True)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Erro ao gerar resposta. Tente novamente.'}, ensure_ascii=False)}\n\n"

