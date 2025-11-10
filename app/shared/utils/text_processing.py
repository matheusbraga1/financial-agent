"""Text processing utilities.

Functions for text normalization, cleaning, and tokenization.
"""

import unicodedata
import re
from typing import Set


def normalize_text(text: str) -> str:
    """Normalize text by removing accents and converting to lowercase.

    Args:
        text: Text to normalize

    Returns:
        Normalized text (lowercase, no accents)

    Examples:
        >>> normalize_text("Olá Mundo!")
        'ola mundo!'
    """
    if not text:
        return ""

    # Remove accents using NFD normalization
    nfd = unicodedata.normalize("NFD", text)
    text_without_accents = "".join(
        char for char in nfd if unicodedata.category(char) != "Mn"
    )

    return text_without_accents.lower().strip()


def extract_words(text: str, remove_stopwords: bool = False) -> Set[str]:
    """Extract words from text.

    Args:
        text: Text to extract words from
        remove_stopwords: If True, remove common Portuguese stopwords

    Returns:
        Set of words found in text
    """
    if not text:
        return set()

    normalized = normalize_text(text)
    words = set(re.findall(r"\w+", normalized))

    if remove_stopwords:
        stopwords = {
            "a", "o", "as", "os", "um", "uma", "uns", "umas",
            "de", "do", "da", "dos", "das",
            "e", "em", "no", "na", "nos", "nas",
            "para", "por", "com", "sem", "ao", "aos",
            "que", "como", "ser", "estar", "ter", "fazer",
            "nao", "duvida", "duvidas", "pergunta", "perguntas",
        }
        words = words - stopwords

    return words
