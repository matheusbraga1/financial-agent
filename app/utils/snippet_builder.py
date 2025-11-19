from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class SnippetBuilder:

    DEFAULT_MAX_LENGTH = 420
    MIN_TRUNCATE_RATIO = 0.7
    SENTENCE_SEPARATORS = ('. ', '! ', '? ', '.\n', '!\n', '?\n', '\n\n')

    @staticmethod
    def build(
        title: str,
        content: Optional[str],
        metadata: Dict,
        max_length: int = DEFAULT_MAX_LENGTH
    ) -> str:
        if not title:
            title = "Documento sem título"

        highlights = SnippetBuilder._build_highlights(metadata)

        snippet_parts = []

        if highlights:
            snippet_parts.append(highlights)

        snippet_parts.append(f"**{title}**")

        header_length = len(" ".join(snippet_parts))
        available_length = max_length - header_length - 5

        if content and available_length > 50:
            truncated_content = SnippetBuilder._truncate_at_sentence(
                content,
                available_length
            )
            snippet_parts.append(truncated_content)

        snippet = " ".join(snippet_parts)

        logger.debug(
            f"Built snippet for '{title[:30]}': "
            f"length={len(snippet)}, max={max_length}"
        )

        return snippet

    @staticmethod
    def _build_highlights(metadata: Dict) -> str:
        highlights = []

        department = metadata.get("department")
        if department and str(department).upper() != "GERAL":
            highlights.append(f"[{department}]")

        section = metadata.get("section") or metadata.get("source_section")
        if section and str(section).strip():
            highlights.append(f"[{section}]")

        return " ".join(highlights) if highlights else ""

    @staticmethod
    def _truncate_at_sentence(text: str, max_length: int) -> str:
        if len(text) <= max_length:
            return text

        truncated = text[:max_length]

        min_length = int(max_length * SnippetBuilder.MIN_TRUNCATE_RATIO)

        best_position = -1
        for separator in SnippetBuilder.SENTENCE_SEPARATORS:
            position = truncated.rfind(separator)
            if position > min_length:
                best_position = position + len(separator)
                break

        if best_position > 0:
            return truncated[:best_position].strip()

        last_space = truncated.rfind(' ')
        if last_space > min_length:
            return truncated[:last_space].strip() + "..."

        return truncated.rstrip() + "..."

    @staticmethod
    def build_with_context(
        title: str,
        content: Optional[str],
        metadata: Dict,
        query: Optional[str] = None,
        max_length: int = DEFAULT_MAX_LENGTH
    ) -> str:
        return SnippetBuilder.build(title, content, metadata, max_length)

    @staticmethod
    def estimate_snippet_length(
        title: str,
        metadata: Dict,
        content_length: Optional[int] = None
    ) -> Dict[str, int]:
        highlights = SnippetBuilder._build_highlights(metadata)
        highlights_length = len(highlights)

        title_formatted = f"**{title}**"
        title_length = len(title_formatted)

        header_length = highlights_length + (1 if highlights_length > 0 else 0) + title_length

        available_content = SnippetBuilder.DEFAULT_MAX_LENGTH - header_length - 5

        if content_length:
            content_part = min(content_length, available_content)
        else:
            content_part = available_content

        estimated_total = header_length + content_part + 1

        return {
            "highlights_length": highlights_length,
            "title_length": title_length,
            "header_length": header_length,
            "available_content_length": available_content,
            "estimated_total": min(estimated_total, SnippetBuilder.DEFAULT_MAX_LENGTH)
        }
