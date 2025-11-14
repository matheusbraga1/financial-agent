from typing import List, Dict, Any, Optional, Tuple
import re
import logging

logger = logging.getLogger(__name__)

class DocumentProcessor:
    def __init__(
        self,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        min_chunk_size: int = 100,
    ):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
    
    def process(
        self,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        if not content or len(content.strip()) < self.min_chunk_size:
            logger.warning(f"Documento '{title}' ignorado: conteúdo muito curto")
            return []
        
        chunks = self._intelligent_chunk(content)
        
        processed_chunks: List[Dict[str, Any]] = []
        
        for i, chunk_text in enumerate(chunks):
            if len(chunk_text.strip()) < self.min_chunk_size:
                continue
            
            chunk_title = title
            if len(chunks) > 1:
                chunk_title = f"{title} (Parte {i+1}/{len(chunks)})"
            
            chunk_metadata = dict(metadata or {})
            chunk_metadata.update({
                "chunk_index": i,
                "total_chunks": len(chunks),
                "is_chunked": len(chunks) > 1,
            })
            
            processed_chunks.append({
                "title": chunk_title,
                "content": chunk_text,
                "metadata": chunk_metadata,
            })
        
        logger.info(
            f"Documento '{title}' processado: {len(processed_chunks)} chunks"
        )
        
        return processed_chunks
    
    def _intelligent_chunk(self, content: str) -> List[str]:
        if len(content) <= self.chunk_size:
            return [content]
        
        chunks: List[str] = []
        
        if "##" in content:
            sections = re.split(r'(^|\n)(#{1,6}\s+)', content)
            current_chunk = ""
            
            for i in range(0, len(sections), 3):
                section = "".join(sections[i:i+3])
                
                if len(current_chunk) + len(section) <= self.chunk_size:
                    current_chunk += section
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    current_chunk = section
            
            if current_chunk:
                chunks.append(current_chunk.strip())
        
        else:
            paragraphs = content.split("\n\n")
            current_chunk = ""
            
            for para in paragraphs:
                if len(current_chunk) + len(para) <= self.chunk_size:
                    current_chunk += para + "\n\n"
                else:
                    if current_chunk:
                        chunks.append(current_chunk.strip())
                    
                    if len(para) > self.chunk_size:
                        sentences = self._split_sentences(para)
                        sentence_chunk = ""
                        
                        for sent in sentences:
                            if len(sentence_chunk) + len(sent) <= self.chunk_size:
                                sentence_chunk += sent + " "
                            else:
                                if sentence_chunk:
                                    chunks.append(sentence_chunk.strip())
                                sentence_chunk = sent + " "
                        
                        current_chunk = sentence_chunk
                    else:
                        current_chunk = para + "\n\n"
            
            if current_chunk:
                chunks.append(current_chunk.strip())
        
        if len(chunks) > 1:
            chunks = self._apply_overlap(chunks)
        
        return chunks
    
    def _split_sentences(self, text: str) -> List[str]:
        sentences = re.split(r'(?<=[.!?])\s+', text)
        return [s.strip() for s in sentences if s.strip()]
    
    def _apply_overlap(self, chunks: List[str]) -> List[str]:
        if not chunks or self.chunk_overlap <= 0:
            return chunks
        
        overlapped: List[str] = [chunks[0]]
        
        for i in range(1, len(chunks)):
            prev_chunk = chunks[i-1]
            current_chunk = chunks[i]
            
            prev_words = prev_chunk.split()
            overlap_words = prev_words[-self.chunk_overlap//5:]
            overlap_text = " ".join(overlap_words)
            
            overlapped_chunk = overlap_text + " " + current_chunk
            overlapped.append(overlapped_chunk)
        
        return overlapped