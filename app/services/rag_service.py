"""RAG Service - Consolidated Multi-Domain Version

Serviço principal que coordena todo o pipeline RAG:
- Classificação automática de domínio (TI, RH, Financeiro, etc.)
- Expansão de query com sinônimos específicos por departamento
- Recuperação de documentos com filtros de domínio
- Scoring de confiança multi-fatorial
- Geração de respostas com exemplos (few-shot prompting)
"""

import logging
import asyncio
import threading
import os
import hashlib
from typing import List, Dict, Any, Optional, AsyncIterator, Tuple

from app.core.config import get_settings
from app.models.chat import ChatResponse, SourceDocument
from app.models.document import DocumentCreate
from app.domain.ports import (
    EmbeddingsPort,
    VectorStorePort,
    QueryExpanderPort,
    RetrieverPort,
    AnswerFormatterPort,
    LLMPort,
    ClarifierPort,
)
# Multi-domain components (Clean Architecture - organized by responsibility)
from app.domain.services.rag.classification import DomainClassifier, ConfidenceScorer
from app.domain.services.rag.query_processing import QueryExpanderMultidomain, Clarifier
from app.domain.services.rag.generation import AnswerFormatterWithExamples
from app.domain.services.rag.reranking import CrossEncoderReranker
from app.infrastructure.llm.ollama_llm import OllamaLLM
from app.utils.retry import retry_on_any_error
from app.utils.text_utils import process_answer_formats


logger = logging.getLogger(__name__)
settings = get_settings()


class RetrieverMultidomain:
    """Retriever com suporte a filtros de domínio/departamento."""

    def __init__(self, embedding_service: EmbeddingsPort, vector_store: VectorStorePort):
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        logger.info("Retriever Multi-domain inicializado")

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        min_score: float = 0.5,
        departments: Optional[List[str]] = None,
        doc_types: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        """Recupera documentos com filtros opcionais de departamento e tipo.

        Args:
            query: Pergunta do usuário
            top_k: Número máximo de documentos
            min_score: Score mínimo de similaridade
            departments: Lista de departamentos para filtrar (ex: ["TI", "RH"])
            doc_types: Lista de tipos de documentos (ex: ["manual", "policy"])

        Returns:
            Lista de documentos relevantes
        """
        try:
            query_vector = self.embedding_service.encode_text(query)

            # Se o vector_store suporta filtros de domínio, use-os
            if hasattr(self.vector_store, 'search_hybrid_filtered'):
                docs = self.vector_store.search_hybrid_filtered(
                    query_text=query,
                    query_vector=query_vector,
                    limit=top_k,
                    score_threshold=min_score,
                    departments=departments,
                    doc_types=doc_types,
                )
            else:
                # Fallback para busca sem filtros
                docs = self.vector_store.search_hybrid(
                    query_text=query,
                    query_vector=query_vector,
                    limit=top_k,
                    score_threshold=min_score,
                )

            logger.info(f"Recuperados {len(docs)} documentos para query: {query[:50]}...")
            return docs

        except Exception as e:
            logger.error(f"Erro ao recuperar documentos: {e}", exc_info=True)
            return []


