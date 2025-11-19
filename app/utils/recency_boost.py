from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class RecencyBoostCalculator:

    VERY_RECENT_DAYS = 7
    VERY_RECENT_BOOST = 0.15

    RECENT_DAYS = 30
    RECENT_BOOST = 0.10

    MODERATE_DAYS = 90
    MODERATE_BOOST = 0.05

    OLD_DAYS = 180
    OLD_BOOST = 0.02

    @staticmethod
    def calculate_boost(document_date: datetime) -> float:
        if not document_date:
            raise ValueError("document_date cannot be None")

        now = datetime.now(timezone.utc)

        if document_date.tzinfo is None:
            document_date = document_date.replace(tzinfo=timezone.utc)

        days_old = (now - document_date).days

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
        if not documents:
            return documents

        for doc in documents:
            metadata = doc.get("metadata", {})

            date_str = (
                metadata.get("date_mod") or
                metadata.get("updated_at") or
                metadata.get("date_creation") or
                metadata.get("created_at")
            )

            if not date_str:
                logger.debug(
                    f"Document '{doc.get('title', 'Unknown')[:50]}' has no date field, "
                    "skipping recency boost"
                )
                continue

            try:
                doc_date = datetime.fromisoformat(
                    str(date_str).replace('Z', '+00:00')
                )

                boost = RecencyBoostCalculator.calculate_boost(doc_date)

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
