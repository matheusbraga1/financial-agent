from app.services.rag_service import rag_service
from app.services.vector_store_service import vector_store_service
from app.services.embedding_service import embedding_service


def get_rag_service():
    yield rag_service


def get_vector_store():
    yield vector_store_service


def get_embedding_service():
    yield embedding_service