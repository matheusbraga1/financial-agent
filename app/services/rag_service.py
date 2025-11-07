import logging
import asyncio
import threading
import os
from typing import List, Dict, Any, Optional, AsyncIterator, Tuple

from app.core.config import get_settings
from app.models.chat import ChatResponse, SourceDocument
from app.domain.ports import (
    EmbeddingsPort,
    VectorStorePort,
    QueryExpanderPort,
    RetrieverPort,
    AnswerFormatterPort,
    LLMPort,
    ClarifierPort,
)
from app.domain.rag.query_expander import QueryExpander
from app.domain.rag.retriever import Retriever
from app.domain.rag.answer_formatter import AnswerFormatter
from app.domain.rag.clarifier import Clarifier
from app.infrastructure.llm.ollama_llm import OllamaLLM
from app.utils.retry import retry_on_any_error
from app.utils.text_utils import process_answer_formats


logger = logging.getLogger(__name__)
settings = get_settings()


class RAGService:
    def __init__(
        self,
        embedding_service: Optional[EmbeddingsPort] = None,
        vector_store: Optional[VectorStorePort] = None,
        query_expander: Optional[QueryExpanderPort] = None,
        retriever: Optional[RetrieverPort] = None,
        formatter: Optional[AnswerFormatterPort] = None,
        llm: Optional[LLMPort] = None,
        clarifier: Optional[ClarifierPort] = None,
    ) -> None:
        # Injeção de dependências com fallback para singletons existentes
        if embedding_service is None or vector_store is None:
            from app.services.embedding_service import embedding_service as _emb
            from app.services.vector_store_service import vector_store_service as _vs
            self.embedding_service = embedding_service or _emb
            self.vector_store = vector_store or _vs
        else:
            self.embedding_service = embedding_service
            self.vector_store = vector_store

        self.model = settings.ollama_model
        self.history_max_messages = int(os.getenv("CHAT_HISTORY_MAX_MESSAGES", "8"))

        # Subcomponentes padrão
        self._expander: QueryExpanderPort = query_expander or QueryExpander()
        self._retriever: RetrieverPort = retriever or Retriever(self.embedding_service, self.vector_store)
        self._fmt: AnswerFormatterPort = formatter or AnswerFormatter()
        self._llm: LLMPort = llm or OllamaLLM(self.model)
        self._clarifier: ClarifierPort = clarifier or Clarifier()

        logger.info(f"RAG Service inicializado com modelo: {self.model}")

    def _expand_query(self, question: str) -> str:
        try:
            return self._expander.expand(question)
        except Exception:
            return question

    def _get_adaptive_params(self, question: str) -> Dict[str, Any]:
        try:
            return self._expander.adaptive_params(question)
        except Exception:
            return {"top_k": settings.top_k_results, "min_score": settings.min_similarity_score, "reasoning": "padrão"}

    def _build_context(self, documents: List[Dict[str, Any]]) -> str:
        return self._fmt.build_context(documents)

    def _build_prompt(self, question: str, context: str, history: str = "") -> str:
        return self._fmt.build_prompt(question, context, history)

    def _build_history(self, rows: Optional[List[Dict[str, Any]]]) -> str:
        if not rows:
            return ""
        parts: List[str] = []
        tail = rows[-self.history_max_messages :]
        for r in tail:
            role = (r.get("role") or "").lower()
            if role == "user":
                msg = (r.get("content") or "").strip()
                if msg:
                    parts.append(f"Usuário: {msg}")
            else:
                ans = (r.get("answer") or "").strip()
                if ans:
                    parts.append(f"Assistente: {ans}")
        return "\n".join(parts)

    @retry_on_any_error(max_attempts=3)
    def _call_llm_sync(self, prompt: str) -> str:
        """Chamada síncrona ao LLM (com retry)."""
        return self._llm.generate(prompt)

    def _generate_no_context_response(self, question: str) -> ChatResponse:
        """Resposta padrão quando não há documentos relevantes."""
        answer = (
            "## Informação Não Disponível\n\n"
            "Desculpe, não tenho informações sobre esse assunto específico no momento.\n\n"
            "### O que você pode fazer:\n\n"
            "1. Reformular a pergunta — tente usar palavras diferentes ou ser mais específico\n"
            "2. Consultar o GLPI — verifique se há documentação disponível no sistema\n"
            "3. Abrir um chamado — a equipe de TI poderá ajudar diretamente\n\n"
            "> **Dica**: Para questões urgentes, contate o suporte de TI diretamente."
        )
        cleaned_markdown, html_answer, plain_answer = process_answer_formats(answer)
        return ChatResponse(
            answer=cleaned_markdown,
            answer_html=html_answer,
            answer_plain=plain_answer,
            sources=[],
            model_used=self.model,
            confidence=0.0,
        )

    async def generate_answer(
        self,
        question: str,
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
        history_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> ChatResponse:
        if not question or not question.strip():
            raise ValueError("Pergunta não pode estar vazia")

        adaptive = self._get_adaptive_params(question)
        if top_k is None:
            top_k = int(adaptive.get("top_k", settings.top_k_results))
        if min_score is None:
            min_score = float(adaptive.get("min_score", settings.min_similarity_score))

        expanded_question = self._expand_query(question)

        documents = self._retriever.retrieve(expanded_question, top_k, min_score)

        # Clarificação proativa quando a pergunta é genérica/ambígua
        clar_text = self._clarifier.maybe_clarify(question, documents)
        if clar_text:
            cleaned_markdown, html_answer, plain_answer = process_answer_formats(clar_text)
            return ChatResponse(
                answer=cleaned_markdown,
                answer_html=html_answer,
                answer_plain=plain_answer,
                sources=[],
                model_used=self.model,
                confidence=0.0,
            )

        if not documents:
            return self._generate_no_context_response(question)

        context = self._build_context(documents)
        history = self._build_history(history_rows) if history_rows else ""
        prompt = self._build_prompt(question, context, history=history)

        # Chamada ao LLM fora do event loop
        loop = asyncio.get_running_loop()
        answer_text = await loop.run_in_executor(None, self._call_llm_sync, prompt)

        # Sanitização e formatos
        answer_text = self._fmt.sanitize(answer_text)
        cleaned_markdown, html_answer, plain_answer = process_answer_formats(answer_text)

        # Fontes para UI
        sources = []
        try:
            from app.domain.rag.answer_formatter import AnswerFormatter as _AF
            sources = _AF().make_sources(documents)
        except Exception:
            for d in documents:
                try:
                    sources.append(
                        SourceDocument(
                            id=str(d.get("id")),
                            title=d.get("title") or "",
                            category=d.get("category") or "",
                            score=max(0.0, min(1.0, float(d.get("score", 0.0)))),
                            snippet=(d.get("content") or "").strip()[:240] + ("..." if d.get("content") and len(d.get("content")) > 240 else ""),
                        )
                    )
                except Exception:
                    pass

        # Confiança simples pelo score máximo
        try:
            confidence = max(float(d.get("score", 0.0)) for d in documents)
            confidence = max(0.0, min(1.0, confidence))
        except Exception:
            confidence = 0.0

        return ChatResponse(
            answer=cleaned_markdown,
            answer_html=html_answer,
            answer_plain=plain_answer,
            sources=sources,
            model_used=self.model,
            confidence=confidence,
        )

    async def stream_answer(
        self,
        question: str,
        history_rows: Optional[List[Dict[str, Any]]] = None,
    ) -> AsyncIterator[Tuple[str, Any]]:
        """Stream de tokens do LLM com eventos estruturados.

        Emite tuplas (tipo, dado):
          - ("sources", List[dict]) uma vez, antes dos tokens
          - ("token", str) diversas vezes
          - ("_error", str) em caso de erro
          - ("_done", None) ao final
        """
        try:
            adaptive = self._get_adaptive_params(question)
            expanded_q = self._expand_query(question)
            top_k = int(adaptive.get("top_k", settings.top_k_results))
            min_score = float(adaptive.get("min_score", settings.min_similarity_score))
            docs = self._retriever.retrieve(expanded_q, top_k, min_score)

            # Fontes para UI
            src_list: List[Dict[str, Any]] = []
            for d in docs or []:
                try:
                    src = SourceDocument(
                        id=str(d.get("id")),
                        title=d.get("title") or "",
                        category=d.get("category") or "",
                        score=float(d.get("score", 0.0)),
                        snippet=(d.get("content") or "").strip()[:240] + ("..." if d.get("content") and len(d.get("content")) > 240 else ""),
                    )
                    src_list.append(src.model_dump())
                except Exception:
                    pass

            if not docs:
                fb = self._generate_no_context_response(question)
                yield ("token", fb.answer)
                yield ("_done", None)
                return

            context = self._build_context(docs)
            history = self._build_history(history_rows) if history_rows else ""
            prompt = self._build_prompt(question, context, history=history)

            # Envia fontes antes dos tokens
            yield ("sources", src_list)

            queue: asyncio.Queue[Tuple[str, Any]] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def _producer():
                try:
                    for piece in self._llm.stream(prompt):
                        if piece:
                            asyncio.run_coroutine_threadsafe(queue.put(("token", piece)), loop)
                    asyncio.run_coroutine_threadsafe(queue.put(("_done", None)), loop)
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(queue.put(("_error", str(e))), loop)

            threading.Thread(target=_producer, daemon=True).start()

            while True:
                kind, data = await queue.get()
                yield (kind, data)
                if kind in ("_done", "_error"):
                    break

        except Exception as e:
            logger.error(f"Erro no streaming: {e}", exc_info=True)
            yield ("_error", "Erro ao gerar resposta. Tente novamente.")
            return


rag_service = RAGService()

