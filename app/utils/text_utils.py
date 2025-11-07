import re
import unicodedata
from typing import Tuple
import markdown
from bs4 import BeautifulSoup


def normalize_text(text: str) -> str:
    """
    Normaliza texto removendo acentos e convertendo para lowercase.
    """
    if not text:
        return ""

    nfd = unicodedata.normalize('NFD', text)
    text_without_accents = ''.join(char for char in nfd if unicodedata.category(char) != 'Mn')
    return text_without_accents.lower().strip()


def clean_markdown(markdown_text: str) -> str:
    """
    Limpa e padroniza markdown gerado pelo LLM.
    Remove inconsistências e normaliza formatação.
    """
    if not markdown_text:
        return ""

    text = markdown_text.strip()

    text = re.sub(r'\n{3,}', '\n\n', text)

    text = re.sub(r'^(#{1,6})\s*([^\n]+)\s*$', r'\1 \2', text, flags=re.MULTILINE)

    text = re.sub(r'```(\w+)?\n', r'```\1\n', text)
    text = re.sub(r'\n```\s*$', '\n```', text, flags=re.MULTILINE)

    text = re.sub(r'\*\*\*(.+?)\*\*\*', r'**\1**', text)

    text = re.sub(r'>\s*\*\*(.+?)\*\*:', r'> **\1**:', text)

    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        cleaned_line = line.rstrip()
        cleaned_lines.append(cleaned_line)

    return '\n'.join(cleaned_lines)


def markdown_to_html(markdown_text: str) -> str:
    """
    Converte markdown para HTML bem formatado e seguro.
    """
    if not markdown_text:
        return ""

    cleaned_md = clean_markdown(markdown_text)

    html = markdown.markdown(
        cleaned_md,
        extensions=[
            'fenced_code',
            'tables',
            'nl2br',
            'sane_lists'
        ]
    )

    soup = BeautifulSoup(html, 'html.parser')

    for tag in soup.find_all(['script', 'style', 'iframe']):
        tag.decompose()

    for a in soup.find_all('a'):
        a['target'] = '_blank'
        a['rel'] = 'noopener noreferrer'

    for code in soup.find_all('code'):
        if not code.parent or code.parent.name != 'pre':
            code['class'] = code.get('class', []) + ['inline-code']

    for blockquote in soup.find_all('blockquote'):
        blockquote['class'] = blockquote.get('class', []) + ['alert']

    return str(soup)


def markdown_to_plain_text(markdown_text: str) -> str:
    """
    Converte markdown para texto puro, removendo toda formatação.
    """
    if not markdown_text:
        return ""

    text = markdown_text

    text = re.sub(r'```[\s\S]*?```', '', text)

    text = re.sub(r'`([^`]+)`', r'\1', text)

    text = re.sub(r'^#{1,6}\s+', '', text, flags=re.MULTILINE)

    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    text = re.sub(r'__(.+?)__', r'\1', text)
    text = re.sub(r'\*(.+?)\*', r'\1', text)
    text = re.sub(r'_(.+?)_', r'\1', text)

    text = re.sub(r'>\s*', '', text)

    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)

    text = re.sub(r'^[\*\-\+]\s+', '', text, flags=re.MULTILINE)
    text = re.sub(r'^\d+\.\s+', '', text, flags=re.MULTILINE)

    text = re.sub(r'^---+$', '', text, flags=re.MULTILINE)

    text = re.sub(r'\n{3,}', '\n\n', text)

    return text.strip()


def process_answer_formats(markdown_answer: str) -> Tuple[str, str, str]:
    """
    Processa resposta e retorna em 3 formatos: markdown limpo, HTML, texto puro.

    Returns:
        Tuple[str, str, str]: (markdown, html, plain_text)
    """
    cleaned_md = clean_markdown(markdown_answer)
    html = markdown_to_html(cleaned_md)
    plain = markdown_to_plain_text(cleaned_md)

    return cleaned_md, html, plain

