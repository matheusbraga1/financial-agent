from typing import Optional, List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class Clarifier:
    def __init__(self, llm_service=None):
        self.llm = llm_service
        
        self.generic_patterns = [
            r"^(\w+\s?){1,2}\?*$",
            
            r"^como (fazer|usar|configurar|instalar)\s+\w+\?*$",
            
            r"^o que (é|são)\s+\w+\?*$",
            
            r"^qual\s+(é|o|a)\s+\w+\?*$",
            
            r"^(isso|este|esse|aquilo)\s+",
        ]
    
    def maybe_clarify(
        self,
        question: str,
        documents: Optional[List[Dict[str, Any]]] = None,
    ) -> Optional[str]:
        if not question or len(question.strip()) < 5:
            return None
        
        question_lower = question.lower().strip()
        
        is_generic = self._is_generic_question(question_lower)
        
        if not is_generic:
            return None
        
        if documents:
            diversity_score = self._calculate_document_diversity(documents)
            
            if diversity_score < 0.6:
                logger.debug(
                    f"Documentos coesos (diversity={diversity_score:.2f}), "
                    f"não clarifica"
                )
                return None
        
        clarification = self._generate_clarification(question, documents)
        
        logger.info(f"Clarificação gerada para: '{question[:50]}...'")
        
        return clarification
    
    def _is_generic_question(self, question: str) -> bool:
        import re
        
        for pattern in self.generic_patterns:
            if re.search(pattern, question, re.IGNORECASE):
                logger.debug(f"Pergunta genérica detectada: pattern={pattern}")
                return True
        
        words = question.split()
        if len(words) <= 3:
            logger.debug(f"Pergunta muito curta: {len(words)} palavras")
            return True
        
        generic_keywords = {
            "ajuda", "help", "problema", "erro", "bug",
            "não funciona", "não consigo", "como faço",
        }
        
        if any(keyword in question for keyword in generic_keywords):
            if len(words) <= 5:
                logger.debug("Keyword genérica sem contexto suficiente")
                return True
        
        return False
    
    def _calculate_document_diversity(
        self,
        documents: List[Dict[str, Any]]
    ) -> float:
        if not documents or len(documents) < 2:
            return 0.0
        
        categories = set()
        departments = set()
        
        for doc in documents:
            category = doc.get("category", "").lower()
            if category:
                categories.add(category)
            
            metadata = doc.get("metadata", {})
            dept = metadata.get("department", "").lower()
            if dept:
                departments.add(dept)
        
        category_diversity = len(categories) / len(documents)
        department_diversity = len(departments) / len(documents) if departments else 0.0
        
        scores = [doc.get("score", 0.0) for doc in documents]
        if scores:
            max_score = max(scores)
            min_score = min(scores)
            score_spread = max_score - min_score
        else:
            score_spread = 0.0
        
        diversity = (
            0.4 * category_diversity +
            0.3 * department_diversity +
            0.3 * score_spread
        )
        
        logger.debug(
            f"Document diversity: {diversity:.2f} "
            f"(categories={len(categories)}, depts={len(departments)}, "
            f"score_spread={score_spread:.2f})"
        )
        
        return diversity
    
    def _generate_clarification(
        self,
        question: str,
        documents: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if self.llm and documents:
            return self._generate_llm_clarification(question, documents)
        
        return self._generate_default_clarification(question, documents)
    
    def _generate_llm_clarification(
        self,
        question: str,
        documents: List[Dict[str, Any]],
    ) -> str:
        doc_titles = [doc.get("title", "") for doc in documents[:5]]
        doc_categories = list(set(
            doc.get("category", "") for doc in documents
            if doc.get("category")
        ))
        
        prompt = f"""A pergunta do usuário é muito genérica: "{question}"

                    Documentos encontrados sugerem múltiplos contextos:
                    Categorias: {', '.join(doc_categories)}
                    Documentos: {', '.join(doc_titles[:3])}

                    Gere UMA pergunta de esclarecimento objetiva e específica para ajudar o usuário.

                    Formato: "Para te ajudar melhor, você poderia esclarecer: [pergunta]?"

                    Sua resposta (apenas a pergunta):"""
        
        try:
            clarification = self.llm.generate(
                prompt=prompt,
                temperature=0.7,
                max_tokens=150,
            )
            
            clarification = clarification.strip()
            
            if not clarification.endswith("?"):
                clarification += "?"
            
            return clarification
            
        except Exception as e:
            logger.warning(f"Erro ao gerar clarificação com LLM: {e}")
            return self._generate_default_clarification(question, documents)
    
    def _generate_default_clarification(
        self,
        question: str,
        documents: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        if documents:
            categories = list(set(
                doc.get("category", "").strip()
                for doc in documents
                if doc.get("category")
            ))[:3]
            
            if len(categories) >= 2:
                categories_text = ", ".join(categories[:-1]) + f" ou {categories[-1]}"
                
                return (
                    f"## Esclarecimento Necessário\n\n"
                    f"Sua pergunta é muito genérica. Encontrei informações sobre: "
                    f"**{categories_text}**.\n\n"
                    f"**Poderia especificar melhor sua dúvida?** Por exemplo:\n"
                    f"- Qual área te interessa?\n"
                    f"- Você busca informações técnicas ou administrativas?\n"
                    f"- Há um contexto específico para sua pergunta?"
                )
        
        return (
            f"## Esclarecimento Necessário\n\n"
            f"Sua pergunta é muito genérica. Para te ajudar melhor, poderia fornecer mais detalhes?\n\n"
            f"**Sugestões:**\n"
            f"- Especifique o contexto (sistema, processo, área)\n"
            f"- Inclua detalhes sobre o que você precisa\n"
            f"- Mencione se há alguma situação específica"
        )