import unicodedata
import re
from typing import Set


def normalize_text(text: str) -> str:
    if not text:
        return ""

    nfd = unicodedata.normalize("NFD", text)
    text_without_accents = "".join(
        char for char in nfd if unicodedata.category(char) != "Mn"
    )

    return text_without_accents.lower().strip()


def extract_words(text: str, remove_stopwords: bool = False) -> Set[str]:
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
