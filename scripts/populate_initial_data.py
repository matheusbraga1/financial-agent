import sys
import os

# Adicionar o diretório pai ao path para importar app
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.vector_store_service import vector_store_service
from app.services.embedding_service import embedding_service
from app.models.document import DocumentCreate
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Documentos de exemplo
INITIAL_DOCUMENTS = [
    {
        "title": "Resetar Senha do Email",
        "category": "Email",
        "content": """Para resetar sua senha do email corporativo, siga os seguintes passos:

1. Acesse o portal RH em rh.empresa.com
2. Clique no botão "Esqueci minha senha"
3. Digite seu CPF no campo indicado
4. Você receberá um link de redefinição por SMS no seu celular cadastrado
5. Clique no link e crie uma nova senha seguindo os requisitos:
   - Mínimo 8 caracteres
   - Pelo menos uma letra maiúscula
   - Pelo menos um número
   - Pelo menos um caractere especial (!@#$%&*)

Importante: A senha não pode ser igual às 5 últimas senhas utilizadas.

Em caso de dúvidas ou problemas, entre em contato com o suporte através do ramal 2020."""
    },
    {
        "title": "Solicitar Novo Computador",
        "category": "Hardware",
        "content": """Para solicitar um novo computador ou notebook, siga o procedimento:

1. Acesse o sistema GLPI em glpi.empresa.com
2. Faça login com suas credenciais da rede
3. Clique em "Novo Chamado"
4. Selecione a categoria: Hardware > Solicitação de Equipamento
5. Preencha o formulário com:
   - Tipo de equipamento necessário (Desktop/Notebook)
   - Justificativa detalhada da necessidade
   - Especificações mínimas requeridas (se houver)
   - Centro de custo
   - Aprovação prévia do gestor (anexar email)

Importante: Solicitações sem aprovação do gestor serão automaticamente recusadas.

Prazo médio de atendimento: 15 dias úteis após aprovação.
Em casos urgentes, mencione no campo de observações."""
    },
    {
        "title": "Configurar VPN da Empresa",
        "category": "Rede",
        "content": """Para configurar o acesso VPN e trabalhar remotamente:

Pré-requisitos:
- Ter VPN liberada pelo seu gestor
- Computador corporativo ou pessoal autorizado

Passos de instalação:

1. Baixar o cliente VPN:
   - Acesse vpn.empresa.com/download
   - Escolha a versão para seu sistema operacional
   - Baixe o Cisco AnyConnect

2. Instalação:
   - Execute o instalador baixado
   - Siga o assistente de instalação (Next, Next, Install)
   - Aguarde a conclusão

3. Configuração:
   - Abra o Cisco AnyConnect
   - No campo servidor, digite: vpn.empresa.com
   - Clique em "Connect"

4. Autenticação:
   - Usuário: mesmo login do Windows (sem domínio)
   - Senha: mesma senha do Windows
   - Se tiver autenticação de dois fatores, informe o código do token

Dica: Marque "Salvar servidor" para não precisar digitar toda vez.

Problemas comuns:
- Erro "Connection timeout": Verifique sua conexão com a internet
- Erro "Invalid credentials": Confira usuário e senha
- VPN conecta mas não acessa recursos: Entre em contato com TI (ramal 2020)"""
    },
    {
        "title": "Acesso ao Sistema ERP",
        "category": "Sistemas",
        "content": """Para obter acesso ao sistema ERP da empresa:

Requisitos:
- Ser funcionário efetivo
- Ter necessidade comprovada pelo cargo/função
- Aprovação do gestor imediato

Procedimento:

1. Preparar informações:
   - Nome completo
   - Matrícula
   - Departamento
   - Cargo
   - Módulos do ERP necessários (Financeiro, Estoque, etc)
   - Justificativa detalhada

2. Solicitar aprovação:
   - Envie email para seu gestor solicitando aprovação
   - Peça que ele responda autorizando explicitamente

3. Abrir chamado:
   - Acesse glpi.empresa.com
   - Categoria: Sistemas > Solicitação de Acesso
   - Anexe o email de aprovação do gestor
   - Preencha todas as informações solicitadas

4. Aguardar liberação:
   - Prazo: até 2 dias úteis após aprovação
   - Você receberá email com usuário e senha temporária
   - Na primeira vez, será solicitado alterar a senha

Treinamento:
O RH oferece treinamento básico do ERP toda segunda-feira às 14h.
Inscreva-se através do portal de treinamentos."""
    },
    {
        "title": "Resolver Problemas com Impressora",
        "category": "Hardware",
        "content": """Quando a impressora não estiver funcionando, siga este checklist:

VERIFICAÇÕES BÁSICAS:

1. Física:
   - Impressora está ligada?
   - Tem papel na bandeja?
   - Toner/cartucho não está vazio?
   - Cabos estão bem conectados?

2. Rede:
   - Impressora está conectada na rede?
   - LED de rede está aceso?
   - Teste ping: ping nome-impressora

3. No computador:
   - A impressora aparece em "Dispositivos e Impressoras"?
   - Há trabalhos travados na fila de impressão?

SOLUÇÕES COMUNS:

Problema: "Impressora offline"
Solução:
1. Painel de Controle > Dispositivos e Impressoras
2. Clique com botão direito na impressora
3. Desmarque "Usar impressora offline"

Problema: "Fila de impressão travada"
Solução:
1. Clique com botão direito na impressora
2. "Ver o que está sendo impresso"
3. Menu Impressora > Cancelar todos os documentos
4. Aguarde alguns segundos e tente imprimir novamente

Problema: "Impressora não aparece"
Solução:
1. Painel de Controle > Dispositivos e Impressoras
2. Adicionar impressora
3. Selecione "Adicionar impressora de rede"
4. Escolha a impressora da lista
5. Se não aparecer, clique em "A impressora desejada não está na lista"
6. Digite: \\\\servidor-impressao\\nome-impressora

Se nenhuma solução funcionar:
- Abra chamado no GLPI categoria "Hardware > Impressoras"
- Informe o nome/localização da impressora
- Descreva o problema detalhadamente"""
    },
    {
        "title": "Acessar Sistema de Ponto Eletrônico",
        "category": "Sistemas",
        "content": """Para acessar e utilizar o sistema de ponto eletrônico:

ACESSO WEB:

1. Acesse: ponto.empresa.com
2. Login: seu CPF (somente números)
3. Senha: mesma senha do email corporativo

FUNCIONALIDADES:

Registrar Ponto:
- Na tela inicial, clique em "Bater Ponto"
- Confirme o horário exibido
- O registro é instantâneo

Consultar Espelho de Ponto:
- Menu > Espelho de Ponto
- Selecione o mês desejado
- Visualize todos os registros
- Botão "Exportar PDF" para salvar

Justificar Ausências/Atrasos:
- Menu > Solicitações > Nova Justificativa
- Selecione a data
- Tipo de justificativa (atestado, compensação, etc)
- Anexe comprovante se necessário
- Aguarde aprovação do gestor

Solicitar Ajuste de Ponto:
- Menu > Solicitações > Ajuste de Ponto
- Informe data, horário correto e motivo
- Sujeito à aprovação do gestor

APLICATIVO MÓVEL:

Disponível na Play Store e App Store
Nome: "Ponto Empresa"
Use as mesmas credenciais do acesso web

IMPORTANTE:
- Horário de trabalho: 8h às 18h (1h almoço)
- Tolerância: 10 minutos
- Banco de horas funciona por compensação mensal
- Faltas não justificadas serão descontadas

Dúvidas sobre fechamento de ponto:
Contate o RH pelo ramal 3030"""
    }
]