class RAGService:
    """Serviço RAG com suporte multi-domínio completo."""

    def __init__(
        self,
        embedding_service: Optional[EmbeddingsPort] = None,
        vector_store: Optional[VectorStorePort] = None,
        query_expander: Optional[QueryExpanderPort] = None,
        retriever: Optional[RetrieverPort] = None,
        formatter: Optional[AnswerFormatterPort] = None,
        llm: Optional[LLMPort] = None,
        clarifier: Optional[ClarifierPort] = None,
        enable_reranking: Optional[bool] = None,
    ) -> None:
        """Inicializa o RAG Service com injeção de dependências.

        Args:
            embedding_service: Serviço de embeddings
            vector_store: Vector store (Qdrant)
            query_expander: Expansor de queries (opcional, usa multi-domain por padrão)
            retriever: Retriever customizado (opcional, usa multi-domain por padrão)
            formatter: Formatador de respostas (opcional, usa versão com exemplos por padrão)
            llm: LLM provider (opcional, usa Ollama por padrão)
            clarifier: Clarificador de perguntas ambíguas
            enable_reranking: Ativa/desativa CrossEncoder reranking (padrão: True)
        """
        # Dependency injection - now required (no fallback to singletons)
        if embedding_service is None or vector_store is None:
            raise ValueError(
                "RAGService requires embedding_service and vector_store via dependency injection. "
                "Use get_rag_service() from api/deps.py"
            )

        self.embedding_service = embedding_service
        self.vector_store = vector_store

        self.model = settings.ollama_model
        self.history_max_messages = int(os.getenv("CHAT_HISTORY_MAX_MESSAGES", "8"))

        # Componentes multi-domain
        self._expander: QueryExpanderPort = query_expander or QueryExpanderMultidomain()
        self._retriever: RetrieverPort = retriever or RetrieverMultidomain(
            self.embedding_service, self.vector_store
        )
        self._fmt: AnswerFormatterPort = formatter or AnswerFormatterWithExamples()
        self._llm: LLMPort = llm or OllamaLLM(self.model)

        # Componentes específicos de multi-domain
        self._domain_classifier = DomainClassifier()
        self._confidence_scorer = ConfidenceScorer()
        self._memory_confidence_threshold = float(os.getenv("QA_MEMORY_MIN_CONFIDENCE", "0.55"))

        # CrossEncoder reranking (improves precision by 15-25%)
        self.enable_reranking = enable_reranking if enable_reranking is not None else (
            os.getenv("ENABLE_RERANKING", "true").lower() == "true"
        )
        self._reranker = CrossEncoderReranker() if self.enable_reranking else None

        # Clarification system (asks follow-up questions for generic queries)
        self.enable_clarification = os.getenv("ENABLE_CLARIFICATION", "true").lower() == "true"
        # Passa o LLM para o Clarifier para gerar perguntas inteligentes
        self._clarifier: ClarifierPort = clarifier or Clarifier(llm_service=self._llm if self.enable_clarification else None)

        logger.info(f"RAG Service Multi-domain inicializado com modelo: {self.model}")
        logger.info(f"CrossEncoder reranking: {'Ativado' if self.enable_reranking else 'Desativado'}")
        logger.info(f"Clarification system: {'Ativado' if self.enable_clarification else 'Desativado'}")

    def _expand_query(self, question: str) -> str:
        """Expande a query com sinônimos específicos do domínio."""
        try:
            return self._expander.expand(question)
        except Exception as e:
            logger.warning(f"Erro ao expandir query: {e}")
            return question

    def _get_adaptive_params(self, question: str) -> Dict[str, Any]:
        """Obtém parâmetros adaptativos baseados na pergunta."""
        try:
            return self._expander.adaptive_params(question)
        except Exception as e:
            logger.warning(f"Erro ao obter parâmetros adaptativos: {e}")
            return {
                "top_k": settings.top_k_results,
                "min_score": settings.min_similarity_score,
                "reasoning": "padrão (fallback)"
            }

    def _build_context(self, documents: List[Dict[str, Any]]) -> str:
        """Constrói o contexto a partir dos documentos recuperados."""
        return self._fmt.build_context(documents)

    def _build_prompt(
        self,
        question: str,
        context: str,
        history: str = "",
        departments: Optional[List[str]] = None,
        confidence: float = 0.0
    ) -> str:
        """Constrói o prompt para o LLM com informações de domínio.

        Args:
            question: Pergunta do usuário
            context: Contexto dos documentos recuperados
            history: Histórico de mensagens
            departments: Departamentos detectados
            confidence: Score de confiança
        """
        # Se o formatter suporta departamentos, use-os
        if hasattr(self._fmt, 'build_prompt_with_domain'):
            return self._fmt.build_prompt_with_domain(
                question, context, history, departments, confidence
            )
        else:
            # Fallback para prompt padrão
            return self._fmt.build_prompt(question, context, history)

    def _build_history(self, rows: Optional[List[Dict[str, Any]]]) -> str:
        """Constrói string de histórico a partir das mensagens."""
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

    def _record_usage(self, documents: Optional[List[Dict[str, Any]]]) -> None:
        """Atualiza estatísticas de uso dos documentos retornados."""
        if not documents:
            return
        try:
            doc_ids = [str(doc.get("id")) for doc in documents if doc.get("id")]
            if doc_ids:
                self.vector_store.record_usage(doc_ids)
        except Exception as err:
            logger.debug(f"Não foi possível atualizar uso dos documentos: {err}")

    def _maybe_store_memory(
        self,
        question: str,
        answer: str,
        document_refs: Optional[List[Dict[str, Any]]],
        detected_departments: Optional[List[str]],
        confidence: float,
    ) -> None:
        """Armazena memória de QA no Qdrant quando a resposta é confiável."""
        if (
            not question
            or not answer
            or confidence < self._memory_confidence_threshold
            or len(answer.strip()) < 40
        ):
            return

        metadata = {
            "doc_type": "qa_memory",
            "department": (detected_departments or ["Geral"])[0],
            "departments": detected_departments or [],
            "tags": ["qa_memory"],
            "source_ids": [ref.get("id") for ref in document_refs or [] if ref.get("id")],
            "source_titles": [ref.get("title") for ref in document_refs or [] if ref.get("title")],
            "confidence": confidence,
            "origin": "chat_history",
        }

        memory_id = f"qa_memory_{hashlib.sha256(question.strip().lower().encode('utf-8')).hexdigest()[:24]}"
        document = DocumentCreate(
            title=question[:200],
            category=metadata["department"] or "QA Memory",
            content=answer,
            metadata=metadata,
        )

        try:
            vector = self.embedding_service.encode_document(document.title, document.content)
            self.vector_store.add_document(document=document, vector=vector, document_id=memory_id)
        except Exception as err:
            logger.debug(f"Falha ao armazenar memória de QA: {err}")

    def store_memory_from_sources(
        self,
        question: str,
        answer: str,
        sources: List[Dict[str, Any]],
        confidence: float,
    ) -> None:
        """Método público para armazenamento pós-processamento (streaming)."""
        departments = self._domain_classifier.classify(question)
        self._maybe_store_memory(question, answer, sources, departments, confidence)

    @retry_on_any_error(max_attempts=3)
    def _call_llm_sync(self, prompt: str) -> str:
        """Chamada síncrona ao LLM com retry automático."""
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
        """Gera resposta completa com classificação de domínio e scoring avançado.

        Args:
            question: Pergunta do usuário
            top_k: Número máximo de documentos (usa adaptativo se None)
            min_score: Score mínimo (usa adaptativo se None)
            history_rows: Histórico de mensagens

        Returns:
            ChatResponse com resposta, fontes e confiança
        """
        if not question or not question.strip():
            raise ValueError("Pergunta não pode estar vazia")

        # 1. Classificação de domínio
        detected_departments = self._domain_classifier.classify(question)

        # Calcular confiança (máxima entre os departamentos detectados)
        if detected_departments:
            domain_confidence = max(
                self._domain_classifier.get_confidence(question, dept)
                for dept in detected_departments
            )
        else:
            domain_confidence = 0.0

        logger.info(
            f"Domínios detectados: {detected_departments} "
            f"(confiança: {domain_confidence:.2f})"
        )

        # 2. Parâmetros adaptativos
        adaptive = self._get_adaptive_params(question)
        if top_k is None:
            top_k = int(adaptive.get("top_k", settings.top_k_results))
        if min_score is None:
            min_score = float(adaptive.get("min_score", settings.min_similarity_score))

        # 3. Expansão de query
        expanded_question = self._expand_query(question)
        logger.info(f"Query expandida: {expanded_question[:100]}...")

        # 4. Recuperação com filtros de domínio
        if hasattr(self._retriever, 'retrieve') and 'departments' in self._retriever.retrieve.__code__.co_varnames:
            documents = self._retriever.retrieve(
                expanded_question,
                top_k,
                min_score,
                departments=detected_departments if detected_departments else None
            )
        else:
            documents = self._retriever.retrieve(expanded_question, top_k, min_score)

        logger.info(f"📚 Documentos recuperados: {len(documents)}")
        if documents:
            for i, doc in enumerate(documents[:3]):
                logger.info(f"  Doc {i+1}: '{doc.get('title')}' (score: {doc.get('score', 0):.4f})")
        self._record_usage(documents)

        # 5. CrossEncoder reranking para melhor precisão
        if self.enable_reranking and self._reranker and len(documents) > 1:
            logger.info("🎯 Aplicando CrossEncoder reranking...")
            documents = self._reranker.rerank(
                query=expanded_question,
                documents=documents,
                original_weight=0.3,  # 30% score original
                rerank_weight=0.7     # 70% score do CrossEncoder
            )
            logger.info(
                f"✓ Reranking concluído - top doc agora: '{documents[0].get('title')}' "
                f"(score: {documents[0].get('score', 0):.4f})"
            )

        # 6. Clarificação proativa se necessário (e habilitada)
        if self.enable_clarification:
            clar_text = self._clarifier.maybe_clarify(question, documents)
            if clar_text:
                logger.info("Retornando clarificação ao invés de resposta")
                cleaned_markdown, html_answer, plain_answer = process_answer_formats(clar_text)
                return ChatResponse(
                    answer=cleaned_markdown,
                    answer_html=html_answer,
                    answer_plain=plain_answer,
                    sources=[],
                    model_used=self.model,
                    confidence=0.0,
                )

        # 7. Se não há documentos, retorna resposta padrão
        if not documents:
            logger.warning("⚠️  Nenhum documento encontrado - retornando resposta padrão")
            return self._generate_no_context_response(question)

        # 8. Calcula confiança multi-fatorial
        confidence_result = self._confidence_scorer.calculate_confidence(
            documents=documents,
            question=question,
            domain_confidence=domain_confidence
        )
        # Extrai o score numérico do resultado
        confidence = confidence_result.get('score', 0.0) if isinstance(confidence_result, dict) else confidence_result
        logger.info(f"Confiança calculada: {confidence:.2f}")

        # 9. Constrói contexto e prompt
        context = self._build_context(documents)
        history = self._build_history(history_rows) if history_rows else ""
        prompt = self._build_prompt(
            question,
            context,
            history=history,
            departments=detected_departments,
            confidence=confidence
        )

        # 10. Gera resposta via LLM
        loop = asyncio.get_running_loop()
        answer_text = await loop.run_in_executor(None, self._call_llm_sync, prompt)

        # 11. Sanitiza e formata resposta
        answer_text = self._fmt.sanitize(answer_text)
        cleaned_markdown, html_answer, plain_answer = process_answer_formats(answer_text)

        # 12. Prepara fontes para UI
        sources = []
        try:
            sources = self._fmt.make_sources(documents)
        except Exception as e:
            logger.warning(f"Erro ao criar fontes formatadas: {e}")
            # Fallback manual
            for d in documents:
                try:
                    sources.append(
                        SourceDocument(
                            id=str(d.get("id")),
                            title=d.get("title") or "",
                            category=d.get("category") or "",
                            score=max(0.0, min(1.0, float(d.get("score", 0.0)))),
                            snippet=(d.get("content") or "").strip()[:240] + (
                                "..." if d.get("content") and len(d.get("content")) > 240 else ""
                            ),
                        )
                    )
                except Exception:
                    pass

        try:
            self._maybe_store_memory(
                question,
                cleaned_markdown,
                documents,
                detected_departments,
                confidence,
            )
        except Exception as mem_err:
            logger.debug(f"Armazenamento de memória ignorado: {mem_err}")

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
        """Stream de tokens do LLM com classificação de domínio.

        Emite tuplas (tipo, dado):
          - ("sources", List[dict]) - fontes antes dos tokens
          - ("token", str) - tokens da resposta
          - ("_error", str) - em caso de erro
          - ("_done", None) - ao final

        Args:
            question: Pergunta do usuário
            history_rows: Histórico de mensagens

        Yields:
            Tuplas (tipo_evento, dados)
        """
        try:
            # 1. Classificação de domínio
            detected_departments = self._domain_classifier.classify(question)

            # Calcular confiança (máxima entre os departamentos detectados)
            if detected_departments:
                domain_confidence = max(
                    self._domain_classifier.get_confidence(question, dept)
                    for dept in detected_departments
                )
            else:
                domain_confidence = 0.0

            # 2. Parâmetros adaptativos e expansão
            adaptive = self._get_adaptive_params(question)
            expanded_q = self._expand_query(question)
            top_k = int(adaptive.get("top_k", settings.top_k_results))
            min_score = float(adaptive.get("min_score", settings.min_similarity_score))

            # 3. Recuperação com filtros
            if hasattr(self._retriever, 'retrieve') and 'departments' in self._retriever.retrieve.__code__.co_varnames:
                docs = self._retriever.retrieve(
                    expanded_q,
                    top_k,
                    min_score,
                    departments=detected_departments if detected_departments else None
                )
            else:
                docs = self._retriever.retrieve(expanded_q, top_k, min_score)

            self._record_usage(docs)

            # 4. CrossEncoder reranking para melhor precisão
            if self.enable_reranking and self._reranker and docs and len(docs) > 1:
                logger.info("🎯 Aplicando CrossEncoder reranking (streaming)...")
                docs = self._reranker.rerank(
                    query=expanded_q,
                    documents=docs,
                    original_weight=0.3,
                    rerank_weight=0.7
                )

            # 5. Prepara fontes
            src_list: List[Dict[str, Any]] = []
            for d in docs or []:
                try:
                    src = SourceDocument(
                        id=str(d.get("id")),
                        title=d.get("title") or "",
                        category=d.get("category") or "",
                        score=float(d.get("score", 0.0)),
                        snippet=(d.get("content") or "").strip()[:240] + (
                            "..." if d.get("content") and len(d.get("content")) > 240 else ""
                        ),
                    )
                    src_list.append(src.model_dump())
                except Exception:
                    pass

            # 6. Clarificação proativa se necessário (e habilitada)
            if self.enable_clarification:
                clar_text = self._clarifier.maybe_clarify(question, docs)
                if clar_text:
                    logger.info("Retornando clarificação ao invés de resposta (streaming)")
                    yield ("token", clar_text)
                    yield ("_done", None)
                    return

            # 7. Se não há docs, retorna resposta padrão
            if not docs:
                fb = self._generate_no_context_response(question)
                yield ("token", fb.answer)
                yield ("_done", None)
                return

            # 8. Calcula confiança
            confidence_result = self._confidence_scorer.calculate_confidence(
                documents=docs,
                question=question,
                domain_confidence=domain_confidence
            )
            # Extrai o score numérico do resultado
            confidence = confidence_result.get('score', 0.0) if isinstance(confidence_result, dict) else confidence_result

            # 8. Constrói prompt
            context = self._build_context(docs)
            history = self._build_history(history_rows) if history_rows else ""
            prompt = self._build_prompt(
                question,
                context,
                history=history,
                departments=detected_departments,
                confidence=confidence
            )

            # 9. Envia fontes antes dos tokens
            yield ("sources", src_list)
            yield ("confidence", confidence)

            # 10. Stream de tokens via thread
            queue: asyncio.Queue[Tuple[str, Any]] = asyncio.Queue()
            loop = asyncio.get_running_loop()

            def _producer():
                try:
                    for piece in self._llm.stream(prompt):
                        if piece:
                            asyncio.run_coroutine_threadsafe(
                                queue.put(("token", piece)), loop
                            )
                    asyncio.run_coroutine_threadsafe(queue.put(("_done", None)), loop)
                except Exception as e:
                    asyncio.run_coroutine_threadsafe(
                        queue.put(("_error", str(e))), loop
                    )

            threading.Thread(target=_producer, daemon=True).start()

            # 11. Consome tokens da queue
            while True:
                kind, data = await queue.get()
                yield (kind, data)
                if kind in ("_done", "_error"):
                    break

        except Exception as e:
            logger.error(f"Erro no streaming: {e}", exc_info=True)
            yield ("_error", "Erro ao gerar resposta. Tente novamente.")
            return


# Singleton removed - use dependency injection via get_rag_service() in api/deps.py
# RAGService now requires explicit dependency injection
