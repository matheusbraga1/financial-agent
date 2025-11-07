from fastapi import APIRouter, Depends, HTTPException, status
from typing import Dict, Any
import logging
from datetime import datetime

from app.models.document import DocumentCreate, DocumentResponse
from app.models.error import ErrorResponse
from app.services.vector_store_service import VectorStoreService
from app.services.embedding_service import EmbeddingService
from app.api.deps import get_vector_store, get_embedding_service
from app.api.security import get_current_user


router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adicionar novo documento",
    description="Adiciona um novo artigo à base de conhecimento (requer admin)",
    responses={
        201: {"description": "Documento criado"},
        400: {"description": "Dados inválidos", "model": ErrorResponse},
        401: {"description": "Não autorizado", "model": ErrorResponse},
        403: {"description": "Proibido", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
)
async def create_document(
    document: DocumentCreate,
    vector_store: VectorStoreService = Depends(get_vector_store),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    current_user = Depends(get_current_user),
) -> DocumentResponse:
    import asyncio

    try:
        if not bool(current_user.get("is_admin")):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Apenas administradores podem criar documentos",
            )

        logger.info(f"Criando documento: {document.title}")
        loop = asyncio.get_running_loop()

        # Gerar embedding em thread pool (CPU-bound)
        vector = await loop.run_in_executor(
            None, embedding_service.encode_document, document.title, document.content
        )

        # Adicionar documento ao Qdrant em thread pool
        doc_id = await loop.run_in_executor(
            None, vector_store.add_document, document, vector
        )

        return DocumentResponse(
            id=doc_id,
            title=document.title,
            category=document.category,
            created_at=datetime.now(),
            indexed=True,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao criar documento: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar documento",
        )


@router.get(
    "/info",
    response_model=Dict[str, Any],
    summary="Informações da base de conhecimento",
    description="Retorna estatísticas públicas sobre os documentos indexados (total, categorias, etc.)",
    responses={
        200: {"description": "Estatísticas da base de conhecimento"},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse},
    },
)
async def get_documents_info(
    vector_store: VectorStoreService = Depends(get_vector_store),
) -> Dict[str, Any]:
    import asyncio

    try:
        loop = asyncio.get_running_loop()
        # Buscar info em thread pool (I/O bound - Qdrant)
        info = await loop.run_in_executor(
            None, vector_store.get_collection_info
        )
        return info
    except Exception as e:
        logger.error(f"Erro ao buscar info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar informações",
        )

