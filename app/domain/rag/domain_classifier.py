"""Classificador de domínio para perguntas multi-departamento."""

from typing import List, Dict, Optional
from app.domain.documents.metadata_schema import Department
import re


class DomainClassifier:
    """
    Classifica perguntas para o(s) departamento(s) mais relevante(s).

    Exemplos:
    - "Como resetar senha?" -> [TI]
    - "Como tirar férias?" -> [RH]
    - "Como emitir nota fiscal?" -> [Financeiro]
    - "Qual o prazo de pagamento de férias?" -> [RH, Financeiro]
    """

    # Palavras-chave por departamento (quanto mais específica, maior o peso)
    DOMAIN_KEYWORDS = {
        Department.TI: {
            # Alta especificidade (peso 3)
            "alta": [
                "vpn", "active directory", "dns", "dhcp", "firewall", "antivirus",
                "backup", "outlook", "windows", "linux", "servidor", "rede",
                "switch", "roteador", "ip", "proxy", "wi-fi", "wifi"
            ],
            # Média especificidade (peso 2)
            "media": [
                "senha", "login", "acesso", "email", "impressora", "computador",
                "sistema", "software", "internet", "chamado", "ticket",
                "instalação", "configuração", "permissão"
            ],
            # Baixa especificidade (peso 1)
            "baixa": [
                "tela", "mouse", "teclado", "monitor", "notebook", "desktop"
            ]
        },

        Department.RH: {
            "alta": [
                "férias", "holerite", "folha de pagamento", "ponto eletrônico",
                "admissão", "demissão", "rescisão", "dcct", "fgts", "inss",
                "vale-transporte", "vale-refeição", "plano de saúde"
            ],
            "media": [
                "salário", "benefícios", "atestado", "licença", "afastamento",
                "treinamento", "curso", "colaborador", "funcionário",
                "contrato de trabalho", "registro", "carteira"
            ],
            "baixa": [
                "aniversário", "uniforme", "crachá"
            ]
        },

        Department.FINANCEIRO: {
            "alta": [
                "nota fiscal", "nfe", "nfse", "danfe", "boleto", "fatura",
                "pagamento", "cobrança", "inadimplência", "juros",
                "prestação de contas", "centro de custo", "orçamento"
            ],
            "media": [
                "reembolso", "despesa", "adiantamento", "conta", "débito",
                "crédito", "transferência", "pix", "ted", "doc"
            ],
            "baixa": [
                "dinheiro", "valor", "custo", "preço"
            ]
        },

        Department.LOTEAMENTO: {
            "alta": [
                "loteamento", "desmembramento", "remembramento", "gleba",
                "infraestrutura", "pavimentação", "esgoto", "água",
                "registro de imóvel", "matrícula", "averbação"
            ],
            "media": [
                "lote", "terreno", "quadra", "área", "metragem",
                "escritura", "projeto", "aprovação", "licença"
            ],
            "baixa": [
                "divisa", "confrontante", "testada"
            ]
        },

        Department.ALUGUEL: {
            "alta": [
                "locação", "locatário", "locador", "inquilino", "fiador",
                "caução", "garantia locatícia", "seguro fiança",
                "vistoria de entrada", "vistoria de saída", "rescisão de contrato"
            ],
            "media": [
                "aluguel", "imóvel", "residencial", "comercial",
                "contrato de locação", "inadimplência", "despejo",
                "iptu", "condomínio", "repasse"
            ],
            "baixa": [
                "casa", "apartamento", "sala"
            ]
        },

        Department.JURIDICO: {
            "alta": [
                "processo", "ação judicial", "recurso", "sentença",
                "alvará", "procuração", "substabelecimento", "petição"
            ],
            "media": [
                "contrato", "cláusula", "aditivo", "rescisão contratual",
                "acordo", "multa", "indenização", "prazo legal"
            ],
            "baixa": [
                "direito", "lei", "legislação", "norma"
            ]
        }
    }

    # Padrões regex para detecção de contexto
    PATTERNS = {
        Department.TI: [
            r"resetar.*senha",
            r"configurar.*email",
            r"instalar.*software",
            r"erro.*sistema",
            r"problema.*internet"
        ],
        Department.RH: [
            r"tirar.*f[ée]rias",
            r"solicitar.*atestado",
            r"bater.*ponto",
            r"(receber|consultar).*holerite"
        ],
        Department.FINANCEIRO: [
            r"emitir.*nota",
            r"solicitar.*reembolso",
            r"pagar.*boleto",
            r"enviar.*nfe"
        ],
        Department.LOTEAMENTO: [
            r"registrar.*lote",
            r"aprovação.*projeto",
            r"escritura.*terreno"
        ],
        Department.ALUGUEL: [
            r"alugar.*im[óo]vel",
            r"rescindir.*loca[çc][ãa]o",
            r"renovar.*contrato.*aluguel"
        ],
        Department.JURIDICO: [
            r"abrir.*processo",
            r"revisar.*contrato",
            r"cl[áa]usula.*contratual"
        ]
    }

    def __init__(self):
        """Inicializa o classificador."""
        pass

    def classify(self, question: str, top_n: int = 2) -> List[Department]:
        """
        Classifica a pergunta retornando os departamentos mais relevantes.

        Args:
            question: Pergunta do usuário
            top_n: Número máximo de departamentos a retornar

        Returns:
            Lista de departamentos ordenados por relevância (pode ser vazia se nenhum match)
        """
        question_lower = question.lower()
        scores = {}

        # 1. Score baseado em palavras-chave
        for dept, keyword_levels in self.DOMAIN_KEYWORDS.items():
            score = 0

            # Palavras de alta especificidade (peso 3)
            for keyword in keyword_levels.get("alta", []):
                if keyword in question_lower:
                    score += 3

            # Palavras de média especificidade (peso 2)
            for keyword in keyword_levels.get("media", []):
                if keyword in question_lower:
                    score += 2

            # Palavras de baixa especificidade (peso 1)
            for keyword in keyword_levels.get("baixa", []):
                if keyword in question_lower:
                    score += 1

            if score > 0:
                scores[dept] = score

        # 2. Boost de score baseado em padrões regex (peso 5)
        for dept, patterns in self.PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, question_lower):
                    scores[dept] = scores.get(dept, 0) + 5

        # 3. Se nenhum departamento foi identificado, retornar lista vazia
        # (o RAG buscará em todos os departamentos)
        if not scores:
            return []

        # 4. Ordenar por score
        sorted_depts = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # 5. Aplicar lógica de threshold
        top_score = sorted_depts[0][1]

        # Se o top score é MUITO maior que o segundo (3x), retornar apenas ele
        if len(sorted_depts) > 1 and top_score >= sorted_depts[1][1] * 3:
            return [sorted_depts[0][0]]

        # Se há empate técnico (diferença < 20%), incluir ambos
        result = [sorted_depts[0][0]]
        for dept, score in sorted_depts[1:top_n]:
            if score >= top_score * 0.8:  # Diferença de no máximo 20%
                result.append(dept)

        return result

    def get_confidence(self, question: str, department: Department) -> float:
        """
        Retorna a confiança (0-1) de que a pergunta pertence ao departamento.

        Args:
            question: Pergunta do usuário
            department: Departamento a avaliar

        Returns:
            Float entre 0 (sem confiança) e 1 (alta confiança)
        """
        question_lower = question.lower()
        score = 0

        # Contar matches de palavras-chave
        keyword_levels = self.DOMAIN_KEYWORDS.get(department, {})

        for keyword in keyword_levels.get("alta", []):
            if keyword in question_lower:
                score += 3

        for keyword in keyword_levels.get("media", []):
            if keyword in question_lower:
                score += 2

        for keyword in keyword_levels.get("baixa", []):
            if keyword in question_lower:
                score += 1

        # Boost de padrões
        patterns = self.PATTERNS.get(department, [])
        for pattern in patterns:
            if re.search(pattern, question_lower):
                score += 5

        # Normalizar para 0-1 (score máximo razoável: 15)
        confidence = min(score / 15.0, 1.0)

        return confidence

    def explain_classification(self, question: str) -> Dict[Department, Dict[str, any]]:
        """
        Retorna explicação detalhada da classificação (útil para debugging).

        Returns:
            Dict com department -> {score, confidence, matched_keywords, matched_patterns}
        """
        question_lower = question.lower()
        explanation = {}

        for dept in Department:
            matched_keywords = []
            matched_patterns = []
            score = 0

            # Keywords
            keyword_levels = self.DOMAIN_KEYWORDS.get(dept, {})
            for level, keywords in keyword_levels.items():
                for kw in keywords:
                    if kw in question_lower:
                        matched_keywords.append({"keyword": kw, "level": level})
                        if level == "alta":
                            score += 3
                        elif level == "media":
                            score += 2
                        else:
                            score += 1

            # Patterns
            patterns = self.PATTERNS.get(dept, [])
            for pattern in patterns:
                if re.search(pattern, question_lower):
                    matched_patterns.append(pattern)
                    score += 5

            if score > 0 or matched_keywords or matched_patterns:
                explanation[dept] = {
                    "score": score,
                    "confidence": min(score / 15.0, 1.0),
                    "matched_keywords": matched_keywords,
                    "matched_patterns": matched_patterns
                }

        return explanation
