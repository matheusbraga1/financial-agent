import re
import logging
import unicodedata
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class ChunkingStrategy(Enum):
    SEMANTIC = "semantic"
    SLIDING_WINDOW = "sliding_window"
    HIERARCHICAL = "hierarchical"

@dataclass
class ChunkConfig:
    strategy: ChunkingStrategy = ChunkingStrategy.SEMANTIC
    min_chunk_size: int = 500
    max_chunk_size: int = 2000
    overlap_size: int = 200
    preserve_sentences: bool = True
    preserve_paragraphs: bool = True
    include_title_context: bool = True
    quality_threshold: float = 0.4


@dataclass
class DocumentChunk:
    text: str
    chunk_index: int
    total_chunks: int
    start_char: int
    end_char: int
    quality_score: float
    metadata: Dict[str, Any]
    parent_section: Optional[str] = None
    semantic_type: Optional[str] = None


class IntelligentChunker:
    def __init__(self, config: Optional[ChunkConfig] = None):
        self.config = config or ChunkConfig()
        
        self.section_pattern = re.compile(r'^#+\s+(.+)$|^(.+):\s*$', re.MULTILINE)
        self.list_pattern = re.compile(r'^\s*[-*•]\s+.+$', re.MULTILINE)
        self.numbered_list_pattern = re.compile(r'^\s*\d+[\.)]\s+.+$', re.MULTILINE)
        self.paragraph_separator = re.compile(r'\n\s*\n')
        
    def chunk_document(
        self, 
        text: str, 
        title: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> List[DocumentChunk]:
        if not text or not text.strip():
            logger.warning(f"Empty document: {title}")
            return []
            
        text = self._normalize_text(text)
        
        strategy = self._determine_strategy(text)
        
        if strategy == ChunkingStrategy.SEMANTIC:
            chunks = self._semantic_chunking(text, title, metadata)
        elif strategy == ChunkingStrategy.HIERARCHICAL:
            chunks = self._hierarchical_chunking(text, title, metadata)
        else:
            chunks = self._sliding_window_chunking(text, title, metadata)
            
        quality_chunks = [
            chunk for chunk in chunks 
            if chunk.quality_score >= self.config.quality_threshold
        ]
        
        for i, chunk in enumerate(quality_chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(quality_chunks)
            
        logger.info(
            f"Document '{title}' chunked into {len(quality_chunks)} chunks "
            f"(filtered from {len(chunks)}, strategy={strategy.value})"
        )
        
        return quality_chunks
    
    def _determine_strategy(self, text: str) -> ChunkingStrategy:
        if self.section_pattern.findall(text):
            return ChunkingStrategy.HIERARCHICAL
            
        paragraphs = self.paragraph_separator.split(text)
        if len(paragraphs) > 3:
            return ChunkingStrategy.SEMANTIC
            
        return ChunkingStrategy.SLIDING_WINDOW
    
    def _semantic_chunking(
        self, 
        text: str, 
        title: str,
        metadata: Optional[Dict[str, Any]]
    ) -> List[DocumentChunk]:
        chunks = []
        
        units = self._extract_semantic_units(text)
        
        current_chunk = []
        current_size = 0
        start_char = 0
        
        for unit in units:
            unit_size = len(unit['text'])
            
            if current_size + unit_size > self.config.max_chunk_size and current_chunk:
                chunk_text = self._build_chunk_text(current_chunk, title)
                chunks.append(self._create_chunk(
                    text=chunk_text,
                    chunk_index=len(chunks),
                    start_char=start_char,
                    end_char=start_char + len(chunk_text),
                    semantic_type='mixed',
                    metadata=metadata
                ))
                
                if self.config.overlap_size > 0 and current_chunk:
                    current_chunk = [current_chunk[-1]]
                    current_size = len(current_chunk[0]['text'])
                else:
                    current_chunk = []
                    current_size = 0
                start_char = start_char + len(chunk_text) - current_size
            
            current_chunk.append(unit)
            current_size += unit_size
            
            if current_size >= self.config.min_chunk_size and unit['type'] in ['paragraph_end', 'section_end']:
                chunk_text = self._build_chunk_text(current_chunk, title)
                chunks.append(self._create_chunk(
                    text=chunk_text,
                    chunk_index=len(chunks),
                    start_char=start_char,
                    end_char=start_char + len(chunk_text),
                    semantic_type=self._determine_chunk_type(current_chunk),
                    metadata=metadata
                ))
                
                current_chunk = []
                current_size = 0
                start_char = start_char + len(chunk_text)
        
        if current_chunk:
            chunk_text = self._build_chunk_text(current_chunk, title)
            chunks.append(self._create_chunk(
                text=chunk_text,
                chunk_index=len(chunks),
                start_char=start_char,
                end_char=start_char + len(chunk_text),
                semantic_type=self._determine_chunk_type(current_chunk),
                metadata=metadata
            ))
        
        return chunks
    
    def _hierarchical_chunking(
        self, 
        text: str, 
        title: str,
        metadata: Optional[Dict[str, Any]]
    ) -> List[DocumentChunk]:
        chunks = []
        sections = self._extract_sections(text)
        
        for section in sections:
            section_text = section['content']
            section_title = section.get('title', '')
            
            if section_title:
                context = f"{title} > {section_title}"
            else:
                context = title
            
            if len(section_text) <= self.config.max_chunk_size:
                chunk_text = self._add_context(section_text, context)
                chunks.append(self._create_chunk(
                    text=chunk_text,
                    chunk_index=len(chunks),
                    start_char=section['start'],
                    end_char=section['end'],
                    semantic_type='section',
                    parent_section=section_title,
                    metadata=metadata
                ))
            else:
                sub_chunks = self._semantic_chunking(section_text, context, metadata)
                for sub_chunk in sub_chunks:
                    sub_chunk.parent_section = section_title
                    sub_chunk.chunk_index = len(chunks)
                    chunks.append(sub_chunk)
        
        return chunks
    
    def _sliding_window_chunking(
        self, 
        text: str, 
        title: str,
        metadata: Optional[Dict[str, Any]]
    ) -> List[DocumentChunk]:
        chunks = []
        
        if self.config.include_title_context:
            title_prefix = f"[{title}]\n\n"
        else:
            title_prefix = ""
        
        text_length = len(text)
        start = 0
        
        while start < text_length:
            end = min(start + self.config.max_chunk_size - len(title_prefix), text_length)
            
            if end < text_length and self.config.preserve_sentences:
                for sep in ['. ', '! ', '? ', '.\n', '!\n', '?\n', '\n\n']:
                    last_sep = text.rfind(sep, start, end)
                    if last_sep > start + self.config.min_chunk_size:
                        end = last_sep + len(sep)
                        break
            
            chunk_text = title_prefix + text[start:end].strip()
            
            chunks.append(self._create_chunk(
                text=chunk_text,
                chunk_index=len(chunks),
                start_char=start,
                end_char=end,
                semantic_type='sliding_window',
                metadata=metadata
            ))
            
            if end >= text_length:
                break
            start = max(start + 1, end - self.config.overlap_size)
        
        return chunks
    
    def _extract_semantic_units(self, text: str) -> List[Dict[str, Any]]:
        units = []
        
        paragraphs = self.paragraph_separator.split(text)
        
        for para in paragraphs:
            if not para.strip():
                continue
            
            if self.list_pattern.match(para) or self.numbered_list_pattern.match(para):
                units.append({
                    'text': para,
                    'type': 'list',
                    'breakable': False
                })
            elif para.strip().startswith('```'):
                units.append({
                    'text': para,
                    'type': 'code',
                    'breakable': False
                })
            elif self.numbered_list_pattern.match(para):
                units.append({
                    'text': para,
                    'type': 'procedure',
                    'breakable': False
                })
            else:
                units.append({
                    'text': para,
                    'type': 'paragraph',
                    'breakable': True
                })
        
        return units
    
    def _extract_sections(self, text: str) -> List[Dict[str, Any]]:
        sections = []
        
        matches = list(self.section_pattern.finditer(text))
        
        if not matches:
            return [{
                'title': '',
                'content': text,
                'start': 0,
                'end': len(text),
                'level': 0
            }]
        
        for i, match in enumerate(matches):
            section_start = match.start()
            section_title = match.group(1) or match.group(2) or ''
            
            if i + 1 < len(matches):
                section_end = matches[i + 1].start()
            else:
                section_end = len(text)
            
            content_start = match.end()
            section_content = text[content_start:section_end].strip()
            
            sections.append({
                'title': section_title.strip(),
                'content': section_content,
                'start': section_start,
                'end': section_end,
                'level': self._determine_section_level(match.group())
            })
        
        return sections
    
    def _determine_section_level(self, header: str) -> int:
        level = len(re.match(r'^#+', header).group()) if header.startswith('#') else 1
        return level
    
    def _build_chunk_text(self, units: List[Dict[str, Any]], title: str) -> str:
        texts = [unit['text'] for unit in units]
        content = '\n\n'.join(texts)
        
        if self.config.include_title_context:
            return f"[{title}]\n\n{content}"
        return content
    
    def _add_context(self, text: str, context: str) -> str:
        if self.config.include_title_context:
            return f"[{context}]\n\n{text}"
        return text
    
    def _determine_chunk_type(self, units: List[Dict[str, Any]]) -> str:
        types = [unit['type'] for unit in units]
        
        if 'procedure' in types:
            return 'procedure'
        elif 'list' in types:
            return 'list'
        elif 'code' in types:
            return 'code'
        elif all(t == 'paragraph' for t in types):
            return 'paragraph'
        else:
            return 'mixed'
    
    def _create_chunk(
        self,
        text: str,
        chunk_index: int,
        start_char: int,
        end_char: int,
        semantic_type: str,
        metadata: Optional[Dict[str, Any]] = None,
        parent_section: Optional[str] = None
    ) -> DocumentChunk:
        quality_score = self._assess_chunk_quality(text, semantic_type)
        
        return DocumentChunk(
            text=text,
            chunk_index=chunk_index,
            total_chunks=0,
            start_char=start_char,
            end_char=end_char,
            quality_score=quality_score,
            metadata=metadata or {},
            parent_section=parent_section,
            semantic_type=semantic_type
        )
    
    def _assess_chunk_quality(self, text: str, semantic_type: str) -> float:
        if not text or len(text) < 50:
            return 0.0
        
        score = 0.5
        
        if len(text) >= self.config.min_chunk_size:
            score += 0.2
        elif len(text) >= 200:
            score += 0.1
        
        alpha_ratio = sum(c.isalnum() or c.isspace() for c in text) / len(text)
        if alpha_ratio > 0.7:
            score += 0.2
        elif alpha_ratio > 0.5:
            score += 0.1
        
        if semantic_type in ['procedure', 'list', 'section']:
            score += 0.2
        elif semantic_type == 'paragraph':
            score += 0.1
        
        if text.rstrip().endswith(('.', '!', '?', ':', ';')):
            score += 0.1
        
        return min(1.0, max(0.0, score))
    
    def _normalize_text(self, text: str) -> str:
        """
        Normalize text for consistent processing.

        This method:
        - Normalizes Unicode characters to NFC form (composed)
        - Standardizes whitespace
        - Standardizes line endings
        - Removes control characters except newlines and tabs

        Args:
            text: Raw text to normalize

        Returns:
            Normalized text
        """
        if not text:
            return ""

        # Normalize Unicode to NFC (Canonical Composition)
        # Ensures consistent representation of accented characters
        text = unicodedata.normalize('NFC', text)

        # Remove control characters except newline and tab
        # Control characters can cause issues during chunking
        normalized_chars = []
        for char in text:
            category = unicodedata.category(char)
            # Keep non-control characters or newlines/tabs
            if category[0] != 'C' or char in '\n\t\r':
                normalized_chars.append(char)

        text = ''.join(normalized_chars)

        # Standardize line endings to Unix style
        text = text.replace('\r\n', '\n')
        text = text.replace('\r', '\n')

        # Normalize whitespace (but preserve single newlines)
        text = re.sub(r'[ \t]+', ' ', text)  # Multiple spaces/tabs to single space
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)  # Multiple newlines to double
        text = re.sub(r' *\n *', '\n', text)  # Remove spaces around newlines

        return text.strip()