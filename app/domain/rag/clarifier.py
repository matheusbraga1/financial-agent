from __future__ import annotations

from typing import List, Dict, Optional


class Clarifier:
    """Heurísticas simples para perguntas de esclarecimento.

    Regras:
    - Perguntas muito curtas (<= 5 palavras) com termos genéricos disparam follow-up.
    - Baixa confiança implícita (poucos docs ou scores baixos) também disparam follow-up.
    - Casos especiais: 'senha', 'impressora', 'email', 'vpn', 'rede'.
    """

    GENERIC_TERMS = {
        'senha', 'login', 'acesso', 'impressora', 'imprimir', 'rede', 'vpn', 'email', 'conta',
        'sistema', 'aplicativo', 'aplicação', 'programa'
    }

    def maybe_clarify(self, question: str, documents: Optional[List[Dict[str, any]]] = None) -> Optional[str]:
        q = (question or '').strip().lower()
        if not q:
            return None

        words = [w for w in q.replace('?', ' ').split() if w]
        short = len(words) <= 5

        # Heurística de baixa confiança nos docs recuperados
        low_conf_docs = False
        if documents is not None:
            if len(documents) == 0:
                low_conf_docs = True
            else:
                try:
                    max_score = max(float(d.get('score', 0.0)) for d in documents)
                except Exception:
                    max_score = 0.0
                if max_score < 0.25:
                    low_conf_docs = True

        contains_generic = any(term in q for term in self.GENERIC_TERMS)

        if contains_generic and (short or low_conf_docs):
            # Casos especiais
            if 'senha' in q:
                return 'Qual senha você deseja trocar? (Windows/AD, e-mail, GLPI, VPN, etc.)'
            if 'impressora' in q or 'imprimir' in q:
                return 'É impressão local ou de rede? Qual modelo da impressora e o sistema operacional?'
            if 'vpn' in q:
                return 'Você usa qual cliente VPN (FortiClient, AnyConnect, outro)? Em qual sistema?'
            if 'email' in q:
                return 'É senha/configuração do e-mail ou problema de envio/recebimento? Qual aplicativo/versão?'
            if 'rede' in q:
                return 'A conexão é via cabo ou Wi‑Fi? O problema ocorre em outros dispositivos/locais?'

            # fallback genérico
            return 'Poderia detalhar melhor? Qual sistema/área exatamente para focarmos na resposta.'

        return None

