from typing import List, Dict, Any, Optional
import re

class AnswerGenerator:
    def build_context(self, documents: List[Dict[str, Any]]) -> str:
        if not documents:
            return ""
        
        context_parts: List[str] = []
        
        for i, doc in enumerate(documents, 1):
            title = doc.get("title", "Documento sem título")
            content = doc.get("content", "")
            score = doc.get("score", 0.0)
            category = doc.get("category", "")
            
            header = f"[Documento {i}] {title}"
            if category:
                header += f" ({category})"
            header += f" - Relevância: {score:.1%}"
            
            context_parts.append(f"{header}\n{content}\n")
        
        return "\n".join(context_parts)
    
    def build_prompt(
        self,
        question: str,
        context: str,
        history: str = "",
        domain: Optional[str] = None,
        confidence: float = 0.0,
    ) -> str:
        prompt_parts = [
            "# Seu Papel",
            "Você é um assistente de suporte técnico especializado e prestativo.",
            "Sua missão é ajudar usuários com informações precisas e claras.",
            "",
        ]
        
        if domain and domain != "Geral":
            prompt_parts.extend([
                f"## Domínio Detectado: {domain}",
                f"Você está respondendo uma questão relacionada a {domain}.",
                "",
            ])
        
        prompt_parts.extend([
            "# Exemplos de Boas Respostas",
            "",
            "**Exemplo 1 - Resposta Direta:**",
            "Usuário: Como resetar minha senha?",
            "Assistente: Para resetar sua senha, siga estes passos:",
            "1. Acesse o portal de login",
            "2. Clique em 'Esqueci minha senha'",
            "3. Digite seu email corporativo",
            "4. Siga as instruções recebidas por email",
            "",
            "**Exemplo 2 - Resposta com Contexto:**",
            "Usuário: O computador está lento",
            "Assistente: Entendo que seu computador está com lentidão. Aqui estão algumas soluções:",
            "- Feche programas não utilizados",
            "- Reinicie o computador",
            "- Verifique atualizações pendentes",
            "Se o problema persistir, abra um chamado no GLPI.",
            "",
        ])
        
        if history and history.strip():
            prompt_parts.extend([
                "# Histórico da Conversa",
                history,
                "",
            ])
        
        prompt_parts.extend([
            "# Informações Disponíveis",
            "Use APENAS as informações abaixo para responder:",
            "",
            context,
            "",
        ])
        
        prompt_parts.extend([
            "# Pergunta do Usuário",
            question,
            "",
        ])
        
        prompt_parts.append("# Sua Resposta")
        
        if confidence >= 0.75:
            prompt_parts.append(
                "Responda de forma clara e confiante, usando as informações acima:"
            )
        elif confidence >= 0.50:
            prompt_parts.append(
                "Responda com base nas informações disponíveis. "
                "Se houver incerteza, mencione:"
            )
        else:
            prompt_parts.append(
                "As informações disponíveis são limitadas. "
                "Responda honestamente e sugira alternativas se necessário:"
            )
        
        return "\n".join(prompt_parts)
    
    def sanitize(self, text: str) -> str:
        if not text:
            return ""
        
        lines = text.split("\n")
        unique_lines: List[str] = []
        
        for line in lines:
            if not unique_lines or line.strip() != unique_lines[-1].strip():
                unique_lines.append(line)
        
        text = "\n".join(unique_lines)
        
        text = "\n".join(line.rstrip() for line in text.split("\n"))
        
        while "\n\n\n" in text:
            text = text.replace("\n\n\n", "\n\n")
        
        text = re.sub(r'\s+([.,!?;:])', r'\1', text)
        
        text = re.sub(r'([.,!?;:])(\w)', r'\1 \2', text)
        
        prefixes_to_remove = [
            "Assistente:",
            "Assistant:",
            "Resposta:",
            "Answer:",
            "AI:",
        ]
        
        for prefix in prefixes_to_remove:
            if text.strip().startswith(prefix):
                text = text.strip()[len(prefix):].strip()
        
        return text.strip()
    
    def build_snippet(
        self, 
        title: str, 
        content: Optional[str], 
        metadata: Dict[str, Any]
    ) -> str:
        highlights: List[str] = []
        
        department = metadata.get("department")
        if department:
            highlights.append(f"[{department}]")
        
        section = metadata.get("section") or metadata.get("source_section")
        if section:
            highlights.append(section)
        
        text = (content or "").strip()
        if text:
            sentences = [
                s.strip() 
                for s in re.split(r'(?<=[.!?])\s+', text) 
                if s.strip()
            ]
            excerpt = ' '.join(sentences[:2]) if sentences else text[:280]
        else:
            excerpt = title
        
        snippet_body = ' '.join(filter(None, highlights + [excerpt])).strip()
        
        if len(snippet_body) > 420:
            snippet_body = snippet_body[:420].rsplit(' ', 1)[0] + '...'
        
        return snippet_body
    
    def format_sources(self, documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        sources: List[Dict[str, Any]] = []
        
        for doc in documents:
            try:
                snippet = doc.get("snippet")
                if not snippet:
                    snippet = self.build_snippet(
                        doc.get("title", ""),
                        doc.get("content"),
                        doc.get("metadata", {})
                    )
                
                source = {
                    "id": str(doc.get("id", "")),
                    "title": doc.get("title", "Documento sem título"),
                    "category": doc.get("category", ""),
                    "score": max(0.0, min(1.0, float(doc.get("score", 0.0)))),
                    "snippet": snippet,
                }
                
                sources.append(source)
                
            except Exception as e:
                continue
        
        return sources