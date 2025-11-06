import logging
from typing import List, Dict, Any
import ollama
import re
import unicodedata
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.core.config import get_settings
from app.services.embedding_service import embedding_service
from app.services.vector_store_service import vector_store_service
from app.models.chat import ChatResponse, SourceDocument
from app.utils.retry import retry_on_any_error

logger = logging.getLogger(__name__)
settings = get_settings()

class RAGService:
    def __init__(self):
        self.embedding_service = embedding_service
        self.vector_store = vector_store_service
        self.ollama_host = settings.ollama_host
        self.model = settings.ollama_model

        self.query_expansions = {
            'senha': ['password', 'login', 'acesso', 'autenticacao', 'credencial', 'logar', 'entrar', 'autenticar'],
            'login': ['senha', 'acesso', 'entrar', 'logar', 'credencial', 'usuario'],
            'acesso': ['senha', 'login', 'permissao', 'autorizacao', 'entrar', 'acessar'],
            'bloqueado': ['travado', 'bloqueio', 'locked', 'impedido', 'trancado'],
            'desbloquear': ['destravar', 'liberar', 'unlock', 'desbloquear'],

            'email': ['e-mail', 'correio', 'outlook', 'webmail', 'mensagem', 'mail', 'correio eletronico'],
            'mensagem': ['email', 'msg', 'comunicacao', 'aviso'],

            'internet': ['rede', 'conexao', 'wifi', 'network', 'conectividade', 'online', 'web'],
            'rede': ['internet', 'conexao', 'network', 'wifi', 'lan', 'conectividade'],
            'wifi': ['wireless', 'sem fio', 'rede', 'internet', 'conexao'],
            'vpn': ['rede privada', 'acesso remoto', 'conexao segura', 'virtual private'],

            'impressora': ['imprimir', 'impressao', 'printer', 'documento', 'pagina'],
            'imprimir': ['impressora', 'impressao', 'printer', 'documento', 'papel'],
            'scanner': ['escanear', 'digitalizar', 'scan', 'digitalizacao'],

            'sistema': ['aplicacao', 'programa', 'software', 'app', 'aplicativo', 'plataforma'],
            'aplicacao': ['sistema', 'programa', 'software', 'app', 'aplicativo'],
            'programa': ['sistema', 'aplicacao', 'software', 'app', 'ferramenta'],
            'instalar': ['instalacao', 'setup', 'configurar', 'baixar', 'download'],
            'atualizar': ['update', 'atualizacao', 'upgrade', 'nova versao'],

            'lento': ['devagar', 'travando', 'performance', 'lag', 'demora', 'lerdo', 'demorado'],
            'travando': ['congelando', 'lento', 'travado', 'freeze', 'parado', 'não responde'],
            'travado': ['travando', 'congelado', 'freeze', 'parado', 'bloqueado'],

            'erro': ['falha', 'problema', 'bug', 'defeito', 'issue', 'error', 'nao funciona'],
            'problema': ['erro', 'falha', 'bug', 'issue', 'dificuldade', 'defeito'],
            'falha': ['erro', 'problema', 'bug', 'nao funciona', 'quebrado'],
            'nao funciona': ['erro', 'problema', 'falha', 'quebrado', 'defeito', 'parou'],

            'computador': ['pc', 'notebook', 'laptop', 'maquina', 'desktop', 'micro'],
            'notebook': ['laptop', 'computador', 'portatil', 'pc'],
            'teclado': ['keyboard', 'teclas', 'digitar'],
            'mouse': ['cursor', 'ponteiro', 'clique'],
            'monitor': ['tela', 'display', 'video', 'screen'],

            'arquivo': ['documento', 'file', 'pasta', 'dados', 'doc'],
            'pasta': ['diretorio', 'folder', 'arquivo', 'pasta'],
            'documento': ['arquivo', 'doc', 'file', 'texto'],
            'backup': ['copia de seguranca', 'backup', 'recuperacao', 'restaurar'],

            'video': ['videoconferencia', 'reuniao', 'meet', 'zoom', 'teams', 'conferencia'],
            'reuniao': ['meeting', 'videoconferencia', 'chamada', 'video', 'encontro'],
            'teams': ['microsoft teams', 'reuniao', 'chat', 'videoconferencia'],
            'zoom': ['reuniao', 'videoconferencia', 'chamada', 'video'],

            'servidor': ['server', 'servidores', 'maquina', 'host', 'infraestrutura', 'datacenter'],
            'servidores': ['servidor', 'server', 'maquinas', 'hosts', 'infraestrutura'],
            'maquina virtual': ['vm', 'virtual machine', 'virtualizacao', 'servidor virtual', 'maquina'],
            'vm': ['maquina virtual', 'virtual machine', 'virtualizacao', 'servidor virtual'],
            'virtual': ['vm', 'virtualizacao', 'maquina virtual', 'virtual machine'],
            'lista': ['relacao', 'listagem', 'inventario', 'catalogo', 'registro'],

            'configurar': ['configuracao', 'setup', 'ajustar', 'parametrizar', 'definir'],
            'resetar': ['reiniciar', 'reset', 'restaurar', 'limpar', 'reboot'],
            'reiniciar': ['restart', 'reboot', 'resetar', 'religar'],
            'deletar': ['excluir', 'apagar', 'remover', 'delete'],
            'recuperar': ['restaurar', 'recovery', 'backup', 'resgatar'],
        }

        logger.info(f"RAG Service inicializado com modelo: {self.model}")

    def _normalize_text(self, text: str) -> str:
        """
        Normaliza texto removendo acentos e caracteres especiais.

        Args:
            text: Texto original

        Returns:
            Texto normalizado
        """
        nfd = unicodedata.normalize('NFD', text)
        text_without_accents = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')

        text_normalized = text_without_accents.lower()

        return text_normalized

    def _expand_query(self, question: str) -> str:
        """
        Expande a query adicionando sinônimos e termos relacionados.
        Usa normalização para melhorar matching.

        Args:
            question: Pergunta original

        Returns:
            Pergunta expandida com termos relacionados
        """
        normalized_question = self._normalize_text(question)
        words = normalized_question.split()

        expanded_terms = set()
        matched_keys = set()

        for word in words:
            clean_word = re.sub(r'[^\w\s]', '', word)

            if len(clean_word) < 3:
                continue

            for key, synonyms in self.query_expansions.items():
                key_normalized = self._normalize_text(key)

                if key_normalized == clean_word or key_normalized in clean_word or clean_word in key_normalized:
                    if key not in matched_keys:
                        num_synonyms = 4 if len(words) <= 3 else 3
                        expanded_terms.update(synonyms[:num_synonyms])
                        matched_keys.add(key)

        if expanded_terms:
            expanded_terms = {term for term in expanded_terms if self._normalize_text(term) not in normalized_question}

            if expanded_terms:
                expanded_query = f"{question} {' '.join(expanded_terms)}"
                logger.debug(f"Query expandida: '{question}' -> adicionados: {expanded_terms}")
                return expanded_query

        return question

    def _get_adaptive_params(self, question: str) -> dict:
        """
        Ajusta parâmetros de busca dinamicamente baseado na pergunta.
        MUITO PERMISSIVO - deixa o reranking filtrar resultados ruins.

        Args:
            question: Pergunta do usuário

        Returns:
            Dict com top_k e min_score ajustados
        """
        question_length = len(question.split())
        normalized_q = self._normalize_text(question)

        specific_terms = ['como fazer', 'passo a passo', 'tutorial', 'configurar', 'instalar', 'procedimento']
        has_specific_terms = any(term in normalized_q for term in specific_terms)

        problem_terms = ['nao funciona', 'erro', 'problema', 'travado', 'lento', 'nao consigo', 'ajuda']
        has_problem_terms = any(term in normalized_q for term in problem_terms)

        if question_length > 12 or has_specific_terms:
            return {
                "top_k": 7,
                "min_score": 0.20,
                "reasoning": "pergunta específica/detalhada"
            }
        elif has_problem_terms:
            return {
                "top_k": 10,
                "min_score": 0.15,
                "reasoning": "pergunta sobre problema"
            }
        elif question_length <= 5:
            return {
                "top_k": 10,
                "min_score": 0.15,
                "reasoning": "pergunta genérica/curta"
            }
        else:
            return {
                "top_k": 10,
                "min_score": 0.18,
                "reasoning": "padrão"
            }

    async def generate_answer(
            self,
            question: str,
            top_k: int = None,
            min_score: float = None
    ) -> ChatResponse:
        import time
        start_time = time.time()

        logger.info(f"Processando pergunta: {question[:50]}...")

        if not question or not question.strip():
            raise ValueError("Pergunta não pode estar vazia")

        adaptive_params = self._get_adaptive_params(question)
        if top_k is None:
            top_k = adaptive_params["top_k"]
        if min_score is None:
            min_score = adaptive_params["min_score"]

        logger.info(f"Parâmetros adaptativos: top_k={top_k}, min_score={min_score} ({adaptive_params['reasoning']})")

        expanded_question = self._expand_query(question)

        metrics = {}

        try:
            embed_start = time.time()
            question_vector = self.embedding_service.encode_text(expanded_question)
            metrics["embedding_time"] = time.time() - embed_start
            logger.debug(f"Embedding gerado em {metrics['embedding_time']:.3f}s")
        except Exception as e:
            logger.error(f"Erro ao gerar embedding: {e}")
            raise

        try:
            search_start = time.time()
            documents = self.vector_store.search_hybrid(
                query_text=expanded_question,
                query_vector=question_vector,
                limit=top_k,
                score_threshold=min_score
            )
            metrics["search_time"] = time.time() - search_start
            logger.info(f"Encontrados {len(documents)} documentos relevantes em {metrics['search_time']:.3f}s")
        except Exception as e:
            logger.error(f"Erro na busca vetorial: {e}")
            raise

        if not documents:
            logger.warning("Nenhum documento relevante encontrado")
            return self._generate_no_context_response(question)

        context = self._build_context(documents)

        prompt = self._build_prompt(question, context)

        try:
            llm_start = time.time()
            answer = await self._call_llm(prompt)
            metrics["llm_time"] = time.time() - llm_start
            logger.info(f"Resposta gerada em {metrics['llm_time']:.3f}s")
        except Exception as e:
            logger.error(f"Erro ao chamar LLM: {e}")
            raise

        sources = []
        for doc in documents:
            if doc.get("title") and doc.get("category"):
                normalized_score = max(0.0, min(1.0, float(doc["score"])))

                sources.append(
                    SourceDocument(
                        id=str(doc["id"]),
                        title=doc["title"],
                        category=doc["category"],
                        score=normalized_score
                    )
                )
            else:
                logger.warning(f"Documento {doc['id']} com campos inválidos, ignorando")

        metrics["total_time"] = time.time() - start_time
        metrics["num_documents"] = len(documents)
        metrics["avg_score"] = sum(doc["score"] for doc in documents) / len(documents) if documents else 0
        metrics["categories"] = list(set(doc["category"] for doc in documents if doc.get("category")))

        logger.info(f"✓ Processamento completo em {metrics['total_time']:.3f}s | Docs: {metrics['num_documents']} | Score médio: {metrics['avg_score']:.3f}")
        logger.debug(f"Métricas detalhadas: {metrics}")

        response = ChatResponse(
            answer=answer,
            sources=sources,
            model_used=self.model
        )

        return response

    def _build_context(self, documents: List[Dict[str, Any]]) -> str:
        """
        Constrói contexto sem mencionar explicitamente 'artigos'.
        O LLM deve tratar como conhecimento interno.
        """
        context_parts = []

        for doc in documents:
            context_parts.append(
                f"[{doc['category']}] {doc['title']}\n"
                f"{doc['content']}\n"
            )

        return "\n---\n".join(context_parts)

    def _build_prompt(self, question: str, context: str) -> str:
        """
        Constrói prompt para respostas com formatação markdown polida no estilo Claude.
        """
        prompt = f"""Você é um assistente técnico de TI experiente da empresa.

Você tem conhecimento sobre os procedimentos e soluções documentados pela equipe de TI:

{context}

Com base no seu conhecimento acima, responda a seguinte pergunta do usuário:

{question}

INSTRUÇÕES DE CONTEÚDO:
- Responda de forma DIRETA e NATURAL, como um especialista
- NÃO mencione artigos, documentos ou base de conhecimento
- Sintetize tudo em UMA resposta coesa e bem estruturada
- Seja prático, objetivo e útil
- Use português brasileiro

INSTRUÇÕES DE FORMATAÇÃO MARKDOWN:
1. Use ## para título principal (quando apropriado)
2. Use ### para subtítulos de seções
3. Use **negrito** para destacar pontos importantes
4. Use `código` para nomes de arquivos, comandos, caminhos
5. Use listas numeradas para procedimentos passo a passo
6. Use listas com marcadores (•) para itens não sequenciais
7. Use > para avisos/alertas importantes
8. Use --- para separar seções grandes
9. Adicione espaçamento adequado entre seções

EXEMPLO DE BOA FORMATAÇÃO:

## Configuração de Email

Para configurar seu email corporativo, siga estes passos:

### 1. Acesse as Configurações

Abra o aplicativo de email e navegue até:
- Vá em `Configurações > Contas`
- Selecione **Adicionar nova conta**

### 2. Insira os Dados

Configure com as seguintes informações:

```
Servidor: mail.empresa.com.br
Porta: 993
Usuário: seu.nome@empresa.com.br
```

> **Importante**: Use sua senha do Active Directory

### 3. Finalize

Após configurar, teste o envio e recebimento.

---

Responda à pergunta com formatação markdown clara e profissional:"""

        return prompt

    @retry_on_any_error(max_attempts=3)
    def _call_llm_sync(self, prompt: str) -> str:
        """
        Versão síncrona da chamada ao LLM com retry automático.
        """
        response = ollama.chat(
            model=self.model,
            messages=[
                {
                    'role': 'system',
                    'content': '''Você é um especialista técnico de TI experiente.

Responda perguntas de forma DIRETA, NATURAL e BEM FORMATADA usando Markdown.

FORMATAÇÃO OBRIGATÓRIA:
✓ Use ## e ### para títulos e subtítulos
✓ Use **negrito** para destacar informações importantes
✓ Use `código` para arquivos, comandos e caminhos
✓ Use listas numeradas para passos sequenciais
✓ Use > para avisos/alertas importantes
✓ Adicione espaçamento entre seções

CONTEÚDO:
✓ NÃO mencione "artigos", "documentos" ou "base de conhecimento"
✓ Responda como se você SOUBESSE a informação naturalmente
✓ Seja conciso, claro e prático
✓ Use português brasileiro profissional'''
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

    async def _call_llm(self, prompt: str) -> str:
        """
        Versão assíncrona da chamada ao LLM que não bloqueia o event loop.
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self._call_llm_sync, prompt)

    def _generate_no_context_response(self, question: str) -> ChatResponse:
        """
        Resposta quando não encontra informações relevantes, com formatação markdown.
        """
        answer = """## Informação Não Disponível

Desculpe, não tenho informações sobre esse assunto específico no momento.

### O que você pode fazer:

1. **Reformular a pergunta** - Tente usar palavras diferentes ou ser mais específico
2. **Consultar o GLPI** - Verifique se há documentação disponível no sistema
3. **Abrir um chamado** - A equipe de TI poderá ajudar diretamente

> **Dica**: Para questões urgentes, contate o suporte de TI diretamente."""

        return ChatResponse(
            answer=answer,
            sources=[],
            model_used=self.model
        )

rag_service = RAGService()