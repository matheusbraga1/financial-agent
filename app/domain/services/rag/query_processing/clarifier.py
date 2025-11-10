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
        Determina se a pergunta precisa de clarificação de forma INTELIGENTE.

        MELHORIA: Evita loops e é mais permissivo quando há documentos relevantes.

        Critérios PRIORITÁRIOS (ordem importa):
        1. Se tem documentos com score alto (≥ 0.6) → NÃO clarifica
        2. Se nenhum documento → clarifica
        3. Se documentos com scores muito baixos (< 0.4) → clarifica
        4. Se pergunta muito genérica E scores médios (0.4-0.6) → clarifica
        """
        if not question or not question.strip():
            return False

        question_lower = question.strip().lower()
        words = question_lower.split()

        # PRIORIDADE 1: Se há documentos com score alto, NÃO pede clarificação
        # Isso evita loops e permite que o usuário complemente respostas
        if documents and len(documents) > 0:
            try:
                max_score = max(float(d.get('score', 0.0)) for d in documents)
                top3_avg = sum(float(d.get('score', 0.0)) for d in documents[:3]) / min(len(documents), 3)

                logger.info(f"[Clarifier] Avaliando documentos: max_score={max_score:.4f}, top3_avg={top3_avg:.4f}")

                # Se o score máximo é bom (≥ 0.6), confiar nos documentos
                if max_score >= 0.6:
                    logger.info(f"[Clarifier] Score alto ({max_score:.2f}) - SEM clarificação")
                    return False

                # Se top 3 tem média boa (≥ 0.5), também confiar
                if top3_avg >= 0.5:
                    logger.info(f"[Clarifier] Score médio dos top3 bom ({top3_avg:.2f}) - SEM clarificação")
                    return False

                # Se scores são baixos (<0.4), verificar outros critérios
                if max_score < 0.4:
                    logger.debug(f"Score máximo baixo: {max_score:.2f} - pode precisar clarificação")
                    # Continue verificando outros critérios
                else:
                    # Score entre 0.4-0.6: verificar se pergunta é muito genérica
                    # Se não for muito genérica, aceitar
                    if len(words) >= 4:  # Pelo menos 4 palavras já dá contexto
                        logger.debug(f"Score moderado ({max_score:.2f}) e pergunta tem contexto - sem clarificação")
                        return False

            except Exception as e:
                logger.warning(f"Erro ao calcular scores: {e}")

        # PRIORIDADE 2: Sem documentos encontrados
        # NÃO pede clarificação - deixa o RAG informar que não há artigos
        if not documents or len(documents) == 0:
            logger.debug("Nenhum documento encontrado - RAG informará ausência de artigos")
            return False

        # PRIORIDADE 3: Documentos com scores MUITO baixos (<0.4)
        # NÃO pede clarificação - não há artigos relevantes na base
        try:
            max_score = max(float(d.get('score', 0.0)) for d in documents)
            if max_score < 0.4:
                logger.debug(f"Score muito baixo ({max_score:.2f}) - RAG informará ausência de artigos relevantes")
                return False
        except:
            return False

        # PRIORIDADE 3.5: Scores baixos mas não mínimos (0.4-0.55)
        # AQUI SIM pede clarificação para tentar melhorar a busca
        try:
            max_score = max(float(d.get('score', 0.0)) for d in documents)
            if max_score < 0.55:
                logger.debug(f"Score baixo ({max_score:.2f}) - pode precisar clarificação")
                # Continue verificando outros critérios
        except:
            pass

        # PRIORIDADE 4: Verificar se pergunta é MUITO genérica
        # Termos que sozinhos não significam nada
        ultra_generic = {
            'ajuda', 'help', 'suporte', 'dúvida', 'duvida', 'problema',
            'informação', 'informacao'
        }

        # Remove stopwords
        stopwords = {'de', 'a', 'o', 'que', 'e', 'do', 'da', 'em', 'um', 'para', 'com', 'não', 'nao', 'é', 'como'}
        content_words = [w for w in words if w not in stopwords and len(w) > 2]

        # Se tem apenas 1 palavra de conteúdo E é ultra-genérica
        if len(content_words) == 1 and content_words[0] in ultra_generic:
            logger.debug(f"Apenas termo ultra-genérico: {content_words[0]}")
            return True

        # Se a pergunta inteira tem ≤ 2 palavras (muito curta)
        if len(words) <= 2:
            logger.debug(f"Pergunta muito curta: {len(words)} palavras")
            return True

        # PRIORIDADE 5: Divergência EXTREMA de tópicos
        # Só considera se houver categorias COMPLETAMENTE diferentes
        if len(documents) >= 5:
            categories = [d.get('category', '').lower() for d in documents[:5]]
            unique_cats = set(cat for cat in categories if cat)
            # Apenas se TODOS os top 5 são de categorias diferentes
            if len(unique_cats) == 5:
                logger.debug(f"Divergência extrema: todas categorias diferentes: {unique_cats}")
                return True

        # Se chegou aqui, não precisa clarificação
        logger.debug("Pergunta tem contexto suficiente - sem clarificação")
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

        logger.info(f"[Clarifier] Clarificacao necessaria para: '{question}'")
        return self._generate_smart_clarification(question, documents)

