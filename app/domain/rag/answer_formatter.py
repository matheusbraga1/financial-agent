from __future__ import annotations

from typing import List, Dict
import re

from app.models.chat import SourceDocument
from app.utils.text_utils import process_answer_formats


class AnswerFormatter:
    def sanitize(self, text: str) -> str:
        try:
            text = re.sub(r"\bAbcd\.1234\b", "********", text)
            # Mascarar exemplos de senha padrão em backticks
            text = re.sub(r"(?i)(senha\s+padr(?:ao|ão)[^\n]*?)(`[^`]+`)", r"\1`********`", text)
            # Remover rótulos entre colchetes
            text = re.sub(r"\s*\[(?:E-?mail|Ferramentas?\s+Internas?|Documentos?)\]\s*", " ", text)
        except Exception:
            pass
        return text

    def build_context(self, documents: List[Dict[str, any]]) -> str:
        parts: List[str] = []
        for doc in documents:
            parts.append(f"[{doc.get('category','')}] {doc.get('title','')}\n{doc.get('content','')}\n")
        return "\n---\n".join(parts)

    def build_prompt(self, question: str, context: str, history: str = "") -> str:
        history_block = f"HISTÓRICO RECENTE (resumo):\n{history}\n\n" if history else ""
        prompt = (
            "Você é um assistente técnico de TI experiente da empresa.\n\n"
            "Você tem conhecimento sobre os procedimentos e soluções documentados pela equipe de TI:\n\n"
            f"{context}\n\n"
            f"{history_block}"
            "Com base no seu conhecimento acima, responda à seguinte pergunta do usuário:\n\n"
            f"{question}\n\n"
            "INSTRUÇÕES DE CONTEÚDO:\n"
            "- Responda de forma DIRETA e NATURAL, como um especialista\n"
            "- NÃO mencione artigos, documentos ou base de conhecimento\n"
            "- Se a pergunta estiver ampla/ambígua, faça 1–2 perguntas de esclarecimento curtas antes de responder\n"
            "- Sintetize tudo em UMA resposta coesa e bem estruturada\n"
            "- Seja prático, objetivo e útil\n"
            "- Use português brasileiro\n\n"
            "INSTRUÇÕES DE FORMATAÇÃO MARKDOWN:\n"
            "1. Use ## para título principal (quando apropriado)\n"
            "2. Use ### para subtítulos de seções\n"
            "3. Use **negrito** para destacar pontos importantes\n"
            "4. Use `código` para nomes de arquivos, comandos, caminhos\n"
            "5. Use listas numeradas para procedimentos passo a passo\n"
            "6. Use listas com marcadores (-) para itens não sequenciais\n"
            "7. Use > para avisos/alertas importantes\n"
            "8. Use --- para separar seções grandes\n"
            "9. Adicione espaçamento adequado entre seções\n\n"
            "Responda à pergunta com formatação markdown clara e profissional."
        )
        prompt += (
            "\n\n[RESTRIÇÃO] RESPONDA SOMENTE com base no CONTEXTO acima. "
            "Se o contexto não tiver informações suficientes, diga explicitamente que não há informação suficiente e sugira o próximo passo."
        )
        prompt += (
            "\n[SEGURANÇA] Não exponha credenciais internas (senhas, tokens, links internos ou exemplos como 'Abcd.1234'). "
            "Se for necessário mencionar credenciais, instrua a política sem revelar valores."
        )
        return prompt

    def make_sources(self, documents: List[Dict[str, any]]) -> List[SourceDocument]:
        items: List[SourceDocument] = []
        for doc in documents:
            if doc.get("title") and doc.get("category"):
                try:
                    score = float(doc.get("score", 0.0))
                except Exception:
                    score = 0.0
                snippet = None
                content = doc.get("content")
                if isinstance(content, str) and content.strip():
                    candidate = content.strip()
                    if "<" in candidate and ">" in candidate:
                        candidate = re.sub(r"<[^>]+>", " ", candidate)
                        try:
                            from html import unescape as _unescape
                            candidate = _unescape(candidate)
                        except Exception:
                            pass
                    candidate = re.sub(r"\b(?:alt|width|height|src|href|style|class)=\"[^\"]*\"", " ", candidate, flags=re.IGNORECASE)
                    candidate = re.sub(r"\b(?:alt|width|height|src|href|style|class)='[^']*'", " ", candidate, flags=re.IGNORECASE)
                    candidate = re.sub(r"\S*document\.send\.php\?docid=\d+\S*", " ", candidate, flags=re.IGNORECASE)
                    candidate = re.sub(r"\S*send\.php\?docid=\d+\S*", " ", candidate, flags=re.IGNORECASE)
                    candidate = re.sub(r"\s*/>\s*", " ", candidate)
                    candidate = re.sub(r"\s+", " ", candidate).strip()
                    snippet = candidate[:240].rstrip() + ("..." if len(candidate) > 240 else "")
                items.append(
                    SourceDocument(
                        id=str(doc.get("id")),
                        title=doc.get("title") or "",
                        category=doc.get("category") or "",
                        score=max(0.0, min(1.0, score)),
                        snippet=snippet,
                    )
                )
        return items

    def finalize_response_fields(self, answer_markdown: str):
        cleaned_markdown, html_answer, plain_answer = process_answer_formats(answer_markdown)
        return cleaned_markdown, html_answer, plain_answer
