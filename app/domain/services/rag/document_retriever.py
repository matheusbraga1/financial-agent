from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
import logging
import re

from app.utils.recency_boost import RecencyBoostCalculator
from app.utils.snippet_builder import SnippetBuilder

logger = logging.getLogger(__name__)

class DocumentRetriever:
    def __init__(
        self,
        embeddings_port,
        vector_store_port,
        reranker=None,
    ):
        self.embeddings = embeddings_port
        self.vector_store = vector_store_port
        self.reranker = reranker
        
        logger.info(
            f"DocumentRetriever inicializado "
            f"(reranker: {'enabled' if reranker else 'disabled'})"
        )
    
    def retrieve(
        self,
        query: str,
        top_k: int = 15,
        min_score: float = 0.15,
        departments: Optional[List[str]] = None,
    ) -> List[Dict[str, Any]]:
        try:
            query_vector = self.embeddings.encode_text(query)
            
            filter_dict = None
            if departments:
                filter_dict = {"departments": departments}
            
            initial_top_k = max(top_k * 3, 30)
            
            documents = self.vector_store.search_hybrid(
                query_text=query,
                query_vector=query_vector,
                limit=initial_top_k,
                score_threshold=min_score,
                filter=filter_dict,
            )
            
            logger.info(f"Busca inicial: {len(documents)} documentos")
            
            if not documents:
                return []
            
            if len(documents) > 1:
                documents = self.apply_recency_boost(documents)
            
            if len(documents) > 1:
                from app.domain.services.rag.diversification import apply_mmr_diversification
                
                logger.debug("Aplicando MMR diversification...")
                documents = apply_mmr_diversification(
                    documents=documents,
                    lambda_param=0.7,
                    max_results=max(top_k * 2, 20),
                )
                logger.info(f"Após MMR: {len(documents)} documentos")
            
            if self.reranker and len(documents) > 1:
                logger.debug("Aplicando CrossEncoder reranking...")
                documents = self.reranker.rerank(
                    query=query,
                    documents=documents,
                    top_k=top_k,
                    original_weight=0.3,
                    rerank_weight=0.7,
                )
                logger.info(f"Após reranking: {len(documents)} documentos")
            else:
                documents = documents[:top_k]
            
            if documents:
                logger.info(f"Top 3 documentos finais:")
                for i, doc in enumerate(documents[:3]):
                    logger.info(
                        f"  {i+1}. '{doc.get('title', '')[:50]}' "
                        f"(score: {doc.get('score', 0):.4f})"
                    )
            
            return documents
            
        except Exception as e:
            logger.error(f"Erro ao recuperar documentos: {e}", exc_info=True)
            return []
    
    def normalize_documents(
        self, 
        documents: Optional[List[Dict[str, Any]]]
    ) -> List[Dict[str, Any]]:
        if not documents:
            return []
        
        normalized: List[Dict[str, Any]] = []
        
        for raw in documents:
            doc = dict(raw or {})
            metadata = doc.get("metadata") or {}
            
            title = (
                doc.get("title") or 
                metadata.get("title") or 
                metadata.get("source_title") or 
                ""
            ).strip()
            
            if not title:
                title = "Documento sem título"
            
            category = (
                doc.get("category") or 
                metadata.get("category") or 
                metadata.get("doc_type") or 
                ""
            ).strip()
            
            snippet = doc.get("snippet")
            if not snippet:
                snippet = self._build_snippet(title, doc.get("content"), metadata)
            
            doc.update({
                "title": title,
                "category": category,
                "snippet": snippet,
                "metadata": metadata,
            })
            
            normalized.append(doc)
        
        return normalized
    
    def apply_recency_boost(
        self,
        documents: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Aplica boost de recência aos documentos.

        Delegado para RecencyBoostCalculator utilitário (evita duplicação).

        Args:
            documents: Lista de documentos

        Returns:
            Documentos com boost aplicado e reordenados
        """
        if not documents or len(documents) < 2:
            return documents

        # Delega para utilitário centralizado
        boosted_docs = RecencyBoostCalculator.apply_to_documents(documents)

        # Log top 3 se houve mudanças
        if any(d.get("recency_boost", 0) > 0.05 for d in boosted_docs[:3]):
            logger.info("Boost de recência aplicado - top 3:")
            for i, doc in enumerate(boosted_docs[:3]):
                logger.info(
                    f"  {i+1}. '{doc.get('title', 'unknown')[:50]}' - "
                    f"score: {doc.get('score', 0):.4f} "
                    f"(boost: +{doc.get('recency_boost', 0):.3f})"
                )

        return boosted_docs
    
    def _parse_update_date(self, metadata: Dict[str, Any]) -> Optional[datetime]:
        if not isinstance(metadata, dict):
            return None
        
        updated_at_str = metadata.get("updated_at") or metadata.get("date_mod")
        
        if not updated_at_str:
            return None
        
        try:
            if isinstance(updated_at_str, str):
                if 'T' in updated_at_str:
                    return datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                else:
                    dt = datetime.strptime(updated_at_str, "%Y-%m-%d %H:%M:%S")
                    return dt.replace(tzinfo=timezone.utc)
        except (ValueError, AttributeError) as e:
            logger.debug(f"Erro ao parsear data '{updated_at_str}': {e}")
        
        return None
    
    def _build_snippet(
        self,
        title: str,
        content: Optional[str],
        metadata: Dict[str, Any]
    ) -> str:
        """Constrói snippet formatado do documento.

        Delegado para SnippetBuilder utilitário (evita duplicação).

        Args:
            title: Título do documento
            content: Conteúdo do documento
            metadata: Metadados do documento

        Returns:
            Snippet formatado
        """
        return SnippetBuilder.build(title, content, metadata)