def populate_database():
    """Popula o banco com documentos iniciais."""

    logger.info("=" * 70)
    logger.info("INICIANDO POPULAÇÃO DA BASE DE CONHECIMENTO")
    logger.info("=" * 70)

    # Verificar estado atual
    try:
        info = vector_store_service.get_collection_info()
        logger.info(f"\n📊 Estado atual da collection:")
        logger.info(f"   Nome: {info['name']}")
        logger.info(f"   Documentos: {info['vectors_count']}")
        logger.info(f"   Dimensões: {info['vector_size']}")

        if info['vectors_count'] > 0:
            response = input(
                f"\n⚠️  A collection já tem {info['vectors_count']} documentos. Deseja limpar e recriar? (s/N): ")
            if response.lower() == 's':
                logger.info("🗑️  Limpando collection...")
                # Deletar e recriar
                from qdrant_client import QdrantClient
                from app.core.config import get_settings
                settings = get_settings()
                client = QdrantClient(host=settings.qdrant_host, port=settings.qdrant_port)
                client.delete_collection(settings.qdrant_collection)
                logger.info("✓ Collection deletada")

                # Recriar
                vector_store_service._ensure_collection()
                logger.info("✓ Collection recriada")
            else:
                logger.info("Mantendo documentos existentes...")
    except Exception as e:
        logger.error(f"Erro ao verificar collection: {e}")
        return

    # Inserir documentos
    logger.info(f"\n📝 Inserindo {len(INITIAL_DOCUMENTS)} documentos...\n")

    success_count = 0
    error_count = 0

    for i, doc_data in enumerate(INITIAL_DOCUMENTS, 1):
        try:
            # Criar documento
            document = DocumentCreate(**doc_data)

            # Gerar embedding
            logger.info(f"[{i}/{len(INITIAL_DOCUMENTS)}] Processando: {document.title}")
            vector = embedding_service.encode_text(document.content)

            # Adicionar ao Qdrant
            doc_id = vector_store_service.add_document(
                document=document,
                vector=vector
            )

            logger.info(f"   ✓ Inserido com ID: {doc_id}")
            success_count += 1

        except Exception as e:
            logger.error(f"   ✗ Erro: {e}")
            error_count += 1

    # Resumo
    logger.info("\n" + "=" * 70)
    logger.info("RESUMO DA POPULAÇÃO")
    logger.info("=" * 70)
    logger.info(f"✓ Sucesso: {success_count}")
    logger.info(f"✗ Erros: {error_count}")

    # Verificar resultado final
    info = vector_store_service.get_collection_info()
    logger.info(f"\n📊 Estado final:")
    logger.info(f"   Total de documentos: {info['vectors_count']}")
    logger.info("=" * 70)

    if success_count > 0:
        logger.info("\n✅ Base de conhecimento populada com sucesso!")
        logger.info("🚀 Agora você pode testar o endpoint /chat")
    else:
        logger.error("\n❌ Nenhum documento foi inserido!")


if __name__ == "__main__":
    try:
        populate_database()
    except KeyboardInterrupt:
        logger.info("\n\n⚠️  Operação cancelada pelo usuário")
    except Exception as e:
        logger.error(f"\n❌ Erro fatal: {e}", exc_info=True)