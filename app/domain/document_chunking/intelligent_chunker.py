import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ChunkingStrategy(Enum):
    """Chunking strategies for different document types."""
    SEMANTIC = "semantic"  # Preserve semantic units (paragraphs, sections)
    SLIDING_WINDOW = "sliding_window"  # Traditional sliding window
    HIERARCHICAL = "hierarchical"  # Preserve document hierarchy


@dataclass
class ChunkConfig:
    """Configuration for chunking behavior."""
    strategy: ChunkingStrategy = ChunkingStrategy.SEMANTIC
    min_chunk_size: int = 500  # Minimum characters per chunk
    max_chunk_size: int = 2000  # Maximum characters per chunk (increased from 700!)
    overlap_size: int = 200  # Overlap between chunks
    preserve_sentences: bool = True  # Don't break mid-sentence
    preserve_paragraphs: bool = True  # Try to keep paragraphs together
    include_title_context: bool = True  # Include title in each chunk
    quality_threshold: float = 0.4  # Minimum quality score to keep chunk


@dataclass
class DocumentChunk:
    """Represents a chunk of a document with metadata."""
    text: str
    chunk_index: int
    total_chunks: int
    start_char: int
    end_char: int
    quality_score: float
    metadata: Dict[str, Any]
    parent_section: Optional[str] = None
    semantic_type: Optional[str] = None  # 'procedure', 'list', 'paragraph', etc.


