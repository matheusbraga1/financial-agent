"""
Content Cleaner Module

Responsible for cleaning and normalizing GLPI content.
Follows Single Responsibility Principle - only handles content cleaning.
"""
import base64
import re
import unicodedata
import logging
from html import unescape
from typing import Optional
from bs4 import BeautifulSoup

# Optional dependency - ftfy for encoding fixes
# If not available, falls back to basic encoding fixes
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
    """
    Cleans and normalizes GLPI content.

    This class handles:
    - Base64 detection and decoding
    - HTML tag removal
    - HTML entity decoding
    - Encoding fixes
    - Whitespace normalization
    """

    def __init__(self, min_content_length: int = 50):
        """
        Initialize content cleaner.

        Args:
            min_content_length: Minimum acceptable content length after cleaning
        """
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
        """
        Main cleaning method - orchestrates all cleaning steps.

        Args:
            content: Raw content from GLPI
            title: Article title (for logging)

        Returns:
            Cleaned plain text content
        """
        if not content:
            return ""

        original_length = len(content)

        # Pipeline of cleaning operations
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
        """
        Check if content is valid after cleaning.

        Args:
            content: Cleaned content

        Returns:
            True if content meets minimum requirements
        """
        return bool(content and len(content.strip()) >= self.min_content_length)

    # Private methods - each handles one specific concern

    def _is_base64(self, text: str) -> bool:
        """Check if text is base64 encoded."""
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
        """Decode base64 content if detected."""
        if self._is_base64(content):
            logger.info(f"Detected base64 content in '{title[:50]}...', decoding")
            try:
                decoded_bytes = base64.b64decode(content)
                return decoded_bytes.decode('utf-8')
            except Exception as e:
                logger.warning(f"Failed to decode base64: {e}")
        return content

    def _decode_html_entities(self, content: str) -> str:
        """Decode HTML entities like &lt;, &#60;, etc."""
        return unescape(content)

    def _remove_html_tags(self, content: str) -> str:
        """Remove HTML tags and extract plain text."""
        try:
            soup = BeautifulSoup(content, 'html.parser')

            # Remove script and style elements
            for script in soup(["script", "style"]):
                script.decompose()

            # Get text
            text = soup.get_text()

            # Clean up whitespace
            lines = (line.strip() for line in text.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            return ' '.join(chunk for chunk in chunks if chunk)
        except Exception as e:
            logger.warning(f"Failed to clean HTML: {e}")
            return content

    def _replace_html_characters(self, content: str) -> str:
        """Replace common HTML-escaped characters."""
        for old, new in self._html_replacements.items():
            content = content.replace(old, new)
        return content

    def _normalize_whitespace(self, content: str) -> str:
        """Normalize whitespace and newlines."""
        # Max 2 consecutive newlines
        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
        # Single spaces only
        content = re.sub(r' +', ' ', content)
        return content

    def _remove_non_printable(self, content: str) -> str:
        """Remove non-printable characters (except newlines and tabs)."""
        return ''.join(
            char for char in content
            if char.isprintable() or char in '\n\t'
        )

    def _fix_encoding(self, content: str) -> str:
        """
        Try to fix encoding issues using ftfy (if available).

        Falls back to basic encoding fixes if ftfy is not installed.
        """
        if not content:
            return content

        # If ftfy is available, use it
        if HAS_FTFY:
            try:
                fixed = ftfy.fix_text(content)
                if fixed != content:
                    logger.debug("Fixed encoding issues using ftfy")
                    return fixed
            except Exception as e:
                logger.debug(f"Failed to fix encoding with ftfy: {e}")

        # Fallback: Basic encoding fixes
        # Try to fix common encoding issues manually
        try:
            # Check for mojibake patterns
            if "??" in content or "\ufffd" in content:
                # Try UTF-8 misread as latin1
                try:
                    fixed = content.encode('utf-8', errors='ignore').decode('latin1', errors='ignore')
                    if "??" not in fixed and len(fixed) > len(content) * 0.8:
                        logger.debug("Fixed encoding using UTF-8 -> latin1")
                        return fixed
                except Exception:
                    pass

                # Try latin1 misread as UTF-8
                try:
                    fixed = content.encode('latin1', errors='ignore').decode('utf-8', errors='ignore')
                    if "??" not in fixed and len(fixed) > len(content) * 0.8:
                        logger.debug("Fixed encoding using latin1 -> UTF-8")
                        return fixed
                except Exception:
                    pass

        except Exception as e:
            logger.debug(f"Failed to fix encoding manually: {e}")

        return content

    def _normalize_unicode(self, content: str) -> str:
        """Normalize unicode to NFC form."""
        return unicodedata.normalize('NFC', content)

    def _log_cleaning_results(
        self,
        original_length: int,
        cleaned_length: int,
        title: str
    ) -> None:
        """Log cleaning results based on reduction severity."""
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


# Factory function for easier instantiation
def create_content_cleaner(min_content_length: int = 50) -> ContentCleaner:
    """
    Factory function to create a ContentCleaner instance.

    Args:
        min_content_length: Minimum acceptable content length

    Returns:
        Configured ContentCleaner instance
    """
    return ContentCleaner(min_content_length=min_content_length)
