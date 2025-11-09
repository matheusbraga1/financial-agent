"""Answer Formatter aprimorado com few-shot examples."""

from __future__ import annotations

from typing import List, Dict, Optional
import re

from app.models.chat import SourceDocument
from app.domain.rag.answer_formatter import AnswerFormatter


class AnswerFormatterWithExamples(AnswerFormatter):
    """
    Formatter estendido com exemplos de respostas de alta qualidade (few-shot learning).

    Inclui exemplos específicos para cada tipo de pergunta e departamento.
    """

    # Few-shot examples organizados por tipo
    FEW_SHOT_EXAMPLES = """
EXEMPLOS DE RESPOSTAS DE ALTA QUALIDADE:

Exemplo 1 - RH:
Pergunta: "Como solicitar férias?"
Resposta:
## Como Solicitar Férias

**Passo a passo:**

1. Acesse o **sistema de RH** (portal.empresa.com/rh)
2. Vá em **"Solicitações" → "Férias"**
3. Escolha o período desejado
4. Anexe a **anuência do gestor** (formulário digital)
5. Clique em **"Enviar"**

**Prazos importantes:**
- Solicitar com pelo menos **30 dias de antecedência**
- Aguardar aprovação do RH (até 5 dias úteis)
- Férias podem ser divididas em até **3 períodos**

> **Dica:** Confira seu saldo de férias antes de solicitar em "Meus Dados → Saldo Férias"

---

Exemplo 2 - Financeiro:
Pergunta: "Como solicitar reembolso de despesas?"
Resposta:
## Como Solicitar Reembolso

Para solicitar reembolso de despesas corporativas:

### 1. Prepare a Documentação
- Notas fiscais originais ou digitalizadas
- Comprovantes de pagamento
- Justificativa da despesa

### 2. Preencha o Formulário
Acesse: `sistema.empresa.com/financeiro/reembolso`

Preencha:
- Centro de custo do projeto
- Descrição detalhada
- Valor total

### 3. Anexe os Documentos
Formatos aceitos: **PDF, JPG, PNG** (máx. 5MB cada)

### 4. Prazo de Análise
- Análise: até **10 dias úteis**
- Pagamento: junto com a folha do mês seguinte

> **Atenção:** Despesas acima de R$ 500,00 requerem aprovação prévia do gestor

---

Exemplo 3 - Troubleshooting:
Pergunta: "Impressora está offline"
Resposta:
## Resolver Impressora Offline

Tente estas soluções na ordem:

**Solução 1: Reiniciar Spooler de Impressão**
1. Pressione `Win + R`
2. Digite `services.msc` e pressione Enter
3. Localize **"Spooler de Impressão"**
4. Clique com botão direito → **"Reiniciar"**

**Solução 2: Verificar Conexão**
- Cabo USB conectado firmemente?
- Impressora ligada e com papel?
- LED de rede piscando? (se for impressora de rede)

**Solução 3: Reinstalar Impressora**
1. `Configurações → Dispositivos → Impressoras`
2. Remova a impressora problemática
3. Clique em **"Adicionar impressora"**
4. Selecione a impressora da lista

**Solução 4: Atualizar Driver**
1. Acesse o site do fabricante
2. Baixe o driver mais recente
3. Execute a instalação

> **Ainda não resolveu?** Abra um chamado informando qual solução tentou.
"""

    def build_prompt(
        self,
        question: str,
        context: str,
        history: str = "",
        department: Optional[str] = None,
        confidence: Optional[float] = None
    ) -> str:
        """
        Constrói prompt aprimorado com few-shot examples.

        Args:
            question: Pergunta do usuário
            context: Contexto dos documentos recuperados
            history: Histórico de conversas
            department: Departamento detectado (opcional)
            confidence: Score de confiança (opcional)

        Returns:
            Prompt completo
        """
        history_block = f"HISTÓRICO RECENTE (resumo):\n{history}\n\n" if history else ""

        # Descrição do departamento
        dept_descriptions = {
            "TI": "especialista técnico de TI",
            "RH": "especialista em Recursos Humanos",
            "Financeiro": "especialista em Finanças e Contabilidade",
            "Loteamento": "especialista em Loteamento e Urbanismo",
            "Aluguel": "especialista em Locação de Imóveis",
            "Juridico": "especialista em questões Jurídicas",
            "Geral": "especialista corporativo"
        }

        role = dept_descriptions.get(department, "assistente experiente da empresa")

        # Nota de confiança (se baixa, adicionar aviso)
        confidence_note = ""
        if confidence is not None and confidence < 0.4:
            confidence_note = (
                "\n> **NOTA**: A confiança desta resposta é BAIXA. "
                "Verifique informações com outras fontes ou contate o departamento responsável.\n\n"
            )

        prompt = f"""Você é um {role}.

CONHECIMENTO DISPONÍVEL:

{context}

{history_block}{self.FEW_SHOT_EXAMPLES}

---

Com base no CONHECIMENTO DISPONÍVEL acima e seguindo o ESTILO DOS EXEMPLOS, responda à seguinte pergunta:

{question}

INSTRUÇÕES DE CONTEÚDO:
- Responda de forma DIRETA e NATURAL, como um especialista
- NÃO mencione "base de conhecimento", "documentos" ou "artigos"
- Sintetize tudo em UMA resposta coesa e bem estruturada
- Seja prático, objetivo e útil
- Use português brasileiro
- Se a informação não estiver completa no conhecimento, seja honesto e sugira próximos passos

INSTRUÇÕES DE FORMATAÇÃO MARKDOWN:
1. Use ## para título principal (quando apropriado)
2. Use ### para subtítulos de seções
3. Use **negrito** para destacar pontos importantes
4. Use `código` para nomes de arquivos, comandos, caminhos, URLs
5. Use listas numeradas para procedimentos passo a passo
6. Use listas com marcadores (-) para itens não sequenciais
7. Use > para avisos/alertas importantes
8. Use --- para separar seções grandes quando necessário
9. Adicione espaçamento adequado entre seções

{confidence_note}[RESTRIÇÃO] RESPONDA SOMENTE com base no CONHECIMENTO DISPONÍVEL acima.
Se o contexto não tiver informações suficientes, diga explicitamente e sugira o próximo passo.

[SEGURANÇA] Não exponha credenciais internas (senhas, tokens, links internos).
Se necessário mencionar credenciais, instrua a política sem revelar valores reais.

RESPOSTA:"""

        return prompt


# Singleton
answer_formatter_with_examples = AnswerFormatterWithExamples()
