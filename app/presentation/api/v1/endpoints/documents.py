import logging
import os
from pathlib import Path
from typing import Dict, Any, List

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    status,
    UploadFile,
    File,
    Form,
)

from app.presentation.api.dependencies import (
    get_ingest_document_use_case,
    get_current_admin_user,
    get_vector_store,
)
from app.application.use_cases.documents.ingest_document_use_case import IngestDocumentUseCase
from app.infrastructure.adapters.vector_store.qdrant_adapter import QdrantAdapter

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_FILE_SIZE = 50 * 1024 * 1024
ALLOWED_EXTENSIONS = {".txt", ".md", ".pdf", ".docx"}
MAX_FILENAME_LENGTH = 255


def sanitize_filename(filename: str) -> str:
    if not filename:
        return "unnamed_file"

    safe_name = os.path.basename(filename)

    safe_name = "".join(c for c in safe_name if c.isalnum() or c in "._- ")
    safe_name = safe_name.strip()

    if safe_name.startswith('.'):
        safe_name = 'file' + safe_name

    if len(safe_name) > MAX_FILENAME_LENGTH:
        name_part, ext_part = os.path.splitext(safe_name)
        safe_name = name_part[:MAX_FILENAME_LENGTH - len(ext_part)] + ext_part

    if not safe_name or safe_name == '.':
        safe_name = "unnamed_file"

    return safe_name


def validate_file_extension(filename: str) -> str:
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome de arquivo não fornecido"
        )

    file_path = Path(filename)
    file_ext = file_path.suffix.lower()

    if not file_ext:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Arquivo sem extensão. Extensões permitidas: " + ", ".join(ALLOWED_EXTENSIONS)
        )

    if file_ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tipo de arquivo não suportado: {file_ext}. Permitidos: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    return file_ext


async def validate_file_size(file: UploadFile) -> bytes:
    content_chunks = []
    total_size = 0

    chunk_size = 1024 * 1024

    while True:
        chunk = await file.read(chunk_size)
        if not chunk:
            break

        total_size += len(chunk)

        if total_size > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"Arquivo muito grande. Tamanho máximo: {MAX_FILE_SIZE // (1024*1024)}MB"
            )

        content_chunks.append(chunk)

    return b''.join(content_chunks)


@router.post(
    "/ingest",
    status_code=status.HTTP_201_CREATED,
    summary="Ingerir documento no vector store",
    description="Processa e armazena documento para busca (requer admin)",
    responses={
        201: {"description": "Documento ingerido com sucesso"},
        400: {"description": "Dados inválidos"},
        401: {"description": "Não autenticado"},
        403: {"description": "Sem permissão (requer admin)"},
    },
)
async def ingest_document(
    title: str = Form(..., min_length=3, max_length=500),
    content: str = Form(..., min_length=50),
    category: str = Form("Documento", max_length=100),
    department: str = Form(None, max_length=50),
    tags: str = Form(None, description="Tags separadas por vírgula"),
    ingest_uc: IngestDocumentUseCase = Depends(get_ingest_document_use_case),
    current_admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    try:
        logger.info(
            f"Ingestão de documento: title='{title[:50]}...', "
            f"content_length={len(content)}, "
            f"admin_user={current_admin['username']}"
        )
        
        if len(content.strip()) < 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Conteúdo muito curto (mínimo 50 caracteres)",
            )
        
        metadata = {
            "category": category,
            "origin": "manual_upload",
            "uploaded_by": current_admin["username"],
        }
        
        if department:
            metadata["department"] = department
        
        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
            if tags_list:
                metadata["tags"] = tags_list
        
        result = ingest_uc.execute(
            title=title,
            content=content,
            metadata=metadata,
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Falha ao ingerir documento"),
            )
        
        logger.info(
            f"Documento ingerido: {result['chunks_processed']} chunks, "
            f"title='{title[:50]}...'"
        )
        
        return {
            "message": result["message"],
            "chunks_processed": result["chunks_processed"],
            "chunks_failed": result.get("chunks_failed", 0),
            "document_ids": result.get("document_ids", []),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao ingerir documento: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar documento",
        )

