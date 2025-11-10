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
        - Pergunta muito curta (≤ 3 palavras)
        - Termos genéricos detectados
        - Nenhum documento encontrado
        - Documentos com scores muito baixos (< 0.3)
        - Múltiplos tópicos diferentes encontrados (divergência)
        - Baixa confiança geral (< 0.4)
        """
        if not question or not question.strip():
            return False

        question_lower = question.strip().lower()
        words = question_lower.split()

        # Termos genéricos que indicam necessidade de clarificação
        generic_terms = {
            'ajuda', 'ajudar', 'help', 'suporte', 'dúvida', 'duvida',
            'preciso', 'necessito', 'quero', 'como', 'o que', 'qual',
            'informação', 'informacao', 'problema', 'erro', 'acesso',
            'configurar', 'configuração', 'configuracao', 'sistema',
            'fazer', 'usar', 'utilizar', 'funciona', 'funcionalidade'
        }

        # Critério 1: Pergunta muito curta (≤ 3 palavras)
        if len(words) <= 3:
            logger.debug(f"Pergunta muito curta: {len(words)} palavras")
            return True

        # Critério 2: Pergunta contém apenas termos genéricos
        # Remove stopwords comuns
        stopwords = {'de', 'a', 'o', 'que', 'e', 'do', 'da', 'em', 'um', 'para', 'com', 'não', 'nao'}
        content_words = [w for w in words if w not in stopwords and len(w) > 2]

        if len(content_words) <= 2:
            # Muito poucas palavras de conteúdo
            logger.debug(f"Poucas palavras de conteúdo: {content_words}")
            return True

        # Verifica se a maioria das palavras é genérica
        generic_count = sum(1 for w in content_words if w in generic_terms)
        if generic_count >= len(content_words) * 0.6:  # 60% genéricas
            logger.debug(f"Muitos termos genéricos: {generic_count}/{len(content_words)}")
            return True

        # Critério 3: Sem documentos
        if not documents or len(documents) == 0:
            logger.debug("Nenhum documento encontrado")
            return True

        # Critério 4: Scores muito baixos (< 0.3)
        try:
            max_score = max(float(d.get('score', 0.0)) for d in documents)
            avg_score = sum(float(d.get('score', 0.0)) for d in documents[:3]) / min(len(documents), 3)

            if max_score < 0.3:
                logger.debug(f"Score máximo muito baixo: {max_score:.2f}")
                return True

            if avg_score < 0.25:
                logger.debug(f"Score médio muito baixo: {avg_score:.2f}")
                return True
        except Exception as e:
            logger.warning(f"Erro ao calcular scores: {e}")
            return True

        # Critério 5: Divergência de tópicos (categorias muito diferentes)
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

        prompt = f"""Você é um assistente corporativo especializado em ajudar colaboradores.

CONTEXTO:
Pergunta do usuário: "{question}"
{doc_context}

SITUAÇÃO:
A pergunta é muito genérica ou ambígua. Para dar uma resposta útil, você precisa entender melhor o contexto.

TAREFA:
Gere 2-4 perguntas de clarificação específicas e objetivas que ajudem a refinar a busca.

DIRETRIZES:
1. Seja direto, amigável e profissional
2. Baseie as perguntas nos documentos encontrados (se houver)
3. Foque em descobrir: sistema/ferramenta específica, contexto do problema, departamento relacionado
4. Use markdown mas SEM emojis
5. NÃO invente informações - apenas pergunte o necessário
6. Mantenha as perguntas curtas e objetivas

FORMATO EXATO:
## Preciso de mais detalhes

Para te ajudar melhor, poderia me informar:

- [pergunta objetiva 1]?
- [pergunta objetiva 2]?
- [pergunta objetiva 3]?

> Com essas informações, posso buscar a resposta certa para você.

Gere APENAS o texto formatado, sem explicações adicionais.

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
                f"- Qual é o contexto ou problema exato que você está enfrentando?\n"
                f"- Há alguma mensagem de erro ou comportamento específico?\n\n"
                f"> Com mais detalhes, posso te dar uma resposta precisa."
            )
        else:
            return (
                "## Preciso de mais detalhes\n\n"
                "Para te ajudar melhor, poderia me informar:\n\n"
                "- Sobre qual sistema, ferramenta ou processo você está perguntando?\n"
                "- Qual é o contexto ou problema específico?\n"
                "- Qual departamento ou área está relacionado (TI, RH, Financeiro, Loteamento, etc.)?\n\n"
                "> Com essas informações, posso buscar a resposta certa para você."
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

