from __future__ import annotations

from typing import Dict
import re
from app.utils.text_utils import normalize_text


class QueryExpander:
    def __init__(self) -> None:
        # Termos e sinônimos (pode futuramente vir de config/DB)
        self._expansions: Dict[str, list[str]] = {
            'senha': ['password', 'login', 'acesso', 'autenticacao', 'credencial', 'logar', 'entrar', 'autenticar'],
            'login': ['senha', 'acesso', 'entrar', 'logar', 'credencial', 'usuario'],
            'acesso': ['senha', 'login', 'permissao', 'autorizacao', 'entrar', 'acessar'],
            'bloqueado': ['travado', 'bloqueio', 'locked', 'impedido', 'trancado'],
            'desbloquear': ['destravar', 'liberar', 'unlock', 'desbloquear'],
            'email': ['e-mail', 'correio', 'outlook', 'webmail', 'mensagem', 'mail', 'correio eletronico'],
            'mensagem': ['email', 'msg', 'comunicacao', 'aviso'],
            'internet': ['rede', 'conexao', 'wifi', 'network', 'conectividade', 'online', 'web'],
            'rede': ['internet', 'conexao', 'network', 'wifi', 'lan', 'conectividade'],
            'wifi': ['wireless', 'sem fio', 'rede', 'internet', 'conexao'],
            'vpn': ['rede privada', 'acesso remoto', 'conexao segura', 'virtual private'],
            'impressora': ['imprimir', 'impressao', 'printer', 'documento', 'pagina'],
            'imprimir': ['impressora', 'impressao', 'printer', 'documento', 'papel'],
            'scanner': ['escanear', 'digitalizar', 'scan', 'digitalizacao'],
            'sistema': ['aplicacao', 'programa', 'software', 'app', 'aplicativo', 'plataforma'],
            'aplicacao': ['sistema', 'programa', 'software', 'app', 'aplicativo'],
            'programa': ['sistema', 'aplicacao', 'software', 'app', 'ferramenta'],
            'instalar': ['instalacao', 'setup', 'configurar', 'baixar', 'download'],
            'atualizar': ['update', 'atualizacao', 'upgrade', 'nova versao'],
            'lento': ['devagar', 'travando', 'performance', 'lag', 'demora', 'lerdo', 'demorado'],
            'travando': ['congelando', 'lento', 'travado', 'freeze', 'parado', 'nao responde'],
            'travado': ['travando', 'congelado', 'freeze', 'parado', 'bloqueado'],
            'erro': ['falha', 'problema', 'bug', 'defeito', 'issue', 'error', 'nao funciona'],
            'problema': ['erro', 'falha', 'bug', 'issue', 'dificuldade', 'defeito'],
            'falha': ['erro', 'problema', 'bug', 'nao funciona', 'quebrado'],
            'nao funciona': ['erro', 'problema', 'falha', 'quebrado', 'defeito', 'parou'],
            'computador': ['pc', 'notebook', 'laptop', 'maquina', 'desktop', 'micro'],
            'notebook': ['laptop', 'computador', 'portatil', 'pc'],
            'teclado': ['keyboard', 'teclas', 'digitar'],
            'mouse': ['cursor', 'ponteiro', 'clique'],
            'monitor': ['tela', 'display', 'video', 'screen'],
            'arquivo': ['documento', 'file', 'pasta', 'dados', 'doc'],
            'pasta': ['diretorio', 'folder', 'arquivo', 'pasta'],
            'documento': ['arquivo', 'doc', 'file', 'texto'],
            'backup': ['copia de seguranca', 'backup', 'recuperacao', 'restaurar'],
            'video': ['videoconferencia', 'reuniao', 'meet', 'zoom', 'teams', 'conferencia'],
            'reuniao': ['meeting', 'videoconferencia', 'chamada', 'video', 'encontro'],
            'teams': ['microsoft teams', 'reuniao', 'chat', 'videoconferencia'],
            'zoom': ['reuniao', 'videoconferencia', 'chamada', 'video'],
            'servidor': ['server', 'servidores', 'maquina', 'host', 'infraestrutura', 'datacenter'],
            'servidores': ['servidor', 'server', 'maquinas', 'hosts', 'infraestrutura'],
            'maquina virtual': ['vm', 'virtual machine', 'virtualizacao', 'servidor virtual', 'maquina'],
            'vm': ['maquina virtual', 'virtual machine', 'virtualizacao', 'servidor virtual'],
            'virtual': ['vm', 'virtualizacao', 'maquina virtual', 'virtual machine'],
            'lista': ['relacao', 'listagem', 'inventario', 'catalogo', 'registro'],
            'configurar': ['configuracao', 'setup', 'ajustar', 'parametrizar', 'definir'],
            'resetar': ['reiniciar', 'reset', 'restaurar', 'limpar', 'reboot'],
            'reiniciar': ['restart', 'reboot', 'resetar', 'religar'],
            'deletar': ['excluir', 'apagar', 'remover', 'delete'],
            'recuperar': ['restaurar', 'recovery', 'backup', 'resgatar'],
        }

    def expand(self, question: str) -> str:
        normalized_question = normalize_text(question)
        words = normalized_question.split()
        expanded_terms = set()
        matched_keys = set()
        for word in words:
            clean_word = re.sub(r'[^\w\s]', '', word)
            if len(clean_word) < 3:
                continue
            for key, synonyms in self._expansions.items():
                key_normalized = normalize_text(key)
                if key_normalized == clean_word or key_normalized in clean_word or clean_word in key_normalized:
                    if key not in matched_keys:
                        num_synonyms = 4 if len(words) <= 3 else 3
                        expanded_terms.update(synonyms[:num_synonyms])
                        matched_keys.add(key)
        if expanded_terms:
            expanded_terms = {term for term in expanded_terms if normalize_text(term) not in normalized_question}
            if expanded_terms:
                return f"{question} {' '.join(expanded_terms)}"
        return question

    def adaptive_params(self, question: str) -> Dict[str, any]:
        question_length = len(question.split())
        normalized_q = normalize_text(question)
        specific_terms = ['como fazer', 'passo a passo', 'tutorial', 'configurar', 'instalar', 'procedimento']
        has_specific_terms = any(term in normalized_q for term in specific_terms)
        problem_terms = ['nao funciona', 'erro', 'problema', 'travado', 'lento', 'nao consigo', 'ajuda']
        has_problem_terms = any(term in normalized_q for term in problem_terms)
        if question_length > 12 or has_specific_terms:
            return {"top_k": 7, "min_score": 0.20, "reasoning": "pergunta específica/detalhada"}
        elif has_problem_terms:
            return {"top_k": 10, "min_score": 0.15, "reasoning": "pergunta sobre problema"}
        elif question_length <= 5:
            return {"top_k": 10, "min_score": 0.15, "reasoning": "pergunta genérica/curta"}
        else:
            return {"top_k": 10, "min_score": 0.18, "reasoning": "padrão"}

