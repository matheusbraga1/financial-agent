from typing import Dict, Any, List, Optional
import uuid
import logging

logger = logging.getLogger(__name__)

class IngestDocumentUseCase:
    def __init__(
        self,
        document_processor,
        embeddings_port,
        vector_store_port,
    ):
        self.processor = document_processor
        self.embeddings = embeddings_port
        self.vector_store = vector_store_port
    
    def execute(
        self,
        title: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        logger.info(f"Iniciando ingestão de documento: '{title}'")
        
        if not title or not title.strip():
            raise ValueError("Título não pode estar vazio")
        
        if not content or not content.strip():
            raise ValueError("Conteúdo não pode estar vazio")
        
        chunks = self.processor.process(
            title=title,
            content=content,
            metadata=metadata,
        )
        
        if not chunks:
            logger.warning(f"Documento '{title}' não gerou chunks válidos")
            return {
                "success": False,
                "message": "Documento muito curto ou inválido",
                "chunks_processed": 0,
            }
        
        logger.info(f"Documento processado em {len(chunks)} chunks")
        
        stored_ids: List[str] = []
        failed_chunks = 0
        
        for i, chunk in enumerate(chunks):
            try:
                vector = self.embeddings.encode_document(
                    title=chunk["title"],
                    content=chunk["content"],
                )
                
                doc_id = str(uuid.uuid4())
                
                full_metadata = {
                    "title": chunk["title"],
                    "content": chunk["content"],
                    "category": metadata.get("category", "Documento") if metadata else "Documento",
                    "metadata": chunk["metadata"],
                }
                
                self.vector_store.upsert(
                    id=doc_id,
                    vector=vector,
                    metadata=full_metadata,
                )
                
                stored_ids.append(doc_id)
                
                logger.debug(f"Chunk {i+1}/{len(chunks)} armazenado: {doc_id}")
                
            except Exception as e:
                logger.error(f"Erro ao armazenar chunk {i+1}: {e}")
                failed_chunks += 1
        
        success = len(stored_ids) > 0
        
        logger.info(
            f"Ingestão concluída: {len(stored_ids)} chunks armazenados, "
            f"{failed_chunks} falhas"
        )
        
        return {
            "success": success,
            "message": f"Documento '{title}' ingerido com sucesso",
            "chunks_processed": len(stored_ids),
            "chunks_failed": failed_chunks,
            "document_ids": stored_ids,
        }
    
    def execute_batch(
        self,
        documents: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        logger.info(f"Iniciando ingestão em lote: {len(documents)} documentos")
        
        total_chunks = 0
        total_failed = 0
        successful_docs = 0
        failed_docs = 0
        
        for i, doc in enumerate(documents):
            try:
                result = self.execute(
                    title=doc.get("title", f"Documento {i+1}"),
                    content=doc.get("content", ""),
                    metadata=doc.get("metadata"),
                )
                
                if result["success"]:
                    successful_docs += 1
                    total_chunks += result["chunks_processed"]
                else:
                    failed_docs += 1
                
                total_failed += result.get("chunks_failed", 0)
                
            except Exception as e:
                logger.error(f"Erro ao processar documento {i+1}: {e}")
                failed_docs += 1
        
        logger.info(
            f"Ingestão em lote concluída: {successful_docs} docs OK, "
            f"{failed_docs} docs com erro, {total_chunks} chunks armazenados"
        )
        
        return {
            "success": successful_docs > 0,
            "total_documents": len(documents),
            "successful_documents": successful_docs,
            "failed_documents": failed_docs,
            "total_chunks": total_chunks,
            "failed_chunks": total_failed,
        }