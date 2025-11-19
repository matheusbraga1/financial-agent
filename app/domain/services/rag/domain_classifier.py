from typing import List, Dict, Tuple, Optional
import re

class DomainClassifier:
    def __init__(self, keywords: Optional[Dict[str, List[str]]] = None):
        self.domain_keywords = keywords or self._get_default_keywords()
    
    def classify(self, query: str) -> List[str]:
        scores = self._calculate_scores(query)
        
        if not scores:
            return ["Geral"]
        
        max_score = max(scores.values())
        threshold = max(1, max_score * 0.3)
        
        detected = [
            domain for domain, score in scores.items() 
            if score >= threshold
        ]
        
        return detected if detected else ["Geral"]
    
    def get_confidence(self, query: str, domain: str) -> float:
        scores = self._calculate_scores(query)
        
        if domain not in scores:
            return 0.0
        
        score = scores[domain]
        query_words = len(query.split())
        
        confidence = min(1.0, score / max(1, query_words * 0.4))
        
        return confidence
    
    def classify_with_confidence(self, query: str) -> List[Tuple[str, float]]:
        domains = self.classify(query)
        
        results = [
            (domain, self.get_confidence(query, domain))
            for domain in domains
        ]
        
        results.sort(key=lambda x: x[1], reverse=True)
        
        return results
    
    def _calculate_scores(self, query: str) -> Dict[str, int]:
        query_lower = query.lower()
        scores: Dict[str, int] = {}
        
        for domain, keywords in self.domain_keywords.items():
            if domain == "Geral":
                continue
            
            score = 0
            for keyword in keywords:
                pattern = r'\b' + re.escape(keyword.lower()) + r'\b'
                if re.search(pattern, query_lower):
                    score += 1
            
            if score > 0:
                scores[domain] = score
        
        return scores
    
    def _get_default_keywords(self) -> Dict[str, List[str]]:
        return {
            "TI": [
                "senha", "password", "internet", "rede", "wifi", "conexão",
                "computador", "pc", "notebook", "desktop", "servidor",
                "sistema", "software", "aplicativo", "app", "programa",
                "instalar", "desinstalar", "atualizar", "update",
                "login", "acesso", "usuário", "permissão", "bloqueado",
                "email", "e-mail", "outlook", "correio",
                "erro", "bug", "travando", "lento", "não funciona",
                "vírus", "antivírus", "firewall", "vpn", "segurança",
                "impressora", "scanner", "mouse", "teclado", "monitor",
                "backup", "restore", "recovery", "suporte técnico",
            ],
            "RH": [
                "salário", "pagamento", "contracheque", "holerite",
                "remuneração", "adiantamento", "13º", "décimo terceiro",
                "benefício", "vale", "auxílio", "plano de saúde",
                "vale transporte", "vale refeição", "vale alimentação",
                "férias", "folga", "feriado", "recesso", "descanso",
                "ponto", "hora extra", "atraso", "falta", "atestado",
                "licença", "afastamento",
                "promoção", "cargo", "função", "treinamento", "curso",
                "desenvolvimento", "avaliação", "performance",
                "admissão", "contratação", "demissão", "desligamento",
                "rescisão", "contrato", "documentação",
                "colaborador", "funcionário", "gestor", "equipe",
            ],
            "Financeiro": [
                "nota fiscal", "nf", "invoice", "recibo", "comprovante",
                "pagamento", "pagar", "boleto", "fatura", "cobrança",
                "débito", "crédito", "transferência", "pix",
                "reembolso", "ressarcimento", "devolução", "estorno",
                "compra", "aquisição", "fornecedor", "cotação",
                "pedido", "ordem de compra",
                "orçamento", "budget", "custo", "despesa", "receita",
                "lucro", "prejuízo", "investimento",
                "contábil", "fiscal", "imposto", "tributo",
                "financeiro", "tesouraria", "caixa", "fluxo de caixa",
            ],
            "Geral": [],
        }