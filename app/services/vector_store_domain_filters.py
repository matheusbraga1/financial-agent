"""Filtros para VectorStore - suporte multi-domínio."""

from typing import List, Optional, Dict, Any
from qdrant_client.models import Filter, FieldCondition, MatchAny
import logging

logger = logging.getLogger(__name__)


class VectorStoreDomainFilters:
    """Helper para construir filtros Qdrant para busca multi-domínio."""

    @staticmethod
    def build_department_filter(
        departments: Optional[List[str]] = None,
        doc_types: Optional[List[str]] = None,
    ) -> Optional[Filter]:
        """
        Constrói filtro Qdrant para departamentos e tipos de documento.

        Args:
            departments: Lista de departamentos (ex: ["TI", "RH"])
            doc_types: Lista de tipos de documento (ex: ["article", "policy"])

        Returns:
            Filter do Qdrant ou None se nenhum filtro aplicável
        """
        conditions = []

        if departments and len(departments) > 0:
            # Filtrar por departamento usando MatchAny
            conditions.append(
                FieldCondition(
                    key="department",
                    match=MatchAny(any=departments)
                )
            )
            logger.debug(f"Filtro de departamento: {departments}")

        if doc_types and len(doc_types) > 0:
            # Filtrar por tipo de documento
            conditions.append(
                FieldCondition(
                    key="doc_type",
                    match=MatchAny(any=doc_types)
                )
            )
            logger.debug(f"Filtro de tipo de documento: {doc_types}")

        if not conditions:
            return None

        return Filter(must=conditions)

    @staticmethod
    def merge_filters(filter1: Optional[Filter], filter2: Optional[Filter]) -> Optional[Filter]:
        """
        Combina dois filtros Qdrant (AND lógico).

        Args:
            filter1: Primeiro filtro
            filter2: Segundo filtro

        Returns:
            Filtro combinado
        """
        if filter1 is None:
            return filter2
        if filter2 is None:
            return filter1

        # Combinar condições must
        must_conditions = []

        if hasattr(filter1, 'must') and filter1.must:
            must_conditions.extend(filter1.must)

        if hasattr(filter2, 'must') and filter2.must:
            must_conditions.extend(filter2.must)

        return Filter(must=must_conditions) if must_conditions else None
