"""Recency Boost Calculator - Utilit\u00e1rio para c\u00e1lculo de boost de rec\u00eancia.

Este m\u00f3dulo fornece funcionalidades para aplicar boost de pontuação baseado
na rec\u00eancia dos documentos. Documentos mais recentes recebem boost maior
na pontuação de relevância.

Princípios Clean Code aplicados:
- Single Responsibility: Apenas calcula boost de recência
- Open/Closed: Extensível através de constantes configuráveis
- Don't Repeat Yourself: Elimina duplicação de lógica de recência
- Testável: Métodos estáticos facilmente testáveis com mocks

Exemplo de uso:
    >>> from datetime import datetime
    >>> from app.utils.recency_boost import RecencyBoostCalculator
    >>>
    >>> doc_date = datetime(2024, 11, 10)
    >>> boost = RecencyBoostCalculator.calculate_boost(doc_date)
    >>> print(f"Boost: {boost}")
    >>>
    >>> documents = [{"metadata": {"date_mod": "2024-11-10"}, "score": 0.85}]
    >>> boosted_docs = RecencyBoostCalculator.apply_to_documents(documents)
"""

from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class RecencyBoostCalculator:
    """Calculador de boost de recência para documentos.

    Esta classe fornece métodos estáticos para calcular e aplicar boost
    de pontuação baseado na recência dos documentos. Documentos mais
    recentes recebem maior prioridade nos resultados de busca.

    Constantes de configuração:
        VERY_RECENT_DAYS (int): Dias para considerar "muito recente" (7)
        VERY_RECENT_BOOST (float): Boost para docs muito recentes (0.15)
        RECENT_DAYS (int): Dias para considerar "recente" (30)
        RECENT_BOOST (float): Boost para docs recentes (0.10)
        MODERATE_DAYS (int): Dias para considerar "moderadamente recente" (90)
        MODERATE_BOOST (float): Boost para docs moderados (0.05)
        OLD_DAYS (int): Dias para considerar "antigo" (180)
        OLD_BOOST (float): Boost para docs antigos (0.02)

    Thread-safe: Sim (métodos estáticos sem estado mutável)
    """

    # Constantes de configuração (podem ser sobrescritas por configuração externa)
    VERY_RECENT_DAYS = 7
    VERY_RECENT_BOOST = 0.15  # 15% boost - docs da última semana

    RECENT_DAYS = 30
    RECENT_BOOST = 0.10  # 10% boost - docs do último mês

    MODERATE_DAYS = 90
    MODERATE_BOOST = 0.05  # 5% boost - docs dos últimos 3 meses

    OLD_DAYS = 180
    OLD_BOOST = 0.02  # 2% boost - docs dos últimos 6 meses

    # Acima de OLD_DAYS não recebe boost

    @staticmethod
    def calculate_boost(document_date: datetime) -> float:
        """Calcula o valor de boost baseado na data do documento.

        O boost é calculado de forma escalonada:
        - < 7 dias: 0.15 (muito recente)
        - < 30 dias: 0.10 (recente)
        - < 90 dias: 0.05 (moderado)
        - < 180 dias: 0.02 (antigo)
        - >= 180 dias: 0.00 (sem boost)

        Args:
            document_date: Data do documento (aware ou naive datetime)

        Returns:
            float: Valor do boost (0.0 a 0.15)

        Raises:
            ValueError: Se document_date for None ou inválido

        Example:
            >>> from datetime import datetime, timedelta
            >>>
            >>> # Documento de ontem
            >>> yesterday = datetime.now() - timedelta(days=1)
            >>> boost = RecencyBoostCalculator.calculate_boost(yesterday)
            >>> assert boost == 0.15  # Muito recente
            >>>
            >>> # Documento de 2 meses atrás
            >>> two_months_ago = datetime.now() - timedelta(days=60)
            >>> boost = RecencyBoostCalculator.calculate_boost(two_months_ago)
            >>> assert boost == 0.05  # Moderado
        """
        if not document_date:
            raise ValueError("document_date cannot be None")

        # Obtém data atual com timezone UTC
        now = datetime.now(timezone.utc)

        # Garante que document_date seja timezone-aware
        if document_date.tzinfo is None:
            document_date = document_date.replace(tzinfo=timezone.utc)

        # Calcula idade do documento em dias
        days_old = (now - document_date).days

        # Aplica boost escalonado
        if days_old < RecencyBoostCalculator.VERY_RECENT_DAYS:
            return RecencyBoostCalculator.VERY_RECENT_BOOST
        elif days_old < RecencyBoostCalculator.RECENT_DAYS:
            return RecencyBoostCalculator.RECENT_BOOST
        elif days_old < RecencyBoostCalculator.MODERATE_DAYS:
            return RecencyBoostCalculator.MODERATE_BOOST
        elif days_old < RecencyBoostCalculator.OLD_DAYS:
            return RecencyBoostCalculator.OLD_BOOST
        else:
            return 0.0

    @staticmethod
    def apply_to_documents(documents: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Aplica boost de recência a uma lista de documentos.

        Este método:
        1. Itera sobre os documentos
        2. Extrai a data de modificação/criação dos metadados
        3. Calcula o boost apropriado
        4. Adiciona o boost ao score existente
        5. Reordena os documentos por score

        Campos de data tentados (em ordem de preferência):
        - metadata.date_mod
        - metadata.updated_at
        - metadata.date_creation
        - metadata.created_at

        O documento original é modificado in-place e também retornado.

        Args:
            documents: Lista de documentos (dicts) com campos:
                - score (float): Pontuação original
                - metadata (dict): Metadados contendo datas

        Returns:
            List[Dict]: Mesma lista de documentos, ordenada por score decrescente

        Side Effects:
            - Modifica documents in-place adicionando/atualizando:
                - score: Pontuação original + boost
                - recency_boost: Valor do boost aplicado

        Example:
            >>> documents = [
            ...     {
            ...         "title": "Doc Recente",
            ...         "score": 0.80,
            ...         "metadata": {"date_mod": "2024-11-10T10:00:00"}
            ...     },
            ...     {
            ...         "title": "Doc Antigo",
            ...         "score": 0.85,
            ...         "metadata": {"date_mod": "2023-01-01T10:00:00"}
            ...     }
            ... ]
            >>> boosted = RecencyBoostCalculator.apply_to_documents(documents)
            >>> # Doc recente agora tem score maior devido ao boost
            >>> assert boosted[0]["title"] == "Doc Recente"
        """
        if not documents:
            return documents

        for doc in documents:
            metadata = doc.get("metadata", {})

            # Tenta diferentes campos de data (prioridade: mod > created)
            date_str = (
                metadata.get("date_mod") or
                metadata.get("updated_at") or
                metadata.get("date_creation") or
                metadata.get("created_at")
            )

            # Se não há data, pula este documento
            if not date_str:
                logger.debug(
                    f"Document '{doc.get('title', 'Unknown')[:50]}' has no date field, "
                    "skipping recency boost"
                )
                continue

            try:
                # Parse da data (suporta ISO format com/sem 'Z')
                doc_date = datetime.fromisoformat(
                    str(date_str).replace('Z', '+00:00')
                )

                # Calcula boost
                boost = RecencyBoostCalculator.calculate_boost(doc_date)

                # Aplica boost apenas se maior que zero
                if boost > 0:
                    original_score = doc.get("score", 0.0)
                    new_score = original_score + boost

                    doc["score"] = new_score
                    doc["recency_boost"] = boost

                    logger.debug(
                        f"Applied recency boost: {boost:.2f} to document "
                        f"'{doc.get('title', 'Unknown')[:50]}' "
                        f"(score: {original_score:.3f} -> {new_score:.3f}, "
                        f"age: {(datetime.now(timezone.utc) - doc_date).days} days)"
                    )

            except (ValueError, TypeError) as e:
                logger.debug(
                    f"Could not parse date '{date_str}' for document "
                    f"'{doc.get('title', 'Unknown')[:50]}': {e}"
                )
                continue

        # Reordena por score decrescente
        sorted_docs = sorted(
            documents,
            key=lambda x: x.get("score", 0.0),
            reverse=True
        )

        logger.info(
            f"Applied recency boost to {len(documents)} documents, "
            f"{sum(1 for d in documents if 'recency_boost' in d)} received boost"
        )

        return sorted_docs

    @staticmethod
    def get_boost_info(document_date: datetime) -> Dict[str, Any]:
        """Retorna informações detalhadas sobre o boost de um documento.

        Útil para debugging e análise de relevância.

        Args:
            document_date: Data do documento

        Returns:
            Dict com informações:
                - boost (float): Valor do boost
                - days_old (int): Idade em dias
                - category (str): Categoria de recência
                - description (str): Descrição humana

        Example:
            >>> from datetime import datetime, timedelta
            >>>
            >>> date = datetime.now() - timedelta(days=5)
            >>> info = RecencyBoostCalculator.get_boost_info(date)
            >>> print(info)
            {
                'boost': 0.15,
                'days_old': 5,
                'category': 'very_recent',
                'description': 'Documento muito recente (última semana)'
            }
        """
        if not document_date:
            return {
                "boost": 0.0,
                "days_old": None,
                "category": "no_date",
                "description": "Sem data disponível"
            }

        now = datetime.now(timezone.utc)
        if document_date.tzinfo is None:
            document_date = document_date.replace(tzinfo=timezone.utc)

        days_old = (now - document_date).days
        boost = RecencyBoostCalculator.calculate_boost(document_date)

        # Determina categoria e descrição
        if days_old < RecencyBoostCalculator.VERY_RECENT_DAYS:
            category = "very_recent"
            description = "Documento muito recente (última semana)"
        elif days_old < RecencyBoostCalculator.RECENT_DAYS:
            category = "recent"
            description = "Documento recente (último mês)"
        elif days_old < RecencyBoostCalculator.MODERATE_DAYS:
            category = "moderate"
            description = "Documento moderadamente recente (últimos 3 meses)"
        elif days_old < RecencyBoostCalculator.OLD_DAYS:
            category = "old"
            description = "Documento antigo (últimos 6 meses)"
        else:
            category = "very_old"
            description = "Documento muito antigo (mais de 6 meses)"

        return {
            "boost": boost,
            "days_old": days_old,
            "category": category,
            "description": description
        }
