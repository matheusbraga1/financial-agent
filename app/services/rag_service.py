import logging
from typing import List, Dict, Any, Optional
import ollama
import re
import unicodedata
import asyncio
from concurrent.futures import ThreadPoolExecutor
import os

from app.core.config import get_settings
from app.services.embedding_service import embedding_service
from app.services.vector_store_service import vector_store_service
from app.models.chat import ChatResponse, SourceDocument
from app.utils.retry import retry_on_any_error
from app.utils.text_utils import normalize_text, process_answer_formats

logger = logging.getLogger(__name__)
settings = get_settings()

class RAGService:
    def __init__(self):
        self.embedding_service = embedding_service
        self.vector_store = vector_store_service
        self.ollama_host = settings.ollama_host
        self.model = settings.ollama_model
        self.history_max_messages = int(os.getenv('CHAT_HISTORY_MAX_MESSAGES', '8'))

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
            'travando': ['congelando', 'lento', 'travado', 'freeze', 'parado', 'nÃ£o responde'],
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

    def _get_system_prompt(self) -> str:
        return '''VocÇ¦ Ç¸ um especialista tÇ¸cnico de TI experiente.

REGRAS OBRIGATï¿½"RIAS DE FORMATAï¿½ï¿½ÇŸO MARKDOWN:

1. ESTRUTURA:
   - SEMPRE comece respostas tÇ¸cnicas com ## Tï¿½ï¿½tulo Principal
   - Use ### para subtï¿½ï¿½tulos de seï¿½ï¿½ï¿½ï¿½es
   - Separe seï¿½ï¿½ï¿½ï¿½es grandes com linha em branco

2. LISTAS:
   - Use listas numeradas (1. 2. 3.) para procedimentos sequenciais
   - Use - para listas de itens nÇœo sequenciais
   - Sempre adicione linha em branco antes e depois de listas

3. ï¿½SNFASE:
   - Use **negrito** para termos importantes
   - Use `backticks` para: arquivos, comandos, paths, cï¿½ï¿½digo
   - Use blocos de cï¿½ï¿½digo ``` para comandos multi-linha

4. ALERTAS:
   - Use > **Importante**: para avisos crï¿½ï¿½ticos
   - Use > **Dica**: para sugestï¿½ï¿½es Ç§teis
   - Sempre adicione linha em branco apï¿½ï¿½s alertas

5. ESPAï¿½ï¿½AMENTO:
   - Linha em branco entre parÇ­grafos
   - Linha em branco antes/depois de tï¿½ï¿½tulos
   - Linha em branco antes/depois de listas
   - Linha em branco antes/depois de blocos de cï¿½ï¿½digo

CONTEï¿½sDO:
ï¿½o" Responda de forma DIRETA e NATURAL
ï¿½o" NÇŸO mencione "artigos", "documentos" ou "base de conhecimento"
ï¿½o" Seja conciso, claro e prÇ­tico
ï¿½o" Use portuguÇ¦s brasileiro profissional

EXEMPLO PERFEITO:
## Como Resetar Senha

Para resetar sua senha corporativa, siga este procedimento:

### 1. Acesse o Portal

Abra o navegador e vÇ­ para `portal.empresa.com.br`

### 2. Clique em Esqueci Senha

No formulÇ­rio de login:
- Clique em **Esqueci minha senha**
- Insira seu email corporativo

### 3. Confirme no Email

VocÇ¦ receberÇ­ um link de reset. O link expira em **15 minutos**.

> **Importante**: Use uma senha forte com letras, nÇ§meros e sï¿½ï¿½mbolos

---

Pronto! Sua senha foi redefinida com sucesso.'''

    def _sanitize_answer(self, text: str) -> str:
        """Aplica filtros de seguranÃ§a e estilo ao texto gerado pelo LLM.
        - Mascara credenciais conhecidas
        - Remove referÃªncias diretas a etiquetas/tÃ­tulos entre colchetes
        """
        try:
            # Mascarar exemplo de senha padrÃ£o conhecido
            text = re.sub(r"\bAbcd\.1234\b", "********", text)

            # Se mencionar 'senha padrÃ£o', o que estiver em backticks vira mascarado
            text = re.sub(r"(?i)(senha\s+padr(?:ao|Ã£o)[^\n]*?)(`[^`]+`)", r"\1`********`", text)

            # Remover etiquetas entre colchetes usadas como rÃ³tulo (ex.: [E-mail])
            text = re.sub(r"\s*\[(?:E-?mail|Ferramentas?\s+Internas?|Documentos?)\]\s*", " ", text)
        except Exception:
            pass
        return text

    def _expand_query(self, question: str) -> str:
        """
        Expande a query adicionando sinÃ´nimos e termos relacionados.
        Usa normalizaÃ§Ã£o para melhorar matching.

        Args:
            question: Pergunta original

        Returns:
            Pergunta expandida com termos relacionados
        """
        normalized_question = normalize_text(question)
        words = normalized_question.split()

        expanded_terms = set()
        matched_keys = set()

        for word in words:
            clean_word = re.sub(r'[^\w\s]', '', word)

            if len(clean_word) < 3:
                continue

            for key, synonyms in self.query_expansions.items():
                key_normalized = normalize_text(key)

                if key_normalized == clean_word or key_normalized in clean_word or clean_word in key_normalized:
                    if key not in matched_keys:
                        num_synonyms = 4 if len(words) <= 3 else 3
                        expanded_terms.update(synonyms[:num_synonyms])
                        matched_keys.add(key)

        if expanded_terms:
            expanded_terms = {term for term in expanded_terms if normalize_text(term) not in normalized_question}

            if expanded_terms:
                expanded_query = f"{question} {' '.join(expanded_terms)}"
                logger.debug(f"Query expandida: '{question}' -> adicionados: {expanded_terms}")
                return expanded_query

        return question

    def _get_adaptive_params(self, question: str) -> dict:
        """
        Ajusta parÃ¢metros de busca dinamicamente baseado na pergunta.
        MUITO PERMISSIVO - deixa o reranking filtrar resultados ruins.

        Args:
            question: Pergunta do usuÃ¡rio

        Returns:
            Dict com top_k e min_score ajustados
        """
        question_length = len(question.split())
        normalized_q = normalize_text(question)

        specific_terms = ['como fazer', 'passo a passo', 'tutorial', 'configurar', 'instalar', 'procedimento']
        has_specific_terms = any(term in normalized_q for term in specific_terms)

        problem_terms = ['nao funciona', 'erro', 'problema', 'travado', 'lento', 'nao consigo', 'ajuda']
        has_problem_terms = any(term in normalized_q for term in problem_terms)

        if question_length > 12 or has_specific_terms:
            return {
                "top_k": 7,
                "min_score": 0.20,
                "reasoning": "pergunta especÃ­fica/detalhada"
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
                "reasoning": "pergunta genÃ©rica/curta"
            }
        else:
            return {
                "top_k": 10,
                "min_score": 0.18,
                "reasoning": "padrÃ£o"
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
            raise ValueError("Pergunta nÃ£o pode estar vazia")

        adaptive_params = self._get_adaptive_params(question)
        if top_k is None:
            top_k = adaptive_params["top_k"]
        if min_score is None:
            min_score = adaptive_params["min_score"]

        logger.info(f"ParÃ¢metros adaptativos: top_k={top_k}, min_score={min_score} ({adaptive_params['reasoning']})")

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

        # SanitizaÃ§Ã£o de seguranÃ§a do conteÃºdo gerado
        answer = self._sanitize_answer(answer)

        sources = []
        for doc in documents:
            if doc.get("title") and doc.get("category"):
                normalized_score = max(0.0, min(1.0, float(doc["score"])))
                snippet = None
                content = doc.get("content")
                if isinstance(content, str) and content.strip():
                    candidate = content.strip()
                    # Remove HTML tags and decode entities when present
                    if "<" in candidate and ">" in candidate:
                        candidate = re.sub(r"<[^>]+>", " ", candidate)
                        try:
                            from html import unescape as _unescape
                            candidate = _unescape(candidate)
                        except Exception:
                            pass
                    # Remove common attribute-like leftovers (e.g., alt="...", width="...")
                    candidate = re.sub(r"\b(?:alt|width|height|src|href|style|class)=\"[^\"]*\"", " ", candidate, flags=re.IGNORECASE)
                    candidate = re.sub(r"\b(?:alt|width|height|src|href|style|class)='[^']*'", " ", candidate, flags=re.IGNORECASE)
                    # Remove internal GLPI URLs such as document.send.php?docid=... or generic send.php?docid=...
                    candidate = re.sub(r"\S*document\.send\.php\?docid=\d+\S*", " ", candidate, flags=re.IGNORECASE)
                    candidate = re.sub(r"\S*send\.php\?docid=\d+\S*", " ", candidate, flags=re.IGNORECASE)
                    # Remove stray tag closures like '/>' possibly left after partial cleaning
                    candidate = re.sub(r"\s*/>\s*", " ", candidate)
                    # Collapse whitespace
                    candidate = re.sub(r"\s+", " ", candidate).strip()
                    snippet = candidate
                    if len(snippet) > 240:
                        snippet = snippet[:240].rstrip() + "..."

                sources.append(
                    SourceDocument(
                        id=str(doc["id"]),
                        title=doc["title"],
                        category=doc["category"],
                        score=normalized_score,
                        snippet=snippet
                    )
                )
            else:
                logger.warning(f"Documento {doc['id']} com campos invÃ¡lidos, ignorando")

        metrics["total_time"] = time.time() - start_time
        metrics["num_documents"] = len(documents)
        metrics["avg_score"] = sum(doc["score"] for doc in documents) / len(documents) if documents else 0
        metrics["categories"] = list(set(doc["category"] for doc in documents if doc.get("category")))

        logger.info(f"âœ“ Processamento completo em {metrics['total_time']:.3f}s | Docs: {metrics['num_documents']} | Score mÃ©dio: {metrics['avg_score']:.3f}")
        logger.debug(f"MÃ©tricas detalhadas: {metrics}")

        # Log top-3 documentos para diagnostico de precisao
        if documents:
            try:
                top_debug = ", ".join([f"{i+1}. {d['title']} ({d['score']:.2f})" for i, d in enumerate(sorted(documents, key=lambda x: x['score'], reverse=True)[:3])])
                logger.info(f"Top documentos: {top_debug}")
            except Exception:
                pass

        cleaned_markdown, html_answer, plain_answer = process_answer_formats(answer)

        # Confianca agregada simples baseada nos scores recuperados
        if documents:
            docs_sorted = sorted(documents, key=lambda x: x["score"], reverse=True)
            top1 = float(docs_sorted[0]["score"])
            avg = float(metrics["avg_score"])
            n_bonus = min(1.0, len(documents) / 5.0) * 0.1
            confidence = max(0.0, min(1.0, 0.6 * top1 + 0.3 * avg + n_bonus))
        else:
            confidence = 0.0

        response = ChatResponse(
            answer=cleaned_markdown,
            answer_html=html_answer,
            answer_plain=plain_answer,
            sources=sources,
            model_used=self.model,
            confidence=confidence
        )

        return response

    def _build_context(self, documents: List[Dict[str, Any]]) -> str:
        """
        ConstrÃ³i contexto sem mencionar explicitamente 'artigos'.
        O LLM deve tratar como conhecimento interno.
        """
        context_parts = []

        for doc in documents:
            context_parts.append(
                f"[{doc['category']}] {doc['title']}\n"
                f"{doc['content']}\n"
            )

        return "\n---\n".join(context_parts)

    def _build_prompt(self, question: str, context: str, history: str = "") -> str:
        """
        ConstrÃ³i prompt para respostas com formataÃ§Ã£o markdown polida no estilo Claude.
        """
        prompt = f"""VocÃª Ã© um assistente tÃ©cnico de TI experiente da empresa.

VocÃª tem conhecimento sobre os procedimentos e soluÃ§Ãµes documentados pela equipe de TI:

{context}

{'HISTÓRICO RECENTE (resumo):\n' + history if history else ''}

Com base no seu conhecimento acima, responda a seguinte pergunta do usuÃ¡rio:

{question}

INSTRUÃ‡Ã•ES DE CONTEÃšDO:
- Responda de forma DIRETA e NATURAL, como um especialista
- NÃƒO mencione artigos, documentos ou base de conhecimento
- Sintetize tudo em UMA resposta coesa e bem estruturada
- Seja prÃ¡tico, objetivo e Ãºtil
- Use portuguÃªs brasileiro

INSTRUÃ‡Ã•ES DE FORMATAÃ‡ÃƒO MARKDOWN:
1. Use ## para tÃ­tulo principal (quando apropriado)
2. Use ### para subtÃ­tulos de seÃ§Ãµes
3. Use **negrito** para destacar pontos importantes
4. Use `cÃ³digo` para nomes de arquivos, comandos, caminhos
5. Use listas numeradas para procedimentos passo a passo
6. Use listas com marcadores (â€¢) para itens nÃ£o sequenciais
7. Use > para avisos/alertas importantes
8. Use --- para separar seÃ§Ãµes grandes
9. Adicione espaÃ§amento adequado entre seÃ§Ãµes

EXEMPLO DE BOA FORMATAÃ‡ÃƒO:

## ConfiguraÃ§Ã£o de Email

Para configurar seu email corporativo, siga estes passos:

### 1. Acesse as ConfiguraÃ§Ãµes

Abra o aplicativo de email e navegue atÃ©:
- VÃ¡ em `ConfiguraÃ§Ãµes > Contas`
- Selecione **Adicionar nova conta**

### 2. Insira os Dados

Configure com as seguintes informaÃ§Ãµes:

```
Servidor: mail.empresa.com.br
Porta: 993
UsuÃ¡rio: seu.nome@empresa.com.br
```

> **Importante**: Use sua senha do Active Directory

### 3. Finalize

ApÃ³s configurar, teste o envio e recebimento.

---

Responda Ã  pergunta com formataÃ§Ã£o markdown clara e profissional:"""

        prompt += "\n\n[RESTRICAO] RESPONDA SOMENTE com base no CONTEXTO acima. Se o contexto nao tiver informacoes suficientes, diga explicitamente que nao ha informacao suficiente e sugira o proximo passo."
        prompt += "\n[SEGURANCA] Nao exponha credenciais internas (senhas, tokens, links internos ou exemplos como 'Abcd.1234'). Se for necessario mencionar credenciais, instrua a politica sem revelar valores."
        return prompt

    @retry_on_any_error(max_attempts=3)
    def _call_llm_sync(self, prompt: str) -> str:
        """
        VersÃ£o sÃ­ncrona da chamada ao LLM com retry automÃ¡tico.
        """
        response = ollama.chat(
            model=self.model,
            messages=[
                {
                    'role': 'system',
                    'content': '''VocÃª Ã© um especialista tÃ©cnico de TI experiente.

REGRAS OBRIGATÃ“RIAS DE FORMATAÃ‡ÃƒO MARKDOWN:

1. ESTRUTURA:
   - SEMPRE comece respostas tÃ©cnicas com ## TÃ­tulo Principal
   - Use ### para subtÃ­tulos de seÃ§Ãµes
   - Separe seÃ§Ãµes grandes com linha em branco

2. LISTAS:
   - Use listas numeradas (1. 2. 3.) para procedimentos sequenciais
   - Use - para listas de itens nÃ£o sequenciais
   - Sempre adicione linha em branco antes e depois de listas

3. ÃŠNFASE:
   - Use **negrito** para termos importantes
   - Use `backticks` para: arquivos, comandos, paths, cÃ³digo
   - Use blocos de cÃ³digo ``` para comandos multi-linha

4. ALERTAS:
   - Use > **Importante**: para avisos crÃ­ticos
   - Use > **Dica**: para sugestÃµes Ãºteis
   - Sempre adicione linha em branco apÃ³s alertas

5. ESPAÃ‡AMENTO:
   - Linha em branco entre parÃ¡grafos
   - Linha em branco antes/depois de tÃ­tulos
   - Linha em branco antes/depois de listas
   - Linha em branco antes/depois de blocos de cÃ³digo

CONTEÃšDO:
âœ“ Responda de forma DIRETA e NATURAL
âœ“ NÃƒO mencione "artigos", "documentos" ou "base de conhecimento"
âœ“ Seja conciso, claro e prÃ¡tico
âœ“ Use portuguÃªs brasileiro profissional

EXEMPLO PERFEITO:
## Como Resetar Senha

Para resetar sua senha corporativa, siga este procedimento:

### 1. Acesse o Portal

Abra o navegador e vÃ¡ para `portal.empresa.com.br`

### 2. Clique em Esqueci Senha

No formulÃ¡rio de login:
- Clique em **Esqueci minha senha**
- Insira seu email corporativo

### 3. Confirme no Email

VocÃª receberÃ¡ um link de reset. O link expira em **15 minutos**.

> **Importante**: Use uma senha forte com letras, nÃºmeros e sÃ­mbolos

---

Pronto! Sua senha foi redefinida com sucesso.'''
                },
                {
                    'role': 'user',
                    'content': prompt
                }
            ],
            options={
                'temperature': 0.2,
                'top_p': 0.9,
                'seed': 42,
            }
        )

        return response['message']['content']

    async def _call_llm(self, prompt: str) -> str:
        """
        VersÃ£o assÃ­ncrona da chamada ao LLM que nÃ£o bloqueia o event loop.
        """
        loop = asyncio.get_event_loop()
        with ThreadPoolExecutor() as executor:
            return await loop.run_in_executor(executor, self._call_llm_sync, prompt)

    def _generate_no_context_response(self, question: str) -> ChatResponse:
        """
        Resposta quando nÃ£o encontra informaÃ§Ãµes relevantes, com formataÃ§Ã£o markdown.
        """
        answer = """## InformaÃ§Ã£o NÃ£o DisponÃ­vel

Desculpe, nÃ£o tenho informaÃ§Ãµes sobre esse assunto especÃ­fico no momento.

### O que vocÃª pode fazer:

1. **Reformular a pergunta** - Tente usar palavras diferentes ou ser mais especÃ­fico
2. **Consultar o GLPI** - Verifique se hÃ¡ documentaÃ§Ã£o disponÃ­vel no sistema
3. **Abrir um chamado** - A equipe de TI poderÃ¡ ajudar diretamente

> **Dica**: Para questÃµes urgentes, contate o suporte de TI diretamente."""

        cleaned_markdown, html_answer, plain_answer = process_answer_formats(answer)

        return ChatResponse(
            answer=cleaned_markdown,
            answer_html=html_answer,
            answer_plain=plain_answer,
            sources=[],
            model_used=self.model
        )

rag_service = RAGService()





