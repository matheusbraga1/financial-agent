#!/usr/bin/env python3
"""
Script para ingestão de documentos multi-formato (PDF, DOCX, TXT, HTML).

Organização esperada:
documents/
├── TI/
│   ├── policies/
│   │   └── politica_seguranca.pdf
│   └── manuals/
│       └── manual_vpn.docx
├── RH/
│   ├── policies/
│   │   └── codigo_conduta.pdf
│   └── procedures/
│       └── ferias.docx
├── Financeiro/
└── ...

Uso:
    python scripts/ingest_documents.py                          # Ingerir todos
    python scripts/ingest_documents.py --department TI          # Apenas TI
    python scripts/ingest_documents.py --clear                  # Limpar antes
    python scripts/ingest_documents.py --dry-run                # Apenas listar
"""

import argparse
import sys
from pathlib import Path
from typing import List, Dict, Any
import logging
import uuid

# Adicionar diretório raiz ao path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.domain.documents.metadata_schema import DocumentMetadata, Department, DocType
from app.domain.services.documents.document_processor import DocumentProcessor
from app.services.embedding_service import EmbeddingService
from app.services.vector_store_service import VectorStoreService
from app.infrastructure.config.settings import get_settings

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

settings = get_settings()


class DocumentIngester:
    """Gerenciador de ingestão de documentos multi-formato."""

    def __init__(
        self,
        documents_dir: Path,
        chunk_size: int = 500,
        chunk_overlap: int = 50
    ):
        """
        Args:
            documents_dir: Diretório raiz dos documentos
            chunk_size: Tamanho de cada chunk em caracteres
            chunk_overlap: Overlap entre chunks
        """
        self.documents_dir = documents_dir
        self.processor = DocumentProcessor(chunk_size, chunk_overlap)
        # Direct instantiation - Dependency Injection
        self.embedding_service = EmbeddingService()
        self.vector_store = VectorStoreService()
        self.stats = {
            "total_files": 0,
            "processed_files": 0,
            "failed_files": 0,
            "total_chunks": 0,
        }

    def detect_metadata_from_path(self, file_path: Path) -> DocumentMetadata:
        """
        Detecta metadados automaticamente baseado na estrutura de diretórios.

        Estrutura esperada: documents/{Department}/{DocType}/arquivo.ext
        Exemplo: documents/TI/policies/seguranca.pdf

        Args:
            file_path: Caminho do arquivo

        Returns:
            DocumentMetadata detectado
        """
        relative = file_path.relative_to(self.documents_dir)
        parts = relative.parts

        # Detectar departamento (primeiro nível)
        department = Department.GERAL
        if len(parts) > 0:
            dept_name = parts[0]
            try:
                department = Department(dept_name)
            except ValueError:
                logger.warning(
                    f"Departamento desconhecido: {dept_name}. Usando GERAL."
                )

        # Detectar tipo de documento (segundo nível)
        doc_type = DocType.ARTICLE
        if len(parts) > 1:
            type_name = parts[1]
            # Mapear nome de pasta para DocType
            type_mapping = {
                "policies": DocType.POLICY,
                "procedures": DocType.PROCEDURE,
                "contracts": DocType.CONTRACT,
                "manuals": DocType.MANUAL,
                "forms": DocType.FORM,
                "guides": DocType.GUIDE,
                "faq": DocType.FAQ,
                "articles": DocType.ARTICLE,
            }
            doc_type = type_mapping.get(type_name, DocType.ARTICLE)

        # Criar metadados
        metadata = DocumentMetadata(
            source_id=f"{department.value}_{file_path.stem}",
            title=file_path.stem.replace('_', ' ').title(),
            department=department,
            doc_type=doc_type,
            category=parts[1] if len(parts) > 1 else None,
            tags=[department.value, doc_type.value],
            file_format=file_path.suffix[1:],  # Remover o ponto
        )

        logger.debug(
            f"Metadados detectados: {file_path.name} → "
            f"{metadata.department}/{metadata.doc_type}"
        )

        return metadata

    def ingest_file(self, file_path: Path, dry_run: bool = False) -> int:
        """
        Ingere um arquivo único.

        Args:
            file_path: Caminho do arquivo
            dry_run: Se True, apenas simula sem inserir

        Returns:
            Número de chunks criados
        """
        logger.info(f"Processando: {file_path.relative_to(self.documents_dir)}")

        try:
            # Detectar metadados
            metadata = self.detect_metadata_from_path(file_path)

            # Processar documento
            chunks = self.processor.process_document(file_path, metadata)

            if not chunks:
                logger.warning(f"Nenhum chunk gerado para: {file_path.name}")
                return 0

            if dry_run:
                logger.info(
                    f"[DRY-RUN] {file_path.name}: "
                    f"{len(chunks)} chunks ({metadata.department})"
                )
                return len(chunks)

            # Indexar cada chunk
            for chunk_meta in chunks:
                # Gerar embedding
                embedding = self.embedding_service.encode_text(chunk_meta.text)

                # Criar ID único para o chunk (string para referência)
                chunk_id_str = f"{chunk_meta.source_id}_chunk_{chunk_meta.chunk_index}"

                # Gerar UUID determinístico a partir do string ID
                # Usar namespace UUID5 para garantir mesmos IDs em re-ingestões
                chunk_id = str(uuid.uuid5(uuid.NAMESPACE_DNS, chunk_id_str))

                # Preparar payload para Qdrant
                payload = {
                    "title": chunk_meta.title,
                    "content": chunk_meta.text,
                    "category": chunk_meta.category or "",
                    "search_text": f"{chunk_meta.title} {chunk_meta.title} {chunk_meta.text}",
                    "metadata": {},
                    # Campos novos para multi-domínio
                    "department": chunk_meta.department,
                    "doc_type": chunk_meta.doc_type,
                    "chunk_index": chunk_meta.chunk_index,
                    "total_chunks": chunk_meta.total_chunks,
                    "file_format": chunk_meta.file_format,
                    "source_id": chunk_meta.source_id,  # Manter ID original para referência
                }

                # Inserir no Qdrant
                from qdrant_client.models import PointStruct
                point = PointStruct(
                    id=chunk_id,
                    vector=embedding,
                    payload=payload
                )

                self.vector_store.client.upsert(
                    collection_name=self.vector_store.collection_name,
                    points=[point]
                )

            logger.info(
                f"✓ {file_path.name}: {len(chunks)} chunks indexados "
                f"({metadata.department}/{metadata.doc_type})"
            )

            return len(chunks)

        except Exception as e:
            logger.error(f"✗ Erro ao processar {file_path.name}: {e}")
            self.stats["failed_files"] += 1
            return 0

    def ingest_directory(
        self,
        department_filter: str | None = None,
        dry_run: bool = False
    ) -> None:
        """
        Ingere todos os documentos de um diretório.

        Args:
            department_filter: Se especificado, processa apenas esse departamento
            dry_run: Se True, apenas simula sem inserir
        """
        if not self.documents_dir.exists():
            logger.error(f"Diretório não existe: {self.documents_dir}")
            return

        # Formatos suportados
        supported_formats = ['.pdf', '.docx', '.txt', '.html', '.htm']

        # Encontrar todos os arquivos
        files: List[Path] = []
        for ext in supported_formats:
            pattern = f"**/*{ext}"
            files.extend(self.documents_dir.glob(pattern))

        if not files:
            logger.warning(f"Nenhum arquivo encontrado em: {self.documents_dir}")
            return

        # Filtrar por departamento se especificado
        if department_filter:
            files = [
                f for f in files
                if f.relative_to(self.documents_dir).parts[0] == department_filter
            ]
            logger.info(f"Filtrando por departamento: {department_filter}")

        self.stats["total_files"] = len(files)
        logger.info(f"Encontrados {len(files)} arquivos para processar")

        if dry_run:
            logger.info("=== MODO DRY-RUN (sem inserir no banco) ===")

        # Processar cada arquivo
        for file_path in files:
            chunks_created = self.ingest_file(file_path, dry_run=dry_run)

            if chunks_created > 0:
                self.stats["processed_files"] += 1
                self.stats["total_chunks"] += chunks_created

        # Resumo
        logger.info("\n" + "="*60)
        logger.info("RESUMO DA INGESTÃO")
        logger.info("="*60)
        logger.info(f"Total de arquivos encontrados: {self.stats['total_files']}")
        logger.info(f"Arquivos processados: {self.stats['processed_files']}")
        logger.info(f"Arquivos com erro: {self.stats['failed_files']}")
        logger.info(f"Total de chunks criados: {self.stats['total_chunks']}")

        if dry_run:
            logger.info("\n[DRY-RUN] Nenhum dado foi inserido no banco.")

    def clear_collection(self) -> None:
        """Limpa a coleção Qdrant (remove todos os pontos)."""
        try:
            self.vector_store.client.delete_collection(
                collection_name=self.vector_store.collection_name
            )
            logger.info(f"Coleção '{self.vector_store.collection_name}' removida")

            # Recriar coleção vazia
            self.vector_store._ensure_collection()
            logger.info("Coleção recriada vazia")

        except Exception as e:
            logger.error(f"Erro ao limpar coleção: {e}")


