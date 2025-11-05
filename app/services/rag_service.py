import logging
from typing import List, Dict, Any
import ollama

from app.core.config import get_settings
from app.services.embedding_service import embedding_service
from app.services.vector_store_service import vector_store_service
from app.models.chat import ChatResponse, SourceDocument

logger = logging.getLogger(__name__)
settings = get_settings()


class RAGService:
    def __init__(self):
        self.embedding_service = embedding_service
        self.vector_store = vector_store_service
        self.ollama_host = settings.ollama_host
        self.model = settings.ollama_model

        logger.info(f"RAG Service inicializado com modelo: {self.model}")

    def generate_answer(
            self,
            question: str,
            top_k: int = None,
            min_score: float = None
    ) -> ChatResponse:
        logger.info(f"Processando pergunta: {question[:50]}...")

        if not question or not question.strip():
            raise ValueError("Pergunta não pode estar vazia")

        try:
            question_vector = self.embedding_service.encode_text(question)
            logger.debug("Embedding da pergunta gerado")
        except Exception as e:
            logger.error(f"Erro ao gerar embedding: {e}")
            raise

        try:
            documents = self.vector_store.search_hybrid(
                query_text=question,
                query_vector=question_vector,
                limit=top_k or settings.top_k_results,
                score_threshold=min_score or settings.min_similarity_score
            )
            logger.info(f"Encontrados {len(documents)} documentos relevantes")
        except Exception as e:
            logger.error(f"Erro na busca vetorial: {e}")
            raise

        if not documents:
            logger.warning("Nenhum documento relevante encontrado")
            return self._generate_no_context_response(question)

        context = self._build_context(documents)

        prompt = self._build_prompt(question, context)

        try:
            answer = self._call_llm(prompt)
            logger.info("Resposta gerada com sucesso")
        except Exception as e:
            logger.error(f"Erro ao chamar LLM: {e}")
            raise

        # 8. Montar resposta
        sources = []
        for doc in documents:
            # Validar que os campos existem e não são None
            if doc.get("title") and doc.get("category"):
                sources.append(
                    SourceDocument(
                        id=str(doc["id"]),
                        title=doc["title"],
                        category=doc["category"],
                        score=doc["score"]
                    )
                )
            else:
                logger.warning(f"Documento {doc['id']} com campos inválidos, ignorando")

        response = ChatResponse(
            answer=answer,
            sources=sources,
            model_used=self.model
        )

        return response

    def _build_context(self, documents: List[Dict[str, Any]]) -> str:
        context_parts = []

        for i, doc in enumerate(documents, 1):
            context_parts.append(
                f"--- ARTIGO {i}: {doc['title']} (Categoria: {doc['category']}) ---\n"
                f"{doc['content']}\n"
            )

        return "\n".join(context_parts)

    def _build_prompt(self, question: str, context: str) -> str:
        prompt = f"""Você é um assistente técnico de TI da empresa, especializado em ajudar funcionários com problemas e dúvidas técnicas.
        
        === EXEMPLO DE BOA RESPOSTA ===
        Pergunta: "Como resolver problema no sistema?"
        Artigo: "Para resolver erro após atualização: 1) Abrir local do arquivo 2) Deletar temporário"
        Resposta BOA: "Para resolver o problema, siga: 1) Abra o local do arquivo... 2) Delete o arquivo temporário..."
        
        Resposta RUIM: "Não há informação sobre seu problema específico."

        === ARTIGOS DA BASE DE CONHECIMENTO ===
        {context}
    
        === PERGUNTA DO USUÁRIO ===
        {question}
    
        === INSTRUÇÕES PARA RESPONDER ===
    
        1. ANALISE CUIDADOSAMENTE:
           - Leia todos os artigos fornecidos
           - Identifique informações relevantes que possam ajudar o usuário
           - Considere soluções relacionadas mesmo que não sejam 100% idênticas à pergunta
    
        2. QUANDO RESPONDER:
           - Se os artigos contêm procedimentos, passos ou soluções relacionadas ao problema, FORNEÇA essas informações
           - Mesmo que o artigo não mencione exatamente as mesmas palavras da pergunta, se o CONTEÚDO é relevante, use-o
           - Seja prático e útil - o objetivo é AJUDAR o usuário
    
        3. QUANDO NÃO RESPONDER:
           - SOMENTE diga que não tem informação se os artigos forem sobre assuntos completamente diferentes
           - Não seja excessivamente restritivo
    
        4. FORMATO DA RESPOSTA:
           - Seja claro, objetivo e profissional
           - Use listas numeradas para passos/procedimentos
           - Explique de forma que qualquer pessoa consiga seguir
           - Se houver imagens ou capturas de tela mencionadas, indique isso
    
        5. IDIOMA:
           - Sempre responda em português brasileiro
    
        === SUA RESPOSTA ===
        Baseando-se nos artigos acima e sendo ÚTIL (não excessivamente restritivo), responda:"""

        return prompt

    def _call_llm(self, prompt: str) -> str:
        response = ollama.chat(
            model=self.model,
            messages=[
                {
                    'role': 'system',
                    'content': '''Você é um assistente técnico prestativo da equipe de TI. 
                    Sua prioridade é AJUDAR os usuários com base nas informações disponíveis. 
                    Quando encontrar procedimentos ou soluções nos artigos, compartilhe-os de forma clara e útil.
                    Seja prático e não excessivamente restritivo - se a informação pode ajudar, forneça-a.
                    Somente diga que não tem informação se o assunto for completamente diferente.'''
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            options={
                'temperature': 0.3,
                'top_p': 0.9,
            }
        )

        return response['message']['content']

    def _generate_no_context_response(self, question: str) -> ChatResponse:
        answer = (
            "Desculpe, não encontrei informações relevantes na base de conhecimento "
            "para responder sua pergunta. Por favor:\n\n"
            "1. Reformule sua pergunta de forma mais específica\n"
            "2. Verifique se o assunto está documentado no GLPI\n"
            "3. Abra um chamado para o time de TI se necessário\n\n"
            f"Pergunta recebida: \"{question}\""
        )

        return ChatResponse(
            answer=answer,
            sources=[],
            model_used=self.model
        )

rag_service = RAGService()