@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
    summary="Upload de arquivo de documento",
    description="Faz upload e ingere arquivo (txt, md, pdf) (requer admin)",
    responses={
        201: {"description": "Arquivo processado com sucesso"},
        400: {"description": "Arquivo inválido"},
        401: {"description": "Não autenticado"},
        403: {"description": "Sem permissão"},
    },
)
async def upload_file(
    file: UploadFile = File(...),
    category: str = Form("Documento"),
    department: str = Form(None),
    tags: str = Form(None),
    ingest_uc: IngestDocumentUseCase = Depends(get_ingest_document_use_case),
    current_admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    try:
        safe_filename = sanitize_filename(file.filename or "")

        logger.info(
            f"Upload de arquivo: filename={safe_filename}, "
            f"content_type={file.content_type}, "
            f"admin_user={current_admin['username']}"
        )

        file_ext = validate_file_extension(safe_filename)

        content_bytes = await validate_file_size(file)
        
        if file_ext in {".txt", ".md"}:
            try:
                content = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                try:
                    content = content_bytes.decode("latin-1")
                except Exception:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Erro ao decodificar arquivo. Use UTF-8 ou Latin-1.",
                    )
        
        elif file_ext == ".pdf":
            try:
                import PyPDF2
                from io import BytesIO
                
                pdf_file = BytesIO(content_bytes)
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                
                text_parts = []
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    except Exception as e:
                        logger.warning(f"Erro ao extrair página {page_num}: {e}")
                
                content = "\n\n".join(text_parts)
                
                if not content.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="PDF não contém texto extraível",
                    )
                
            except ImportError:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="PyPDF2 não está instalado. Instale com: pip install PyPDF2",
                )
            except Exception as e:
                logger.error(f"Erro ao processar PDF: {e}", exc_info=True)
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Erro ao processar PDF: {str(e)}",
                )
        
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tipo de arquivo não suportado",
            )
        
        if len(content.strip()) < 50:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Arquivo contém pouco texto (mínimo 50 caracteres)",
            )
        
        metadata = {
            "category": category,
            "origin": "file_upload",
            "uploaded_by": current_admin["username"],
            "original_filename": safe_filename,
            "file_type": file_ext,
        }

        if department:
            metadata["department"] = department

        if tags:
            tags_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
            if tags_list:
                metadata["tags"] = tags_list

        title = Path(safe_filename).stem if safe_filename else "Documento sem título"
        
        result = ingest_uc.execute(
            title=title,
            content=content,
            metadata=metadata,
        )
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result.get("message", "Falha ao processar arquivo"),
            )
        
        logger.info(
            f"Arquivo processado: {result['chunks_processed']} chunks, "
            f"filename={safe_filename}"
        )

        return {
            "message": result["message"],
            "filename": safe_filename,
            "chunks_processed": result["chunks_processed"],
            "chunks_failed": result.get("chunks_failed", 0),
            "document_ids": result.get("document_ids", []),
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao fazer upload: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao processar arquivo",
        )

@router.get(
    "/stats",
    summary="Estatísticas da coleção",
    description="Retorna informações sobre a coleção de documentos",
    responses={
        200: {"description": "Estatísticas da coleção"},
        401: {"description": "Não autenticado"},
    },
)
async def get_collection_stats(
    vector_store: QdrantAdapter = Depends(get_vector_store),
    current_admin: Dict[str, Any] = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    try:
        logger.info(f"Consultando stats por admin_user={current_admin['username']}")
        
        stats = vector_store.get_stats()
        
        return {
            "collection": stats.get("name", "unknown"),
            "total_documents": stats.get("vectors_count", 0),
            "indexed_documents": stats.get("indexed_vectors_count", 0),
            "status": stats.get("status", "unknown"),
        }
        
    except Exception as e:
        logger.error(f"Erro ao obter stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao obter estatísticas",
        )

@router.get(
    "/health",
    summary="Verificar saúde do serviço de documentos",
)
async def health_check() -> Dict[str, str]:
    return {"status": "healthy", "service": "documents"}