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
        500: {"description": "Erro interno do servidor", "model": ErrorResponse}
    }
)
async def create_document(
        document: DocumentCreate,
        vector_store: VectorStoreService = Depends(get_vector_store),
        embedding_service: EmbeddingService = Depends(get_embedding_service),
        current_user = Depends(get_current_user)
) -> DocumentResponse:
    try:
        if not bool(current_user.get('is_admin')):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Apenas administradores podem criar documentos")

        logger.info(f"Criando documento: {document.title}")

        vector = embedding_service.encode_document(
            title=document.title,
            content=document.content
        )

        doc_id = vector_store.add_document(
            document=document,
            vector=vector
        )

        return DocumentResponse(
            id=doc_id,
            title=document.title,
            category=document.category,
            created_at=datetime.now(),
            indexed=True
        )

    except Exception as e:
        logger.error(f"Erro ao criar documento: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao criar documento"
        )


@router.get(
    "/info",
    response_model=Dict[str, Any],
    summary="Informações da base de conhecimento",
    description="Retorna estatísticas sobre os documentos indexados (requer login)",
    responses={
        200: {"description": "Estatísticas"},
        401: {"description": "Não autorizado", "model": ErrorResponse},
        500: {"description": "Erro interno do servidor", "model": ErrorResponse}
    }
)
async def get_documents_info(
        vector_store: VectorStoreService = Depends(get_vector_store),
        current_user = Depends(get_current_user)
) -> Dict[str, Any]:
    try:
        info = vector_store.get_collection_info()
        return info
    except Exception as e:
        logger.error(f"Erro ao buscar info: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Erro ao buscar informações"
        )

