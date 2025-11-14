from typing import List, Dict, Any, Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

class GenerateAnswerUseCase:
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
        top_k: Optional[int] = None,
        min_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not question or not question.strip():
            raise ValueError("Pergunta não pode estar vazia")
        
        logger.info(f"Iniciando pipeline RAG para: '{question[:100]}...'")
        
        detected_departments = self.domain_classifier.classify(question)
        
        domain_confidence = 0.0
        if detected_departments:
            domain_confidence = max(
                self.domain_classifier.get_confidence(question, dept)
                for dept in detected_departments
            )
        
        logger.info(
            f"Domínios detectados: {detected_departments} "
            f"(confiança: {domain_confidence:.2f})"
        )
        
        adaptive_params = self.query_processor.get_adaptive_params(question)
        
        if top_k is None:
            top_k = adaptive_params.get("top_k", 15)
        if min_score is None:
            min_score = adaptive_params.get("min_score", 0.15)
        
        logger.info(
            f"Parâmetros: top_k={top_k}, min_score={min_score} "
            f"({adaptive_params.get('reason')})"
        )
        
        primary_domain = detected_departments[0] if detected_departments else None
        expanded_question = self.query_processor.expand(question, primary_domain)
        
        logger.info(f"Query expandida: '{expanded_question[:100]}...'")
        
        documents = self.document_retriever.retrieve(
            query=expanded_question,
            top_k=top_k,
            min_score=min_score,
            departments=detected_departments if detected_departments else None,
        )
        
        logger.info(f"Documentos recuperados (após pipeline): {len(documents)}")
        
        documents = self.document_retriever.normalize_documents(documents)
        
        if not documents:
            logger.warning("Nenhum documento relevante encontrado")
            return self._generate_no_context_response()
        
        max_score = max(d.get("score", 0.0) for d in documents)
        if max_score < 0.4:
            logger.warning(
                f"Score máximo muito baixo ({max_score:.2f}) - "
                f"sem artigos relevantes"
            )
            return self._generate_no_context_response()
        
        clarification_text = self.clarifier.maybe_clarify(
            question=question,
            documents=documents,
        )
        
        if clarification_text:
            logger.info("Retornando clarificação ao invés de resposta")
            return {
                "answer": clarification_text,
                "sources": [],
                "confidence": 0.0,
                "model_used": "clarifier",
            }
        
        confidence_result = self.confidence_scorer.calculate(
            documents=documents,
            query=question,
            domain_confidence=domain_confidence,
        )
        
        confidence = confidence_result["score"]
        
        logger.info(
            f"Confiança: {confidence:.2f} ({confidence_result['level']}) - "
            f"{confidence_result['message']}"
        )
        
        context = self.answer_generator.build_context(documents)
        
        history_text = ""
        if history:
            history_text = self._build_history_text(history)
        
        prompt = self.answer_generator.build_prompt(
            question=question,
            context=context,
            history=history_text,
            domain=primary_domain,
            confidence=confidence,
        )
        
        loop = asyncio.get_running_loop()
        answer_text = await loop.run_in_executor(
            None,
            self.llm.generate,
            prompt,
        )
        
        answer_text = self.answer_generator.sanitize(answer_text)
        
        sources = self.answer_generator.format_sources(documents)
        
        try:
            self.memory_manager.store_if_worthy(
                question=question,
                answer=answer_text,
                source_documents=documents,
                detected_departments=detected_departments,
                confidence=confidence,
            )
        except Exception as e:
            logger.debug(f"Falha ao armazenar memória: {e}")
        
        logger.info(
            f"Pipeline concluído: {len(answer_text)} chars, "
            f"{len(sources)} fontes, confidence={confidence:.2f}"
        )
        
        return {
            "answer": answer_text,
            "sources": sources,
            "confidence": confidence,
            "model_used": getattr(self.llm, "model_name", "unknown"),
        }
    
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
        
        return {
            "answer": answer,
            "sources": [],
            "confidence": 0.0,
            "model_used": getattr(self.llm, "model_name", "unknown"),
        }