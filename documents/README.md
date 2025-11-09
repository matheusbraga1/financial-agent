# 📁 Documentos Multi-Domínio

Este diretório contém documentos de todos os departamentos da empresa que serão indexados pelo Agente de IA.

## 📂 Estrutura de Diretórios

```
documents/
├── TI/                     # Tecnologia da Informação
│   ├── policies/          # Políticas de TI
│   ├── procedures/        # Procedimentos técnicos
│   ├── manuals/           # Manuais de sistemas
│   └── guides/            # Guias e tutoriais
│
├── RH/                     # Recursos Humanos
│   ├── policies/          # Políticas de RH
│   ├── procedures/        # Procedimentos de RH
│   └── forms/             # Formulários
│
├── Financeiro/            # Financeiro
│   ├── policies/          # Políticas financeiras
│   ├── procedures/        # Procedimentos contábeis
│   └── guides/            # Guias de reembolso, etc.
│
├── Loteamento/            # Loteamento
│   ├── policies/          # Políticas de loteamento
│   ├── procedures/        # Procedimentos de aprovação
│   └── manuals/           # Manuais técnicos
│
├── Aluguel/               # Locação
│   ├── contracts/         # Modelos de contrato
│   ├── procedures/        # Procedimentos de locação
│   └── forms/             # Formulários
│
├── Juridico/              # Jurídico
│   ├── contracts/         # Modelos de contrato
│   ├── policies/          # Políticas legais
│   └── procedures/        # Procedimentos jurídicos
│
└── Geral/                 # Documentos gerais
    └── policies/          # Políticas corporativas gerais
```

## 📝 Formatos Suportados

- ✅ **PDF** (.pdf) - Documentos Adobe PDF
- ✅ **Word** (.docx) - Documentos Microsoft Word
- ✅ **Texto** (.txt) - Arquivos de texto simples
- ✅ **HTML** (.html, .htm) - Páginas HTML

## 🔍 Como o Sistema Funciona

### 1. Classificação Automática

Quando um usuário faz uma pergunta, o sistema:

1. **Detecta o domínio** automaticamente usando palavras-chave
2. **Filtra documentos** apenas do(s) departamento(s) relevante(s)
3. **Retorna resposta** mais precisa e focada

**Exemplos:**

| Pergunta | Departamentos Detectados |
|----------|-------------------------|
| "Como resetar minha senha?" | TI |
| "Como tirar férias?" | RH |
| "Como solicitar reembolso?" | Financeiro |
| "Qual prazo de pagamento de férias?" | RH, Financeiro |
| "Como registrar um lote?" | Loteamento |

### 2. Metadados Automáticos

Os metadados são detectados automaticamente pela estrutura de diretórios:

**Exemplo:** `documents/TI/policies/seguranca_informacao.pdf`

```python
{
    "department": "TI",
    "doc_type": "policy",
    "title": "Segurança Informação",
    "file_format": "pdf"
}
```

## 🚀 Como Adicionar Novos Documentos

### Passo 1: Organize o Arquivo

Coloque o arquivo no diretório correto seguindo o padrão:
```
documents/{Departamento}/{TipoDocumento}/nome_do_arquivo.ext
```

**Tipos de Documento:**
- `policies` → Políticas corporativas
- `procedures` → Procedimentos operacionais
- `contracts` → Contratos e modelos
- `manuals` → Manuais técnicos
- `guides` → Guias e tutoriais
- `forms` → Formulários
- `faq` → Perguntas frequentes

### Passo 2: Executar Ingestão

```bash
# Ativar ambiente virtual
venv\Scripts\activate

# Ingerir todos os documentos
python scripts/ingest_documents.py

# Ingerir apenas um departamento
python scripts/ingest_documents.py --department TI

# Limpar e reingerir tudo
python scripts/ingest_documents.py --clear

# Visualizar o que seria processado (sem inserir)
python scripts/ingest_documents.py --dry-run
```

### Passo 3: Verificar Ingestão

```bash
# Ver estatísticas da coleção
python scripts/show_stats.py

# Testar busca
python scripts/test_chat_interactive.py
```

