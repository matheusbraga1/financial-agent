from typing import Dict, Any, List, Optional
import re

class QueryProcessor:
    def __init__(self, synonyms: Optional[Dict[str, List[str]]] = None):
        self.synonyms = synonyms or self._get_default_synonyms()
    
    def expand(self, query: str, domain: Optional[str] = None) -> str:
        if not query or not query.strip():
            return query
        
        words = self._tokenize(query)
        expanded_words = []
        
        for word in words:
            expanded_words.append(word)
            
            if word.lower() in self.synonyms.get("general", {}):
                synonyms = self.synonyms["general"][word.lower()][:2]
                expanded_words.extend(synonyms)
            
            if domain and word.lower() in self.synonyms.get(domain, {}):
                domain_synonyms = self.synonyms[domain][word.lower()][:1]
                expanded_words.extend(domain_synonyms)
        
        return " ".join(expanded_words)
    
    def get_adaptive_params(self, query: str) -> Dict[str, Any]:
        words = self._tokenize(query)
        query_length = len(words)
        
        if query_length <= 3:
            return {
                "top_k": 20,
                "min_score": 0.10,
                "reason": "query curta - ampliando busca"
            }
        elif query_length >= 15:
            return {
                "top_k": 10,
                "min_score": 0.25,
                "reason": "query específica - resultados precisos"
            }
        else:
            return {
                "top_k": 15,
                "min_score": 0.15,
                "reason": "query padrão"
            }
    
    def normalize(self, text: str) -> str:
        if not text:
            return ""
        
        text = re.sub(r'\s+', ' ', text).strip()
        
        text = re.sub(r'[^\w\s\-]', ' ', text)
        
        return text
    
    def _tokenize(self, text: str) -> List[str]:
        normalized = self.normalize(text)
        return [w for w in normalized.lower().split() if len(w) > 2]
    
    def _get_default_synonyms(self) -> Dict[str, Dict[str, List[str]]]:
        return {
            "general": {
                "senha": ["password", "credencial"],
                "internet": ["rede", "conexão", "wifi"],
                "computador": ["pc", "notebook", "máquina"],
                "lento": ["devagar", "travando"],
                "erro": ["problema", "falha", "bug"],
                "email": ["e-mail", "correio"],
                "sistema": ["aplicação", "software"],
                "instalar": ["baixar", "download"],
                "atualizar": ["update", "upgrade"],
                "remover": ["deletar", "excluir"],
            },
            "TI": {
                "servidor": ["server", "host"],
                "backup": ["cópia", "segurança"],
                "firewall": ["proteção", "segurança"],
                "vpn": ["rede privada", "conexão segura"],
                "antivirus": ["proteção", "segurança"],
            },
            "RH": {
                "férias": ["descanso", "folga"],
                "salário": ["remuneração", "pagamento", "contracheque"],
                "benefício": ["vale", "auxílio"],
                "atestado": ["licença", "afastamento"],
            },
            "Financeiro": {
                "nota fiscal": ["nf", "invoice"],
                "reembolso": ["devolução", "ressarcimento"],
                "pagamento": ["quitação", "débito"],
                "orçamento": ["budget", "custo"],
            },
        }