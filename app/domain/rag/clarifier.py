from __future__ import annotations

from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class Clarifier:
    """Sistema inteligente de clarificação usando LLM.

    Detecta automaticamente quando uma pergunta é ambígua e gera
    perguntas de clarificação contextuais usando o LLM.
    """

    def __init__(self, llm_service=None):
        """
        Args:
            llm_service: Serviço LLM para gerar clarificações (opcional)
        """
        self.llm_service = llm_service

    def _needs_clarification(self, question: str, documents: Optional[List[Dict[str, any]]] = None) -> bool:
        """
        Determina se a pergunta precisa de clarificação.

        Critérios:
        - Pergunta muito curta (≤ 4 palavras)
        - Nenhum documento encontrado
        - Documentos com scores muito baixos (< 0.35)
        - Múltiplos tópicos diferentes encontrados (divergência)
        """
        if not question or not question.strip():
            return False

        words = question.strip().split()

        # Critério 1: Pergunta muito curta
        if len(words) <= 4:
            return True

        # Critério 2: Sem documentos
        if not documents or len(documents) == 0:
            return True

        # Critério 3: Scores muito baixos
        try:
            max_score = max(float(d.get('score', 0.0)) for d in documents)
            if max_score < 0.35:
                return True
        except Exception:
            return True

        # Critério 4: Divergência de tópicos (categorias muito diferentes)
        if len(documents) >= 3:
            categories = [d.get('category', '').lower() for d in documents[:3]]
            unique_cats = set(cat for cat in categories if cat)
            # Se há 3+ categorias diferentes nos top 3 docs, pode ser ambíguo
            if len(unique_cats) >= 3:
                logger.debug(f"Múltiplas categorias detectadas: {unique_cats}")
                return True

        return False

    def _generate_smart_clarification(self, question: str, documents: Optional[List[Dict[str, any]]] = None) -> str:
        """
        Gera clarificação inteligente usando LLM baseada no contexto.
        """
        if not self.llm_service:
            return self._generate_fallback_clarification(question, documents)

        # Monta contexto dos documentos encontrados
        doc_context = ""
        if documents and len(documents) > 0:
            doc_titles = [d.get('title', '') for d in documents[:5] if d.get('title')]
            doc_categories = list(set(d.get('category', '') for d in documents[:5] if d.get('category')))

            if doc_titles:
                doc_context = f"\nDocumentos relacionados encontrados: {', '.join(doc_titles[:3])}"
            if doc_categories:
                doc_context += f"\nCategorias: {', '.join(doc_categories)}"

        prompt = f"""Você é um assistente que ajuda a clarificar perguntas ambíguas.

PERGUNTA DO USUÁRIO: "{question}"
{doc_context}

ANÁLISE:
A pergunta do usuário é muito vaga ou genérica. Você precisa fazer 2-4 perguntas curtas e objetivas para entender melhor o que o usuário precisa.

INSTRUÇÕES:
1. Seja direto e amigável
2. Faça perguntas específicas que ajudem a refinar a busca
3. Use bullet points com emojis quando apropriado
4. Mantenha tom profissional mas acessível
5. Use markdown para formatação
6. NÃO invente informações - apenas pergunte o necessário para clarificar

FORMATO:
## Preciso de mais detalhes

Para te ajudar melhor, poderia me informar:

- [pergunta 1]
- [pergunta 2]
- [pergunta 3]

> Com essas informações, posso te dar uma resposta mais precisa! 😊

RESPOSTA:"""

        try:
            clarification = self.llm_service.generate(prompt)
            # Remove possíveis prefixos do LLM
            clarification = clarification.strip()
            if clarification.startswith("RESPOSTA:"):
                clarification = clarification[9:].strip()

            logger.info(f"Clarificação gerada pelo LLM para: '{question[:50]}...'")
            return clarification

        except Exception as e:
            logger.warning(f"Erro ao gerar clarificação com LLM: {e}. Usando fallback.")
            return self._generate_fallback_clarification(question, documents)

    def _generate_fallback_clarification(self, question: str, documents: Optional[List[Dict[str, any]]] = None) -> str:
        """
        Gera clarificação básica quando LLM não está disponível.
        """
        # Analisa documentos para dar contexto
        topics = []
        if documents and len(documents) > 0:
            categories = list(set(d.get('category', '') for d in documents[:5] if d.get('category')))
            if categories:
                topics = categories[:3]

        if topics:
            topics_str = ", ".join(topics)
            return (
                f"## Preciso de mais detalhes\n\n"
                f"Encontrei informações relacionadas a: **{topics_str}**.\n\n"
                f"Para te ajudar melhor, poderia especificar:\n\n"
                f"- Sobre qual sistema ou ferramenta específica você está perguntando?\n"
                f"- Qual é o contexto ou problema exato?\n"
                f"- Há alguma mensagem de erro ou comportamento específico?\n\n"
                f"> Com mais detalhes, posso te dar uma resposta precisa! 😊"
            )
        else:
            return (
                "## Preciso de mais detalhes\n\n"
                "Para te ajudar melhor, poderia me informar:\n\n"
                "- Sobre qual sistema, ferramenta ou processo você está perguntando?\n"
                "- Qual é o contexto ou problema específico?\n"
                "- Qual departamento ou área está relacionado (TI, RH, Financeiro, etc.)?\n\n"
                "> Com essas informações, posso buscar a resposta certa para você! 😊"
            )

    def maybe_clarify(self, question: str, documents: Optional[List[Dict[str, any]]] = None) -> Optional[str]:
        """
        Decide se precisa clarificar e gera a mensagem apropriada.

        Args:
            question: Pergunta do usuário
            documents: Documentos encontrados na busca (opcional)

        Returns:
            Mensagem de clarificação ou None se não precisa clarificar
        """
        if not self._needs_clarification(question, documents):
            return None

        logger.info(f"🤔 Clarificação necessária para: '{question}'")
        return self._generate_smart_clarification(question, documents)

