from typing import AsyncIterator, Tuple, List, Dict, Any, Optional
import asyncio
import threading
import logging

logger = logging.getLogger(__name__)

class StreamAnswerUseCase:
    def __init__(
        self,
        query_processor,
        domain_classifier,
        document_retriever, 
        confidence_scorer,
        answer_generator,
        memory_manager,
        clarifier,
        llm_port,
    ):
        self.query_processor = query_processor
        self.domain_classifier = domain_classifier
        self.document_retriever = document_retriever
        self.confidence_scorer = confidence_scorer
        self.answer_generator = answer_generator
        self.memory_manager = memory_manager
        self.clarifier = clarifier
        self.llm = llm_port
    
    async def execute(
        self,
        question: str,
        history: Optional[List[Dict[str, Any]]] = None,
        cancel_event: Optional[threading.Event] = None,
    ) -> AsyncIterator[Tuple[str, Any]]:
        if not question or not question.strip():
            yield ("_error", "Pergunta não pode estar vazia")
            yield ("_done", None)
            return
        
        sources_list: List[Dict[str, Any]] = []
        confidence: float = 0.0
        documents: List[Dict[str, Any]] = []
        full_answer_parts: List[str] = []
        
        try:
            logger.info(f"Iniciando streaming RAG para: '{question[:100]}...'")
            
            detected_departments = self.domain_classifier.classify(question)
            
            domain_confidence = 0.0
            if detected_departments:
                domain_confidence = max(
                    self.domain_classifier.get_confidence(question, dept)
                    for dept in detected_departments
                )
            
            adaptive_params = self.query_processor.get_adaptive_params(question)
            expanded_q = self.query_processor.expand(
                question, 
                detected_departments[0] if detected_departments else None
            )
            
            top_k = adaptive_params.get("top_k", 15)
            min_score = adaptive_params.get("min_score", 0.15)
            
            documents = self.document_retriever.retrieve(
                query=expanded_q,
                top_k=top_k,
                min_score=min_score,
                departments=detected_departments if detected_departments else None,
            )
            
            documents = self.document_retriever.normalize_documents(documents)
            
            if not documents:
                logger.warning("Nenhum documento relevante (streaming)")
                fallback = self._generate_no_context_response()
                yield ("sources", [])
                yield ("confidence", 0.0)
                yield ("token", fallback["answer"])
                yield ("_done", None)
                return
            
            max_score = max(d.get("score", 0.0) for d in documents)
            if max_score < 0.4:
                logger.warning(
                    f"Score máximo baixo ({max_score:.2f}) - streaming"
                )
                fallback = self._generate_no_context_response()
                yield ("sources", [])
                yield ("confidence", 0.0)
                yield ("token", fallback["answer"])
                yield ("_done", None)
                return
            
            clarification_text = self.clarifier.maybe_clarify(
                question=question,
                documents=documents,
            )
            
            if clarification_text:
                logger.info("Retornando clarificação (streaming)")
                yield ("sources", [])
                yield ("confidence", 0.0)
                yield ("token", clarification_text)
                yield ("_done", None)
                return
            
            confidence_result = self.confidence_scorer.calculate(
                documents=documents,
                query=question,
                domain_confidence=domain_confidence,
            )
            confidence = confidence_result["score"]
            
            sources_list = self.answer_generator.format_sources(documents)
            
            yield ("sources", sources_list)
            yield ("confidence", confidence)
            
            context = self.answer_generator.build_context(documents)
            
            history_text = ""
            if history:
                history_text = self._build_history_text(history)
            
            prompt = self.answer_generator.build_prompt(
                question=question,
                context=context,
                history=history_text,
                domain=detected_departments[0] if detected_departments else None,
                confidence=confidence,
            )
            
            queue: asyncio.Queue[Tuple[str, Any]] = asyncio.Queue()
            loop = asyncio.get_running_loop()
            
            def _producer():
                try:
                    for token in self.llm.stream(prompt):
                        # Verifica se o stream foi cancelado
                        if cancel_event and cancel_event.is_set():
                            logger.info("Stream cancelado pelo cliente - parando geração LLM")
                            asyncio.run_coroutine_threadsafe(
                                queue.put(("_cancelled", None)),
                                loop
                            )
                            return

                        if token:
                            asyncio.run_coroutine_threadsafe(
                                queue.put(("token", token)),
                                loop
                            )
                            full_answer_parts.append(token)

                    asyncio.run_coroutine_threadsafe(
                        queue.put(("_done", None)),
                        loop
                    )

                except Exception as e:
                    if cancel_event and cancel_event.is_set():
                        logger.debug("Erro após cancelamento - ignorando")
                    else:
                        logger.error("Erro no streaming do LLM", exc_info=True)
                        asyncio.run_coroutine_threadsafe(
                            queue.put(("_error", str(e))),
                            loop
                        )
            
            producer_thread = threading.Thread(
                target=_producer,
                daemon=True,
                name="LLM-Stream-Producer"
            )
            producer_thread.start()
            logger.debug(f"Thread de streaming iniciada: {producer_thread.name}")
            
            while True:
                kind, data = await queue.get()
                yield (kind, data)

                if kind in ("_done", "_error", "_cancelled"):
                    break
            
            if full_answer_parts:
                assembled_answer = "".join(full_answer_parts)
                assembled_answer = self.answer_generator.sanitize(assembled_answer)
                
                try:
                    self.memory_manager.store_if_worthy(
                        question=question,
                        answer=assembled_answer,
                        source_documents=documents,
                        detected_departments=detected_departments,
                        confidence=confidence,
                    )
                except Exception as e:
                    logger.debug(f"Falha ao armazenar memória (streaming): {e}")
        
        except Exception as e:
            logger.error(f"Erro no streaming: {e}", exc_info=True)
            yield ("_error", "Erro ao gerar resposta. Tente novamente.")
            yield ("_done", None)
    
    def _build_history_text(
        self, 
        history: List[Dict[str, Any]], 
        max_messages: int = 8
    ) -> str:
        if not history:
            return ""
        
        parts: List[str] = []
        tail = history[-max_messages:]
        
        for row in tail:
            role = (row.get("role") or "").lower()
            
            if role == "user":
                content = (row.get("content") or "").strip()
                if content:
                    parts.append(f"Usuário: {content}")
            else:
                answer = (row.get("answer") or "").strip()
                if answer:
                    parts.append(f"Assistente: {answer}")
        
        return "\n".join(parts)
    
    def _generate_no_context_response(self) -> Dict[str, Any]:
        answer = (
            "## Informação Não Disponível\n\n"
            "Desculpe, não tenho informações sobre esse assunto específico no momento.\n\n"
            "### O que você pode fazer:\n\n"
            "1. Reformular a pergunta — tente usar palavras diferentes ou ser mais específico\n"
            "2. Consultar o GLPI — verifique se há documentação disponível no sistema\n"
            "3. Abrir um chamado — a equipe de TI poderá ajudar diretamente\n\n"
            "> **Dica**: Para questões urgentes, contate o suporte de TI diretamente."
        )
        
        return {"answer": answer}