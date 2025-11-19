import base64
import re
import unicodedata
import logging
from html import unescape
from typing import Optional
from bs4 import BeautifulSoup

try:
    import ftfy
    HAS_FTFY = True
except ImportError:
    HAS_FTFY = False
    logger = logging.getLogger(__name__)
    logger.info(
        "ftfy not installed - using basic encoding fixes. "
        "Install with: pip install ftfy"
    )

logger = logging.getLogger(__name__)


class ContentCleaner:
    def __init__(self, min_content_length: int = 50):
        self.min_content_length = min_content_length
        self._html_replacements = {
            '&nbsp;': ' ',
            '&quot;': '"',
            '&apos;': "'",
            '&amp;': '&',
            '&lt;': '<',
            '&gt;': '>',
            '\r\n': '\n',
            '\r': '\n',
        }

    def clean(self, content: str, title: str = "") -> str:
        if not content:
            return ""

        original_length = len(content)

        content = self._decode_base64_if_needed(content, title)
        content = self._decode_html_entities(content)
        content = self._remove_html_tags(content)
        content = self._replace_html_characters(content)
        content = self._normalize_whitespace(content)
        content = self._remove_non_printable(content)
        content = self._fix_encoding(content)
        content = self._normalize_unicode(content)
        content = content.strip()

        self._log_cleaning_results(original_length, len(content), title)

        return content

    def is_valid_content(self, content: str) -> bool:
        return bool(content and len(content.strip()) >= self.min_content_length)

    def _is_base64(self, text: str) -> bool:
        if not text or len(text) < 50:
            return False

        base64_pattern = re.compile(r'^[A-Za-z0-9+/=]+$')
        text_clean = text.strip()

        if not base64_pattern.match(text_clean) or len(text_clean) % 4 != 0:
            return False

        try:
            decoded = base64.b64decode(text_clean)
            decoded.decode('utf-8')
            return True
        except Exception:
            return False

    def _decode_base64_if_needed(self, content: str, title: str) -> str:
        if self._is_base64(content):
            logger.info(f"Detected base64 content in '{title[:50]}...', decoding")
            try:
                decoded_bytes = base64.b64decode(content)
                return decoded_bytes.decode('utf-8')
            except Exception as e:
                logger.warning(f"Failed to decode base64: {e}")
        return content

    def _decode_html_entities(self, content: str) -> str:
        return unescape(content)

    def _remove_html_tags(self, content: str) -> str:
        try:
            soup = BeautifulSoup(content, 'html.parser')

            for script in soup(["script", "style"]):
                script.decompose()

            text = soup.get_text()

            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            return ' '.join(chunk for chunk in chunks if chunk)
        except Exception as e:
            logger.warning(f"Failed to clean HTML: {e}")
            return content

    def _replace_html_characters(self, content: str) -> str:
        for old, new in self._html_replacements.items():
            content = content.replace(old, new)
        return content

    def _normalize_whitespace(self, content: str) -> str:
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        content = re.sub(r' +', ' ', content)
        return content

    def _remove_non_printable(self, content: str) -> str:
        return ''.join(
            char for char in content
            if (
                char.isprintable()
                or char in '\n\t\r'
                or unicodedata.category(char)[0] == 'L'
                or unicodedata.category(char)[0] == 'N'
                or unicodedata.category(char)[0] == 'P'
                or unicodedata.category(char)[0] == 'S'
            )
        )

    def _fix_encoding(self, content: str) -> str:
        if not content:
            return content

        if HAS_FTFY:
            try:
                fixed = ftfy.fix_text(content)
                if fixed != content:
                    logger.debug("Fixed encoding issues using ftfy")
                    return fixed
            except Exception as e:
                logger.debug(f"Failed to fix encoding with ftfy: {e}")

        return content

    def _normalize_unicode(self, content: str) -> str:
        return unicodedata.normalize('NFC', content)

    def _log_cleaning_results(
        self,
        original_length: int,
        cleaned_length: int,
        title: str
    ) -> None:
        if original_length == 0:
            return

        reduction_pct = (original_length - cleaned_length) / original_length * 100

        if cleaned_length < original_length * 0.15:
            logger.warning(
                f"Extreme content reduction: {original_length} -> {cleaned_length} chars "
                f"({reduction_pct:.0f}% reduced) for '{title[:50]}...'. "
                f"Content may be mostly HTML/formatting."
            )
        elif cleaned_length < original_length * 0.30:
            logger.info(
                f"Significant HTML removed: {original_length} -> {cleaned_length} chars "
                f"({reduction_pct:.0f}% reduced) for '{title[:50]}...'"
            )
        elif reduction_pct > 50:
            logger.debug(
                f"Content cleaned: {original_length} -> {cleaned_length} chars "
                f"({reduction_pct:.0f}% reduced) for '{title[:50]}...'"
            )


def create_content_cleaner(min_content_length: int = 50) -> ContentCleaner:
    return ContentCleaner(min_content_length=min_content_length)