## ⚙️ Configurações Avançadas

### Tamanho de Chunks

Por padrão, documentos são divididos em chunks de 500 caracteres com overlap de 50.

Para ajustar:

```bash
python scripts/ingest_documents.py --chunk-size 800 --chunk-overlap 100
```

**Recomendações:**
- Documentos técnicos densos: `chunk-size=300`
- Políticas e procedimentos: `chunk-size=500` (padrão)
- Manuais longos: `chunk-size=800`

### Atualizar Documentos Existentes

Para atualizar um documento já indexado:

1. Substitua o arquivo no diretório
2. Execute a ingestão com `--clear` (reindexar tudo):

```bash
python scripts/ingest_documents.py --clear
```

Ou para atualizar apenas um departamento:

```bash
python scripts/ingest_documents.py --clear --department RH
```

## 📊 Boas Práticas

### Nomenclatura de Arquivos

✅ **Bom:**
- `politica_ferias_2024.pdf`
- `procedimento_reembolso_despesas.docx`
- `manual_vpn_forticlient.pdf`

❌ **Evitar:**
- `doc1.pdf`
- `ARQUIVO FINAL FINAL.docx`
- `sem-espacos-e-muito-longo-demais.pdf`

### Organização

1. **Mantenha estrutura consistente** - Sempre use a hierarquia departamento/tipo
2. **Evite duplicatas** - Remova versões antigas antes de adicionar novas
3. **Nomes descritivos** - Use nomes que descrevam o conteúdo
4. **Formatos adequados** - Prefira PDF para documentos finais, DOCX para editáveis

### Qualidade do Conteúdo

1. **Texto legível** - PDFs com OCR ruim prejudicam a busca
2. **Estrutura clara** - Use títulos, listas e parágrafos bem formatados
3. **Conteúdo objetivo** - Evite texto muito genérico ou vago
4. **Atualização regular** - Remova documentos obsoletos

## 🔧 Troubleshooting

### Problema: Arquivo não foi indexado

**Possíveis causas:**
1. Formato não suportado
2. Arquivo corrompido ou vazio
3. PDF sem texto (só imagens)

**Solução:**
```bash
# Testar com dry-run
python scripts/ingest_documents.py --dry-run

# Ver logs detalhados
python scripts/ingest_documents.py 2>&1 | tee ingestao.log
```

### Problema: Busca retorna documentos errados

**Possíveis causas:**
1. Documento no diretório errado
2. Palavras-chave muito genéricas
3. Chunk size muito grande

**Solução:**
1. Verificar estrutura de diretórios
2. Ajustar chunk size para documentos específicos
3. Adicionar tags manualmente (editar script)

### Problema: Respostas misturando departamentos

**Causa:** Pergunta muito genérica ou ambígua

**Solução:**
- Usuário deve ser mais específico na pergunta
- Adicionar mais palavras-chave ao DomainClassifier

## 📈 Monitoramento

### Verificar Documentos Indexados

```python
# scripts/list_indexed_documents.py (criar este script)
from app.services.vector_store_service_extended import vector_store_service_extended

info = vector_store_service_extended.get_collection_info()
print(f"Total de chunks indexados: {info['vectors_count']}")
```

### Estatísticas por Departamento

```python
# Buscar todos os pontos e agrupar por departamento
from app.services.vector_store_service_extended import vector_store_service_extended

results = vector_store_service_extended.client.scroll(
    collection_name="artigos_glpi",
    limit=10000,
    with_payload=True,
    with_vectors=False
)

from collections import Counter
departments = Counter(point.payload.get("department") for point in results[0])
print(departments)
```

## 🎯 Próximos Passos

Após configurar a estrutura de documentos:

1. ✅ Adicionar documentos de cada departamento
2. ✅ Executar ingestão
3. ✅ Testar com perguntas reais
4. ✅ Ajustar classificação se necessário
5. ✅ Configurar processo de atualização periódica

---

**Dúvidas?** Consulte a documentação principal em [SETUP.md](../SETUP.md)