class IntelligentChunker:
    """
    Intelligent document chunking that preserves semantic meaning.
    
    Key improvements over simple character splitting:
    1. Preserves complete semantic units (paragraphs, lists, procedures)
    2. Maintains document structure and hierarchy
    3. Includes contextual information in each chunk
    4. Adapts chunk size based on content type
    """
    
    def __init__(self, config: Optional[ChunkConfig] = None):
        """Initialize chunker with configuration."""
        self.config = config or ChunkConfig()
        
        # Semantic unit patterns
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
        """
        Chunk a document intelligently based on semantic units.
        
        Args:
            text: Document text to chunk
            title: Document title (included for context)
            metadata: Additional metadata to include
            
        Returns:
            List of DocumentChunk objects
        """
        if not text or not text.strip():
            logger.warning(f"Empty document: {title}")
            return []
            
        # Clean and normalize text
        text = self._normalize_text(text)
        
        # Choose strategy based on content analysis
        strategy = self._determine_strategy(text)
        
        if strategy == ChunkingStrategy.SEMANTIC:
            chunks = self._semantic_chunking(text, title, metadata)
        elif strategy == ChunkingStrategy.HIERARCHICAL:
            chunks = self._hierarchical_chunking(text, title, metadata)
        else:
            chunks = self._sliding_window_chunking(text, title, metadata)
            
        # Filter by quality
        quality_chunks = [
            chunk for chunk in chunks 
            if chunk.quality_score >= self.config.quality_threshold
        ]
        
        # Reindex after filtering
        for i, chunk in enumerate(quality_chunks):
            chunk.chunk_index = i
            chunk.total_chunks = len(quality_chunks)
            
        logger.info(
            f"Document '{title}' chunked into {len(quality_chunks)} chunks "
            f"(filtered from {len(chunks)}, strategy={strategy.value})"
        )
        
        return quality_chunks
    
    def _determine_strategy(self, text: str) -> ChunkingStrategy:
        """Determine best chunking strategy based on document structure."""
        # Check for hierarchical structure (markdown headers, etc.)
        if self.section_pattern.findall(text):
            return ChunkingStrategy.HIERARCHICAL
            
        # Check for well-structured content (lists, paragraphs)
        paragraphs = self.paragraph_separator.split(text)
        if len(paragraphs) > 3:
            return ChunkingStrategy.SEMANTIC
            
        # Fallback to sliding window
        return ChunkingStrategy.SLIDING_WINDOW
    
    def _semantic_chunking(
        self, 
        text: str, 
        title: str,
        metadata: Optional[Dict[str, Any]]
    ) -> List[DocumentChunk]:
        """
        Chunk based on semantic units (paragraphs, lists, etc.).
        
        This is the RECOMMENDED approach for knowledge base articles.
        """
        chunks = []
        
        # Split into semantic units
        units = self._extract_semantic_units(text)
        
        # Group units into chunks
        current_chunk = []
        current_size = 0
        start_char = 0
        
        for unit in units:
            unit_size = len(unit['text'])
            
            # Check if adding this unit would exceed max size
            if current_size + unit_size > self.config.max_chunk_size and current_chunk:
                # Create chunk from accumulated units
                chunk_text = self._build_chunk_text(current_chunk, title)
                chunks.append(self._create_chunk(
                    text=chunk_text,
                    chunk_index=len(chunks),
                    start_char=start_char,
                    end_char=start_char + len(chunk_text),
                    semantic_type='mixed',
                    metadata=metadata
                ))
                
                # Start new chunk with overlap
                if self.config.overlap_size > 0 and current_chunk:
                    # Keep last unit for overlap
                    current_chunk = [current_chunk[-1]]
                    current_size = len(current_chunk[0]['text'])
                else:
                    current_chunk = []
                    current_size = 0
                start_char = start_char + len(chunk_text) - current_size
            
            current_chunk.append(unit)
            current_size += unit_size
            
            # Force chunk if at minimum size and found good breaking point
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
        
        # Handle remaining units
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
        """
        Chunk based on document hierarchy (sections, subsections).
        
        Best for structured documents with clear sections.
        """
        chunks = []
        sections = self._extract_sections(text)
        
        for section in sections:
            section_text = section['content']
            section_title = section.get('title', '')
            
            # Include section context
            if section_title:
                context = f"{title} > {section_title}"
            else:
                context = title
            
            # If section is small enough, keep it as single chunk
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
                # Recursively chunk large sections
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
        """
        Fallback to sliding window with smart boundaries.
        
        Even in sliding window, we try to break at sentence boundaries.
        """
        chunks = []
        
        # Add title context if configured
        if self.config.include_title_context:
            title_prefix = f"[{title}]\n\n"
        else:
            title_prefix = ""
        
        text_length = len(text)
        start = 0
        
        while start < text_length:
            # Calculate end position
            end = min(start + self.config.max_chunk_size - len(title_prefix), text_length)
            
            # Try to find sentence boundary
            if end < text_length and self.config.preserve_sentences:
                # Look for sentence endings
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
            
            # Move start with overlap
            if end >= text_length:
                break
            start = max(start + 1, end - self.config.overlap_size)
        
        return chunks
    
    def _extract_semantic_units(self, text: str) -> List[Dict[str, Any]]:
        """Extract semantic units from text (paragraphs, lists, etc.)."""
        units = []
        
        # Split by paragraphs first
        paragraphs = self.paragraph_separator.split(text)
        
        for para in paragraphs:
            if not para.strip():
                continue
            
            # Check if it's a list
            if self.list_pattern.match(para) or self.numbered_list_pattern.match(para):
                # Keep list together as single unit
                units.append({
                    'text': para,
                    'type': 'list',
                    'breakable': False  # Don't break lists
                })
            # Check if it's a code block
            elif para.strip().startswith('```'):
                units.append({
                    'text': para,
                    'type': 'code',
                    'breakable': False
                })
            # Check if it's a procedure (numbered steps)
            elif self.numbered_list_pattern.match(para):
                units.append({
                    'text': para,
                    'type': 'procedure',
                    'breakable': False
                })
            else:
                # Regular paragraph - can be broken if needed
                units.append({
                    'text': para,
                    'type': 'paragraph',
                    'breakable': True
                })
        
        return units
    
    def _extract_sections(self, text: str) -> List[Dict[str, Any]]:
        """Extract sections based on headers or other markers."""
        sections = []
        
        # Find all section headers
        matches = list(self.section_pattern.finditer(text))
        
        if not matches:
            # No sections found, treat entire text as one section
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
            
            # Determine section end (start of next section or end of text)
            if i + 1 < len(matches):
                section_end = matches[i + 1].start()
            else:
                section_end = len(text)
            
            # Extract section content (excluding the header)
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
        """Determine section level from header."""
        # Count # symbols for markdown headers
        level = len(re.match(r'^#+', header).group()) if header.startswith('#') else 1
        return level
    
    def _build_chunk_text(self, units: List[Dict[str, Any]], title: str) -> str:
        """Build chunk text from semantic units."""
        texts = [unit['text'] for unit in units]
        content = '\n\n'.join(texts)
        
        if self.config.include_title_context:
            return f"[{title}]\n\n{content}"
        return content
    
    def _add_context(self, text: str, context: str) -> str:
        """Add contextual information to chunk."""
        if self.config.include_title_context:
            return f"[{context}]\n\n{text}"
        return text
    
    def _determine_chunk_type(self, units: List[Dict[str, Any]]) -> str:
        """Determine the primary type of a chunk based on its units."""
        types = [unit['type'] for unit in units]
        
        # Priority order
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
        """Create a DocumentChunk with quality assessment."""
        quality_score = self._assess_chunk_quality(text, semantic_type)
        
        return DocumentChunk(
            text=text,
            chunk_index=chunk_index,
            total_chunks=0,  # Will be updated later
            start_char=start_char,
            end_char=end_char,
            quality_score=quality_score,
            metadata=metadata or {},
            parent_section=parent_section,
            semantic_type=semantic_type
        )
    
    def _assess_chunk_quality(self, text: str, semantic_type: str) -> float:
        """
        Assess the quality of a chunk (0-1).
        
        Quality factors:
        - Length (too short = low quality)
        - Content density (too many special chars = low quality)
        - Semantic completeness (broken sentences = low quality)
        - Type bonus (procedures and lists get quality bonus)
        """
        if not text or len(text) < 50:
            return 0.0
        
        score = 0.5  # Base score
        
        # Length factor
        if len(text) >= self.config.min_chunk_size:
            score += 0.2
        elif len(text) >= 200:
            score += 0.1
        
        # Content density (ratio of alphanumeric chars)
        alpha_ratio = sum(c.isalnum() or c.isspace() for c in text) / len(text)
        if alpha_ratio > 0.7:
            score += 0.2
        elif alpha_ratio > 0.5:
            score += 0.1
        
        # Semantic type bonus
        if semantic_type in ['procedure', 'list', 'section']:
            score += 0.2
        elif semantic_type == 'paragraph':
            score += 0.1
        
        # Check for sentence completeness
        if text.rstrip().endswith(('.', '!', '?', ':', ';')):
            score += 0.1
        
        return min(1.0, max(0.0, score))
    
    def _normalize_text(self, text: str) -> str:
        """Normalize text for processing."""
        # Remove excessive whitespace
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        
        # Fix common encoding issues
        text = text.replace('\r\n', '\n')
        text = text.replace('\r', '\n')
        
        return text.strip()