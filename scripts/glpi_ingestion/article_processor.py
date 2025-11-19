import logging
import uuid
from typing import Dict, Any, List, Optional
from dataclasses import asdict

from app.domain.document_chunking.intelligent_chunker import IntelligentChunker, DocumentChunk
from app.domain.documents.metadata_schema import DocumentMetadata, ChunkMetadata, Department, DocType
from app.domain.services.rag.domain_classifier import DomainClassifier
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter
from app.infrastructure.adapters.embeddings.sentence_transformer_adapter import SentenceTransformerAdapter
from app.models.document import DocumentCreate

from .content_cleaner import ContentCleaner

logger = logging.getLogger(__name__)


class ArticleProcessor:

    def __init__(
        self,
        content_cleaner: ContentCleaner,
        chunker: IntelligentChunker,
        classifier: DomainClassifier,
        embedding_service: SentenceTransformerAdapter,
        vector_store: QdrantAdapter,
        embedding_dimension: int
    ):
        self.content_cleaner = content_cleaner
        self.chunker = chunker
        self.classifier = classifier
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.embedding_dimension = embedding_dimension

    def process_article(
        self,
        article: Dict[str, Any],
        dry_run: bool = False
    ) -> tuple[bool, int, List[int]]:
        title = article.get("title", "Sem título")
        content_raw = article.get("content", "")

        content_clean = self.content_cleaner.clean(content_raw, title)

        if not self.content_cleaner.is_valid_content(content_clean):
            logger.warning(f"Article '{title}' too short after cleaning, skipping")
            return False, 0, []

        metadata = self._classify_and_build_metadata(
            article=article,
            content=content_clean
        )

        chunks = self.chunker.chunk_document(
            text=content_clean,
            title=title,
            metadata=asdict(metadata)
        )

        if not chunks:
            logger.warning(f"No valid chunks created for '{title}'")
            return False, 0, []

        chunk_sizes = [len(chunk.text) for chunk in chunks]

        if not dry_run:
            indexed_count = self._index_chunks(chunks, title, metadata)
            if indexed_count == 0:
                return False, len(chunks), chunk_sizes

        return True, len(chunks), chunk_sizes

    def _classify_and_build_metadata(
        self,
        article: Dict[str, Any],
        content: str
    ) -> DocumentMetadata:
        title = article.get("title", "")
        category = article.get("category", "Geral")
        glpi_meta = article.get("metadata", {})

        sample_text = f"{title} {category} {content[:1000]}"
        department_strings = self.classifier.classify(sample_text)
        departments = self._convert_to_department_enums(department_strings)

        if not departments:
            departments = [Department.GERAL]

        doc_type = DocType.FAQ if glpi_meta.get("is_faq") else DocType.ARTICLE

        tags = self._extract_tags(title, content, category)
        keywords = self._extract_keywords(title, content)

        metadata = DocumentMetadata(
            source_id=f"glpi_{article['id']}",
            title=title,
            department=departments[0],
            doc_type=doc_type,
            category=category,
            tags=tags,
            file_format="html",
            created_at=glpi_meta.get("date_creation"),
            updated_at=glpi_meta.get("date_mod"),
            author=glpi_meta.get("author") or "GLPI",
            version="1.0",
            glpi_id=int(article['id']),
            is_public=glpi_meta.get("visibility") == "public",
            language="pt-BR",
            keywords=keywords,
            summary=self._generate_summary(content),
            departments=departments
        )

        logger.debug(
            f"Classified: {title[:50]}... -> Dept={departments[0].value}, "
            f"Type={doc_type.value}, Tags={len(tags)}"
        )

        return metadata

    def _convert_to_department_enums(
        self,
        department_strings: List[str]
    ) -> List[Department]:
        departments = []

        mapping = {
            "TI": Department.TI,
            "RH": Department.RH,
            "Financeiro": Department.FINANCEIRO,
            "FINANCEIRO": Department.FINANCEIRO,
            "Loteamento": Department.LOTEAMENTO,
            "LOTEAMENTO": Department.LOTEAMENTO,
            "Geral": Department.GERAL
        }

        for dept_str in department_strings:
            if dept_str in mapping:
                departments.append(mapping[dept_str])

        return departments

    def _extract_tags(self, title: str, content: str, category: str) -> List[str]:
        tags = set()

        if category:
            parts = [p.strip() for p in category.split(">")]
            tags.update(p for p in parts if p and p != "Geral")

        stopwords = {"para", "como", "fazer", "sobre", "quando", "onde"}
        title_words = [
            w.lower() for w in title.split()
            if len(w) >= 4 and w.lower() not in stopwords
        ]
        tags.update(title_words[:5])

        tech_terms = self._extract_technical_terms(content)
        tags.update(tech_terms[:5])

        return list(tags)[:15]

    def _extract_keywords(self, title: str, content: str) -> List[str]:
        words = (title + " " + content[:500]).lower().split()

        freq = {}
        for word in words:
            if len(word) >= 4 and word.isalpha():
                freq[word] = freq.get(word, 0) + 1

        keywords = sorted(freq.items(), key=lambda x: x[1], reverse=True)
        return [kw[0] for kw in keywords[:10]]

    def _extract_technical_terms(self, content: str) -> List[str]:
        import re

        patterns = [
            r'\b[A-Z]{2,}\b',
            r'\b[A-Z][a-z]+[A-Z][a-z]+\b',
            r'\b\w+[@.]\w+\b',
        ]

        terms = set()
        for pattern in patterns:
            matches = re.findall(pattern, content)
            terms.update(m.lower() for m in matches[:5])

        return list(terms)

    def _generate_summary(self, content: str, max_length: int = 200) -> str:
        if not content:
            return ""

        paragraphs = content.split('\n\n')
        if paragraphs:
            summary = paragraphs[0][:max_length]
            if len(summary) == max_length:
                summary = summary.rsplit(' ', 1)[0] + "..."
            return summary

        return content[:max_length]

    def _index_chunks(
        self,
        chunks: List[DocumentChunk],
        title: str,
        metadata: DocumentMetadata
    ) -> int:
        indexed_count = 0

        for chunk in chunks:
            try:
                chunk_metadata = ChunkMetadata.from_document_metadata(
                    doc_metadata=metadata,
                    chunk_index=chunk.chunk_index,
                    total_chunks=chunk.total_chunks,
                    text=chunk.text
                )

                metadata_dict = chunk_metadata.model_dump()
                metadata_dict.update({
                    "quality_score": chunk.quality_score,
                    "semantic_type": chunk.semantic_type,
                    "parent_section": chunk.parent_section,
                    "chunk_size": len(chunk.text),
                })

                embedding = self.embedding_service.encode_text(chunk.text)

                if len(embedding) != self.embedding_dimension:
                    logger.error(
                        f"Embedding dimension mismatch: got {len(embedding)}, "
                        f"expected {self.embedding_dimension}"
                    )
                    continue

                payload = self._build_payload(title, chunk.text, metadata, metadata_dict)

                doc_id = str(uuid.uuid4())
                self.vector_store.upsert_point(
                    point_id=doc_id,
                    vector=embedding,
                    payload=payload
                )

                indexed_count += 1

                logger.debug(
                    f"Chunk {chunk.chunk_index + 1}/{chunk.total_chunks} indexed: "
                    f"size={len(chunk.text)}, quality={chunk.quality_score:.2f}"
                )

            except Exception as e:
                logger.error(f"Failed to index chunk {chunk.chunk_index}: {e}")
                continue

        return indexed_count

    def _build_payload(
        self,
        title: str,
        content: str,
        metadata: DocumentMetadata,
        metadata_dict: Dict[str, Any]
    ) -> Dict[str, Any]:
        search_text = f"{title} {title} {title} {content}"

        payload = {
            "title": title,
            "category": metadata.category or "Geral",
            "content": content,
            "search_text": search_text,
            "metadata": metadata_dict,
            "department": metadata.department.value,
            "departments": [d.value for d in (metadata.departments or [])],
            "doc_type": metadata.doc_type.value,
            "tags": metadata.tags,
        }

        return self._sanitize_payload(payload)

    def _sanitize_payload(self, payload: Any) -> Any:
        """Recursively sanitize payload for JSON safety, preserving UTF-8 characters."""
        import unicodedata

        if payload is None:
            return None

        if isinstance(payload, str):
            # Normalize Unicode to NFC to ensure consistent character representation
            payload = unicodedata.normalize('NFC', payload)

            # Strings from MySQL with utf8mb4 charset are already properly encoded
            # No need to re-encode, just return the normalized string
            return payload

        elif isinstance(payload, dict):
            return {key: self._sanitize_payload(val) for key, val in payload.items()}

        elif isinstance(payload, (list, tuple)):
            return [self._sanitize_payload(item) for item in payload]

        elif isinstance(payload, (int, float, bool)):
            return payload

        else:
            # Convert other types to string and sanitize
            return self._sanitize_payload(str(payload))


def create_article_processor(
    content_cleaner: ContentCleaner,
    chunker: IntelligentChunker,
    classifier: DomainClassifier,
    embedding_service: SentenceTransformerAdapter,
    vector_store: QdrantAdapter,
    embedding_dimension: int
) -> ArticleProcessor:
    """
    Factory function to create an ArticleProcessor.

    Args:
        content_cleaner: Content cleaning service
        chunker: Intelligent chunking service
        classifier: Domain classification service
        embedding_service: Embedding generation service
        vector_store: Vector storage service
        embedding_dimension: Expected embedding dimension

    Returns:
        Configured ArticleProcessor instance
    """
    return ArticleProcessor(
        content_cleaner=content_cleaner,
        chunker=chunker,
        classifier=classifier,
        embedding_service=embedding_service,
        vector_store=vector_store,
        embedding_dimension=embedding_dimension
    )
