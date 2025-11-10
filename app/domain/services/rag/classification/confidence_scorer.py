"""Calculador de score de confiança para respostas do RAG."""

from typing import List, Dict, Any
import statistics
import logging

logger = logging.getLogger(__name__)


class ConfidenceScorer:
    """
    Calcula score de confiança da resposta baseado em múltiplos fatores:

    1. Score dos documentos recuperados
    2. Consistência entre documentos
    3. Quantidade de documentos relevantes
    4. Cobertura da pergunta pelos documentos
    """

    def __init__(self):
        # Thresholds para classificação de confiança
        self.confidence_levels = {
            "muito_alta": 0.80,  # >= 80%
            "alta": 0.60,        # >= 60%
            "media": 0.40,       # >= 40%
            "baixa": 0.20,       # >= 20%
            "muito_baixa": 0.0   # < 20%
        }

    def calculate_confidence(
        self,
        documents: List[Dict[str, Any]],
        question: str = "",
        domain_confidence: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calcula confiança geral da resposta.

        Args:
            documents: Lista de documentos recuperados com scores
            question: Pergunta original (opcional, para análise de cobertura)
            domain_confidence: Confiança da classificação de domínio (0-1)

        Returns:
            Dict com:
            - score: float (0-1)
            - level: str ("muito_alta", "alta", "media", "baixa", "muito_baixa")
            - factors: Dict com scores de cada fator
            - message: str explicativa
        """
        if not documents:
            return {
                "score": 0.0,
                "level": "muito_baixa",
                "factors": {},
                "message": "Nenhum documento relevante encontrado"
            }

        factors = {}

        # Fator 1: Score médio dos documentos (peso: 40%)
        doc_scores = [float(doc.get("score", 0.0)) for doc in documents]
        avg_score = statistics.mean(doc_scores)
        factors["avg_document_score"] = avg_score

        # Fator 2: Score do melhor documento (peso: 30%)
        max_score = max(doc_scores) if doc_scores else 0.0
        factors["max_document_score"] = max_score

        # Fator 3: Consistência entre documentos (peso: 15%)
        # Medido por desvio padrão - menor desvio = maior consistência
        if len(doc_scores) > 1:
            std_dev = statistics.stdev(doc_scores)
            # Normalizar usando função sigmóide invertida para evitar valores negativos
            # std_dev de 0.0 → consistency 1.0, std_dev de 0.5 → 0.5, std_dev de 1.0 → 0.0
            consistency = max(0.0, 1.0 - min(1.0, std_dev))
        else:
            # Penalizar quando há apenas 1 documento (baixa evidência)
            consistency = 0.5  # Reduzido de 1.0 para 0.5
        factors["document_consistency"] = consistency

        # Fator 4: Quantidade de documentos de alta qualidade (peso: 10%)
        high_quality_docs = sum(1 for score in doc_scores if score >= 0.6)
        quality_ratio = high_quality_docs / len(documents) if documents else 0.0
        factors["quality_ratio"] = quality_ratio

        # Fator 5: Confiança do domínio (peso: 10% - aumentado de 5%)
        factors["domain_confidence"] = domain_confidence

        # Calcular score final ponderado (ajustado: domain 5%→10%, quality 10%→5%)
        final_score = (
            avg_score * 0.40 +
            max_score * 0.30 +
            consistency * 0.15 +
            quality_ratio * 0.05 +  # Reduzido de 10% para 5%
            domain_confidence * 0.10  # Aumentado de 5% para 10%
        )

        # Penalizar se houver poucos documentos (< 3)
        if len(documents) < 3:
            doc_count_penalty = 0.85  # Multiplica por 0.85 se < 3 docs
            final_score *= doc_count_penalty
            factors["doc_count_penalty"] = doc_count_penalty

        final_score = max(0.0, min(1.0, final_score))

        # Determinar nível de confiança
        if final_score >= self.confidence_levels["muito_alta"]:
            level = "muito_alta"
            message = "Alta confiança - resposta baseada em documentos altamente relevantes"
        elif final_score >= self.confidence_levels["alta"]:
            level = "alta"
            message = "Boa confiança - resposta baseada em documentos relevantes"
        elif final_score >= self.confidence_levels["media"]:
            level = "media"
            message = "Confiança moderada - verifique informações adicionais se necessário"
        elif final_score >= self.confidence_levels["baixa"]:
            level = "baixa"
            message = "Baixa confiança - considere reformular a pergunta ou consultar outras fontes"
        else:
            level = "muito_baixa"
            message = "Confiança muito baixa - documentos encontrados podem não ser relevantes"

        logger.debug(
            f"Confiança calculada: {final_score:.2f} ({level}) - "
            f"Fatores: avg={avg_score:.2f}, max={max_score:.2f}, "
            f"consistency={consistency:.2f}, quality={quality_ratio:.2f}"
        )

        return {
            "score": round(final_score, 3),
            "level": level,
            "factors": factors,
            "message": message,
            "document_count": len(documents),
            "high_quality_count": high_quality_docs
        }

    def get_confidence_emoji(self, confidence_score: float) -> str:
        """
        Retorna emoji representando nível de confiança.

        Args:
            confidence_score: Score de confiança (0-1)

        Returns:
            Emoji string
        """
        if confidence_score >= 0.80:
            return "🟢"  # Verde - Muito Alta
        elif confidence_score >= 0.60:
            return "🔵"  # Azul - Alta
        elif confidence_score >= 0.40:
            return "🟡"  # Amarelo - Média
        elif confidence_score >= 0.20:
            return "🟠"  # Laranja - Baixa
        else:
            return "🔴"  # Vermelho - Muito Baixa

    def should_show_confidence_warning(self, confidence_score: float) -> bool:
        """
        Determina se deve mostrar aviso de baixa confiança ao usuário.

        Args:
            confidence_score: Score de confiança (0-1)

        Returns:
            bool: True se deve mostrar aviso
        """
        return confidence_score < 0.40


# Singleton
confidence_scorer = ConfidenceScorer()