def main():
    """Função principal."""
    parser = argparse.ArgumentParser(
        description="Ingestão de documentos multi-formato para o Qdrant"
    )

    parser.add_argument(
        "--documents-dir",
        type=Path,
        default=Path(__file__).parent.parent / "documents",
        help="Diretório raiz dos documentos (padrão: ./documents)"
    )

    parser.add_argument(
        "--department",
        type=str,
        choices=["TI", "RH", "Financeiro", "Loteamento", "Aluguel", "Juridico", "Geral"],
        help="Processar apenas documentos de um departamento específico"
    )

    parser.add_argument(
        "--clear",
        action="store_true",
        help="Limpar coleção antes de ingerir"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Apenas simular (não inserir no banco)"
    )

    parser.add_argument(
        "--chunk-size",
        type=int,
        default=500,
        help="Tamanho de cada chunk em caracteres (padrão: 500)"
    )

    parser.add_argument(
        "--chunk-overlap",
        type=int,
        default=50,
        help="Overlap entre chunks (padrão: 50)"
    )

    args = parser.parse_args()

    # Criar ingester
    ingester = DocumentIngester(
        documents_dir=args.documents_dir,
        chunk_size=args.chunk_size,
        chunk_overlap=args.chunk_overlap
    )

    # Limpar se solicitado
    if args.clear:
        logger.info("Limpando coleção existente...")
        ingester.clear_collection()

    # Ingerir documentos
    ingester.ingest_directory(
        department_filter=args.department,
        dry_run=args.dry_run
    )


if __name__ == "__main__":
    main()
