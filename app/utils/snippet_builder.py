"""Snippet Builder - Utilit\u00e1rio para constru\u00e7\u00e3o de snippets de documentos.

Este m\u00f3dulo fornece funcionalidades para criar snippets formatados e
truncados de documentos, incluindo highlights de metadados e truncagem
inteligente em limites de senten\u00e7as.

Princípios Clean Code aplicados:
- Single Responsibility: Apenas constr\u00f3i snippets de documentos
- Open/Closed: Extens\u00edvel atrav\u00e9s de constantes configur\u00e1veis
- Don't Repeat Yourself: Elimina duplica\u00e7\u00e3o de l\u00f3gica de snippets
- Test\u00e1vel: M\u00e9todos est\u00e1ticos facilmente test\u00e1veis

Exemplo de uso:
    >>> from app.utils.snippet_builder import SnippetBuilder
    >>>
    >>> snippet = SnippetBuilder.build(
    ...     title="Como configurar VPN",
    ...     content="A VPN (Virtual Private Network) permite...",
    ...     metadata={"department": "TI", "section": "Redes"}
    ... )
    >>> print(snippet)
    [TI] [Redes] **Como configurar VPN** A VPN (Virtual Private Network)...
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SnippetBuilder:
    """Construtor de snippets formatados para documentos.

    Esta classe fornece métodos estáticos para construir snippets de
    documentos com formatação consistente, incluindo highlights de
    metadados (departamento, seção) e truncagem inteligente.

    Constantes de configuração:
        DEFAULT_MAX_LENGTH (int): Comprimento máximo do snippet (420 chars)
        MIN_TRUNCATE_RATIO (float): Proporção mínima para truncagem (0.7)
        SENTENCE_SEPARATORS (tuple): Separadores de sentenças

    Thread-safe: Sim (métodos estáticos sem estado mutável)

    Example:
        >>> metadata = {
        ...     "department": "RH",
        ...     "section": "Benefícios",
        ...     "category": "Vale Alimentação"
        ... }
        >>> snippet = SnippetBuilder.build(
        ...     title="Vale Alimentação 2024",
        ...     content="O vale alimentação é um benefício...",
        ...     metadata=metadata,
        ...     max_length=200
        ... )
    """

    # Constantes de configuração
    DEFAULT_MAX_LENGTH = 420  # Comprimento padrão do snippet
    MIN_TRUNCATE_RATIO = 0.7  # Mínimo 70% do tamanho desejado ao truncar
    SENTENCE_SEPARATORS = ('. ', '! ', '? ', '.\n', '!\n', '?\n', '\n\n')

    @staticmethod
    def build(
        title: str,
        content: Optional[str],
        metadata: Dict,
        max_length: int = DEFAULT_MAX_LENGTH
    ) -> str:
        """Constrói snippet formatado de documento.

        O snippet é composto por:
        1. Highlights de metadados (entre colchetes)
        2. Título em negrito
        3. Conteúdo truncado inteligentemente

        Formato: [DEPT] [SEÇÃO] **Título** Conteúdo...

        Args:
            title: Título do documento
            content: Conteúdo completo do documento (pode ser None)
            metadata: Dicionário com metadados do documento contendo:
                - department (str, optional): Departamento do documento
                - section (str, optional): Seção do documento
                - source_section (str, optional): Seção alternativa
            max_length: Comprimento máximo do snippet (default: 420)

        Returns:
            str: Snippet formatado e truncado

        Example:
            >>> snippet = SnippetBuilder.build(
            ...     title="Política de Férias",
            ...     content="Todo colaborador tem direito a 30 dias de férias...",
            ...     metadata={"department": "RH", "section": "Políticas"}
            ... )
            >>> print(snippet)
            [RH] [Políticas] **Política de Férias** Todo colaborador tem...
        """
        # Validação básica
        if not title:
            title = "Documento sem título"

        # Constrói highlights de metadados
        highlights = SnippetBuilder._build_highlights(metadata)

        # Constrói partes do snippet
        snippet_parts = []

        # Adiciona highlights
        if highlights:
            snippet_parts.append(highlights)

        # Adiciona título em negrito
        snippet_parts.append(f"**{title}**")

        # Calcula espaço disponível para conteúdo
        header_length = len(" ".join(snippet_parts))
        available_length = max_length - header_length - 5  # 5 chars para "..."

        # Adiciona conteúdo truncado
        if content and available_length > 50:  # Mínimo 50 chars de conteúdo
            truncated_content = SnippetBuilder._truncate_at_sentence(
                content,
                available_length
            )
            snippet_parts.append(truncated_content)

        # Junta todas as partes
        snippet = " ".join(snippet_parts)

        logger.debug(
            f"Built snippet for '{title[:30]}': "
            f"length={len(snippet)}, max={max_length}"
        )

        return snippet

    @staticmethod
    def _build_highlights(metadata: Dict) -> str:
        """Constrói string de highlights de metadados.

        Extrai departamento e seção dos metadados e formata como tags
        entre colchetes. Ignora valores vazios, None ou "GERAL".

        Args:
            metadata: Dicionário de metadados

        Returns:
            str: String formatada com highlights (ex: "[TI] [Redes]")
                 ou string vazia se não houver highlights

        Example:
            >>> metadata = {"department": "TI", "section": "Segurança"}
            >>> highlights = SnippetBuilder._build_highlights(metadata)
            >>> print(highlights)
            [TI] [Segurança]

            >>> metadata = {"department": "GERAL"}  # Ignorado
            >>> highlights = SnippetBuilder._build_highlights(metadata)
            >>> print(highlights)
            ''
        """
        highlights = []

        # Adiciona departamento (se não for GERAL)
        department = metadata.get("department")
        if department and str(department).upper() != "GERAL":
            highlights.append(f"[{department}]")

        # Adiciona seção (prioriza 'section', fallback para 'source_section')
        section = metadata.get("section") or metadata.get("source_section")
        if section and str(section).strip():
            highlights.append(f"[{section}]")

        return " ".join(highlights) if highlights else ""

    @staticmethod
    def _truncate_at_sentence(text: str, max_length: int) -> str:
        """Trunca texto em sentença completa mais próxima.

        Tenta truncar o texto no limite de sentença mais próximo do
        max_length, mantendo pelo menos MIN_TRUNCATE_RATIO do tamanho
        desejado. Se não encontrar separador adequado, trunca em palavra.

        Args:
            text: Texto completo a truncar
            max_length: Comprimento máximo desejado

        Returns:
            str: Texto truncado terminando em sentença completa ou "..."

        Example:
            >>> text = "Primeira sentença. Segunda sentença. Terceira sentença."
            >>> truncated = SnippetBuilder._truncate_at_sentence(text, 30)
            >>> print(truncated)
            Primeira sentença.

            >>> text = "Texto sem pontuação final"
            >>> truncated = SnippetBuilder._truncate_at_sentence(text, 15)
            >>> print(truncated)
            Texto sem...
        """
        # Se já cabe, retorna sem modificar
        if len(text) <= max_length:
            return text

        # Pega substring até max_length
        truncated = text[:max_length]

        # Calcula comprimento mínimo aceitável (70% do desejado)
        min_length = int(max_length * SnippetBuilder.MIN_TRUNCATE_RATIO)

        # Procura último separador de sentença dentro do range aceitável
        best_position = -1
        for separator in SnippetBuilder.SENTENCE_SEPARATORS:
            position = truncated.rfind(separator)
            if position > min_length:  # Está no range aceitável?
                # Inclui o separador no resultado
                best_position = position + len(separator)
                break

        # Se encontrou separador adequado, usa ele
        if best_position > 0:
            return truncated[:best_position].strip()

        # Fallback 1: Tenta truncar em espaço (palavra completa)
        last_space = truncated.rfind(' ')
        if last_space > min_length:
            return truncated[:last_space].strip() + "..."

        # Fallback 2: Trunca forçadamente e adiciona "..."
        return truncated.rstrip() + "..."

    @staticmethod
    def build_with_context(
        title: str,
        content: Optional[str],
        metadata: Dict,
        query: Optional[str] = None,
        max_length: int = DEFAULT_MAX_LENGTH
    ) -> str:
        """Constrói snippet com contexto da query (futura expansão).

        Versão futura que poderá destacar termos da query no snippet.
        Por enquanto, comporta-se igual a build().

        Args:
            title: Título do documento
            content: Conteúdo completo
            metadata: Metadados do documento
            query: Query do usuário (para highlight futuro)
            max_length: Comprimento máximo

        Returns:
            str: Snippet formatado

        Note:
            Esta é uma função placeholder para futura implementação de
            highlight de termos da query no snippet.
        """
        # TODO: Implementar highlight de query terms no conteúdo
        # Por enquanto, delega para build() padrão
        return SnippetBuilder.build(title, content, metadata, max_length)

    @staticmethod
    def estimate_snippet_length(
        title: str,
        metadata: Dict,
        content_length: Optional[int] = None
    ) -> Dict[str, int]:
        """Estima comprimento do snippet antes de construí-lo.

        Útil para otimização de queries e planejamento de espaço.

        Args:
            title: Título do documento
            metadata: Metadados do documento
            content_length: Comprimento do conteúdo (opcional)

        Returns:
            Dict com estimativas:
                - highlights_length: Tamanho dos highlights
                - title_length: Tamanho do título formatado
                - header_length: Tamanho total do cabeçalho
                - available_content_length: Espaço disponível para conteúdo
                - estimated_total: Tamanho total estimado

        Example:
            >>> estimate = SnippetBuilder.estimate_snippet_length(
            ...     title="Título Exemplo",
            ...     metadata={"department": "TI"},
            ...     content_length=500
            ... )
            >>> print(estimate)
            {
                'highlights_length': 4,
                'title_length': 18,
                'header_length': 23,
                'available_content_length': 392,
                'estimated_total': 415
            }
        """
        highlights = SnippetBuilder._build_highlights(metadata)
        highlights_length = len(highlights)

        title_formatted = f"**{title}**"
        title_length = len(title_formatted)

        # Cabeçalho: highlights + espaço + título + espaço
        header_length = highlights_length + (1 if highlights_length > 0 else 0) + title_length

        # Espaço disponível para conteúdo
        available_content = SnippetBuilder.DEFAULT_MAX_LENGTH - header_length - 5

        # Estima total (header + min conteúdo ou content_length)
        if content_length:
            content_part = min(content_length, available_content)
        else:
            content_part = available_content

        estimated_total = header_length + content_part + 1  # +1 para espaço

        return {
            "highlights_length": highlights_length,
            "title_length": title_length,
            "header_length": header_length,
            "available_content_length": available_content,
            "estimated_total": min(estimated_total, SnippetBuilder.DEFAULT_MAX_LENGTH)
        }
