"""Query Expander aprimorado com sinônimos multi-domínio."""

from __future__ import annotations

from typing import Dict
import re
from app.utils.text_utils import normalize_text


class QueryExpanderMultidomain:
    """
    Expansor de queries com sinônimos específicos de todos os departamentos.

    Expande automaticamente perguntas com termos relacionados para melhorar
    a recuperação de documentos relevantes.
    """

    def __init__(self) -> None:
        # Sinônimos organizados por domínio para melhor cobertura
        self._expansions: Dict[str, list[str]] = {
            # === TI / Tecnologia ===
            'senha': ['password', 'login', 'acesso', 'autenticacao', 'credencial'],
            'login': ['senha', 'acesso', 'entrar', 'logar', 'usuario'],
            'acesso': ['senha', 'login', 'permissao', 'autorizacao', 'entrar'],
            'bloqueado': ['travado', 'bloqueio', 'locked', 'impedido'],
            'email': ['e-mail', 'correio', 'outlook', 'webmail', 'mensagem'],
            'internet': ['rede', 'conexao', 'wifi', 'network', 'conectividade'],
            'vpn': ['rede privada', 'acesso remoto', 'conexao segura'],
            'impressora': ['imprimir', 'impressao', 'printer'],
            'sistema': ['aplicacao', 'programa', 'software', 'aplicativo'],
            'instalar': ['instalacao', 'setup', 'configurar', 'baixar'],
            'erro': ['falha', 'problema', 'bug', 'defeito'],
            'lento': ['devagar', 'travando', 'performance', 'lag'],
            'computador': ['pc', 'notebook', 'laptop', 'maquina'],
            'backup': ['copia seguranca', 'recuperacao', 'restaurar'],
            'servidor': ['server', 'host', 'infraestrutura'],

            # === RH / Recursos Humanos ===
            'ferias': ['recesso', 'descanso', 'afastamento ferias', 'gozo'],
            'salario': ['remuneracao', 'pagamento', 'vencimento', 'proventos'],
            'holerite': ['contracheque', 'folha pagamento', 'demonstrativo'],
            'ponto': ['frequencia', 'registro ponto', 'cartao ponto', 'horario'],
            'atestado': ['licenca medica', 'afastamento medico', 'cid'],
            'beneficios': ['vale transporte', 'vale refeicao', 'plano saude'],
            'admissao': ['contratacao', 'integracao', 'onboarding', 'entrada'],
            'demissao': ['desligamento', 'rescisao', 'termino contrato', 'saida'],
            'licenca': ['afastamento', 'ausencia', 'dispensa', 'permissao'],
            'treinamento': ['capacitacao', 'curso', 'desenvolvimento', 'formacao'],
            'colaborador': ['funcionario', 'empregado', 'trabalhador'],
            'folha': ['folha pagamento', 'holerite', 'demonstrativo'],
            'dcct': ['exame demissional', 'rescisao', 'desligamento'],
            'fgts': ['fundo garantia', 'saque fgts', 'deposito'],
            'inss': ['previdencia', 'contribuicao', 'aposentadoria'],

            # === Financeiro / Contabilidade ===
            'nota fiscal': ['nf', 'nfe', 'nfse', 'danfe', 'fatura'],
            'nfe': ['nota fiscal eletronica', 'nf-e', 'danfe'],
            'pagamento': ['pagar', 'quitacao', 'liquidacao', 'desembolso'],
            'boleto': ['guia pagamento', 'fatura', 'cobranca'],
            'reembolso': ['ressarcimento', 'devolucao', 'restituicao'],
            'despesa': ['custo', 'gasto', 'dispendio', 'debito'],
            'orcamento': ['planejamento', 'previsao', 'budget', 'estimativa'],
            'fatura': ['nota fiscal', 'boleto', 'conta', 'invoice'],
            'cobranca': ['faturamento', 'debito', 'valor devido'],
            'prestacao contas': ['relatorio despesas', 'comprovacao gastos'],
            'centro custo': ['cc', 'departamento', 'setor'],
            'conta': ['despesa', 'fatura', 'debito', 'pagamento'],
            'adiantamento': ['antecipacao', 'provisionamento', 'adiamento'],
            'tributo': ['imposto', 'taxa', 'contribuicao'],
            'contabilidade': ['escrituracao', 'lancamento', 'balanco'],

            # === Loteamento ===
            'lote': ['terreno', 'area', 'gleba', 'fracao', 'parcela'],
            'terreno': ['lote', 'area', 'solo', 'propriedade'],
            'quadra': ['quarteirao', 'bloco', 'secao'],
            'escritura': ['documento propriedade', 'titulo', 'registro'],
            'registro': ['matricula', 'cartorio', 'registro imovel', 'averbacao'],
            'loteamento': ['parcelamento solo', 'desmembramento', 'subdivisao'],
            'aprovacao': ['licenca', 'autorizacao', 'permissao', 'liberacao'],
            'projeto': ['plano', 'planejamento', 'desenho', 'memorial'],
            'infraestrutura': ['obras', 'pavimentacao', 'saneamento'],
            'metragem': ['area', 'tamanho', 'metros quadrados', 'dimensao'],
            'divisa': ['confrontante', 'limite', 'fronteira'],

            # === Aluguel / Locação ===
            'aluguel': ['locacao', 'arrendamento', 'renda', 'rent'],
            'locacao': ['aluguel', 'arrendamento', 'rental'],
            'inquilino': ['locatario', 'arrendatario', 'morador'],
            'locador': ['proprietario', 'dono', 'senhorio'],
            'contrato': ['acordo', 'termo', 'instrumento', 'pacto'],
            'caucao': ['deposito', 'garantia', 'fianca'],
            'vistoria': ['inspecao', 'verificacao', 'laudo', 'check'],
            'inadimplencia': ['atraso', 'mora', 'debito', 'pendencia'],
            'rescisao': ['cancelamento', 'termino', 'distrato'],
            'imovel': ['propriedade', 'residencia', 'edificacao', 'casa'],
            'iptu': ['imposto predial', 'taxa', 'tributo municipal'],
            'condominio': ['taxa condominio', 'rateio', 'despesas comuns'],

            # === Jurídico / Legal ===
            'processo': ['acao', 'demanda', 'litigio', 'causa'],
            'clausula': ['dispositivo', 'artigo', 'item', 'paragrafo'],
            'aditivo': ['termo aditivo', 'emenda', 'alteracao contratual'],
            'acordo': ['transacao', 'ajuste', 'pacto', 'concordia'],
            'multa': ['penalidade', 'sancao', 'pena', 'punicao'],
            'prazo': ['periodo', 'tempo', 'lapso', 'deadline'],
            'lei': ['legislacao', 'norma', 'dispositivo legal', 'regra'],
            'contrato': ['acordo', 'instrumento', 'pacto', 'termo'],
            'procuracao': ['mandato', 'poderes', 'representacao'],
            'alvara': ['licenca', 'autorizacao', 'permissao judicial'],

            # === Termos Gerais / Comuns ===
            'como': ['de que forma', 'de que maneira', 'procedimento'],
            'onde': ['local', 'lugar', 'em qual', 'localizacao'],
            'quando': ['prazo', 'data', 'periodo', 'momento'],
            'quem': ['responsavel', 'pessoa', 'setor'],
            'solicitar': ['pedir', 'requerer', 'requisitar', 'demandar'],
            'documento': ['arquivo', 'file', 'texto', 'papel'],
            'formulario': ['form', 'requerimento', 'solicitacao', 'ficha'],
            'procedimento': ['processo', 'rotina', 'passo passo', 'instrucao'],
            'prazo': ['tempo', 'periodo', 'deadline', 'limite'],
            'cancelar': ['anular', 'revogar', 'desfazer', 'rescindir'],
            'alterar': ['modificar', 'mudar', 'ajustar', 'corrigir'],
        }

    def expand(self, question: str) -> str:
        """
        Expande uma pergunta adicionando sinônimos relevantes.

        Args:
            question: Pergunta original do usuário

        Returns:
            Pergunta expandida com sinônimos
        """
        normalized_question = normalize_text(question)
        words = normalized_question.split()
        expanded_terms = set()
        matched_keys = set()

        for word in words:
            # Limpar pontuação
            clean_word = re.sub(r'[^\w\s]', '', word)

            # Ignorar palavras muito curtas
            if len(clean_word) < 3:
                continue

            # Buscar matches em chaves de expansão
            for key, synonyms in self._expansions.items():
                key_normalized = normalize_text(key)

                # Match exato ou parcial
                if (key_normalized == clean_word or
                    key_normalized in clean_word or
                    clean_word in key_normalized):

                    if key not in matched_keys:
                        # Número de sinônimos adaptativo
                        num_synonyms = 3 if len(words) <= 5 else 2
                        expanded_terms.update(synonyms[:num_synonyms])
                        matched_keys.add(key)

        # Remover termos que já estão na pergunta original
        if expanded_terms:
            expanded_terms = {
                term for term in expanded_terms
                if normalize_text(term) not in normalized_question
            }

            if expanded_terms:
                # Adicionar termos expandidos
                return f"{question} {' '.join(expanded_terms)}"

        return question

    def adaptive_params(self, question: str) -> Dict[str, any]:
        """
        Retorna parâmetros adaptativos baseados nas características da pergunta.

        Args:
            question: Pergunta do usuário

        Returns:
            Dict com top_k, min_score, reasoning
        """
        question_length = len(question.split())
        normalized_q = normalize_text(question)

        # Termos que indicam perguntas específicas/técnicas
        specific_terms = [
            'como fazer', 'passo a passo', 'tutorial', 'configurar',
            'instalar', 'procedimento', 'qual prazo', 'qual valor'
        ]
        has_specific_terms = any(term in normalized_q for term in specific_terms)

        # Termos que indicam problemas/troubleshooting
        problem_terms = [
            'nao funciona', 'erro', 'problema', 'travado', 'lento',
            'nao consigo', 'ajuda', 'duvida', 'bloqueado'
        ]
        has_problem_terms = any(term in normalized_q for term in problem_terms)

        # Termos que indicam perguntas de informação geral
        info_terms = [
            'o que e', 'qual e', 'quem e', 'onde fica', 'quando',
            'por que', 'para que serve'
        ]
        has_info_terms = any(term in normalized_q for term in info_terms)

        # Ajustar parâmetros
        if has_specific_terms and question_length > 8:
            # Pergunta específica detalhada → menos resultados, maior threshold
            return {
                "top_k": 5,
                "min_score": 0.25,
                "reasoning": "pergunta específica e detalhada"
            }

        elif has_problem_terms:
            # Troubleshooting → mais resultados, menor threshold
            return {
                "top_k": 12,
                "min_score": 0.12,
                "reasoning": "pergunta sobre problema/erro"
            }

        elif has_info_terms or question_length <= 5:
            # Pergunta genérica/curta → mais resultados, threshold médio
            return {
                "top_k": 10,
                "min_score": 0.15,
                "reasoning": "pergunta genérica ou curta"
            }

        else:
            # Padrão
            return {
                "top_k": 8,
                "min_score": 0.18,
                "reasoning": "padrão"
            }


# Instância singleton
query_expander_multidomain = QueryExpanderMultidomain()
