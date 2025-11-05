from fastapi import APIRouter, Depends, HTTPException, status, Query
from typing import Dict, Any
import logging

from app.models.document import DocumentCreate, DocumentResponse
from app.services.vector_store_service import VectorStoreService
from app.services.embedding_service import EmbeddingService
from app.api.deps import get_vector_store, get_embedding_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Adicionar novo documento",
    description="Adiciona um novo artigo à base de conhecimento"
)
async def create_document(
        document: DocumentCreate,
        vector_store: VectorStoreService = Depends(get_vector_store),
        embedding_service: EmbeddingService = Depends(get_embedding_service)
) -> DocumentResponse:
    try:
        logger.info(f"Criando documento: {document.title}")

        # Gerar embedding do conteúdo
        vector = embedding_service.encode_document(
            title=document.title,
            content=document.content
        )

        # Adicionar ao vector store
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
    "/documents/info",
    response_model=Dict[str, Any],
    summary="Informações da base de conhecimento",
    description="Retorna estatísticas sobre os documentos indexados"
)
async def get_documents_info(
        vector_store: VectorStoreService = Depends(get_vector_store)
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

from datetime import datetime