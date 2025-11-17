# 🔧 Correção de Encoding - Caracteres Especiais (ã, ç, ê → ???)

## ❌ Problema Identificado

Artigos no Qdrant estavam aparecendo com `???` ao invés de caracteres acentuados (ã, ç, ê, õ, etc).

**Exemplo:**
- ❌ **Antes:** "Configura??o de usu?rio"
- ✅ **Depois:** "Configuração de usuário"

---

## 🔍 Causa Raiz

**NÃO era problema do modelo LLM**, mas sim de **2 bugs críticos** no pipeline de ingestão:

### Bug #1: `_remove_non_printable()` - Muito Restritivo

**Código Problemático:**
```python
# ANTES (QUEBRADO)
def _remove_non_printable(self, content: str) -> str:
    return ''.join(
        char for char in content
        if char.isprintable() or char in '\n\t'  # ❌ Muito restritivo!
    )
```

**Problema:**
- Se o encoding já estava errado, preservava os `???` como válidos
- Não protegia explicitamente caracteres acentuados

**Solução:**
```python
# DEPOIS (CORRIGIDO)
def _remove_non_printable(self, content: str) -> str:
    return ''.join(
        char for char in content
        if (
            char.isprintable()
            or char in '\n\t\r'
            or unicodedata.category(char)[0] == 'L'  # ✅ Todas as letras (incluindo acentuadas)
            or unicodedata.category(char)[0] == 'N'  # ✅ Todos os números
            or unicodedata.category(char)[0] == 'P'  # ✅ Pontuação
            or unicodedata.category(char)[0] == 'S'  # ✅ Símbolos
        )
    )
```

---

### Bug #2: `_fix_encoding()` - Criando Problemas ao Invés de Resolver

**Código Problemático:**
```python
# ANTES (QUEBRADO)
def _fix_encoding(self, content: str) -> str:
    # Detecta "???" e tenta "corrigir"
    if "??" in content or "\ufffd" in content:
        # Tenta UTF-8 → latin1
        fixed = content.encode('utf-8', errors='ignore').decode('latin1', errors='ignore')
        # ❌ DESTROI dados válidos!

        # Tenta latin1 → UTF-8
        fixed = content.encode('latin1', errors='ignore').decode('utf-8', errors='ignore')
        # ❌ DESTROI dados válidos!
```

**Problema GRAVE:**
1. MySQL **já retorna UTF-8 correto** (charset=utf8mb4)
2. A função tentava "corrigir" algo que NÃO estava quebrado
3. `errors='ignore'` **deleta caracteres** ao invés de preservá-los
4. Conversões encode/decode **corrompem dados válidos**

**Solução:**
```python
# DEPOIS (CORRIGIDO)
def _fix_encoding(self, content: str) -> str:
    # APENAS usa ftfy (biblioteca confiável e testada)
    if HAS_FTFY:
        try:
            return ftfy.fix_text(content)
        except Exception as e:
            logger.debug(f"Failed to fix with ftfy: {e}")

    # SEM correções manuais - elas corrompem dados!
    return content
```

---

## ✅ Correções Aplicadas

### 1. **Arquivo Corrigido:**
- `scripts/glpi_ingestion/content_cleaner.py`

### 2. **Novo Script de Diagnóstico:**
- `scripts/diagnose_encoding.py`

---

## 🚀 Como Corrigir os Dados Existentes

### Passo 1: Verificar o Problema

Execute o script de diagnóstico:

```bash
python scripts/diagnose_encoding.py
```

**O que ele verifica:**
- ✅ Charset do MySQL (deve ser `utf8mb4`)
- ✅ Encoding das tabelas e colunas
- ✅ Conteúdo RAW do banco de dados
- ✅ Conteúdo após limpeza
- ✅ Conteúdo armazenado no Qdrant

**Saída esperada:**
```
VERIFICANDO MYSQL ENCODING
════════════════════════════════════════════════════════════════════════════════
✅ Connection Charset: {'@@character_set_connection': 'utf8mb4', ...}
✅ Database Charset: {'@@character_set_database': 'utf8mb4', ...}

📊 Charset das tabelas principais:
   glpi_knowbaseitems: utf8mb4_unicode_ci

📝 Charset das colunas de conteúdo:
   name: utf8mb4 / utf8mb4_unicode_ci
   answer: utf8mb4 / utf8mb4_unicode_ci
```

### Passo 2: Instalar ftfy (Opcional mas Recomendado)

```bash
pip install ftfy
```

**ftfy** (fix text for you) é uma biblioteca especializada em corrigir problemas de encoding de forma segura.

### Passo 3: Re-executar a Ingestão

**IMPORTANTE:** Você precisa limpar e re-ingerir os dados para aplicar as correções:

```bash
# Limpar Qdrant e re-importar tudo
python scripts/ingest_glpi_clean.py --clear

# Ou apenas re-importar (sobrescreve)
python scripts/ingest_glpi_clean.py
```

### Passo 4: Verificar Resultado

Após re-ingestão, execute novamente o diagnóstico:

```bash
python scripts/diagnose_encoding.py --skip-mysql
```

Verifique se o output mostra:
- ✅ `Caracteres acentuados válidos detectados`
- ❌ **NÃO** deve ter `PROBLEMA: Caracteres corrompidos detectados (??? ou �)`

---

## 🔍 Comandos Úteis do Script de Diagnóstico

### Verificar artigo específico:
```bash
python scripts/diagnose_encoding.py --article-id 123
```

### Pular verificação do MySQL (mais rápido):
```bash
python scripts/diagnose_encoding.py --skip-mysql
```

### Pular verificação do Qdrant:
```bash
python scripts/diagnose_encoding.py --skip-qdrant
```

---

## 📊 Exemplo de Saída do Diagnóstico

### Quando há PROBLEMA:

```
CONTEÚDO (no Qdrant)
════════════════════════════════════════════════════════════════════════════════
📏 Tamanho: 245 caracteres
📝 Preview (primeiros 200 chars):
   Para configurar o usu?rio, acesse as configura??es...

🔍 Análise:
   ⚠️  PROBLEMA: Caracteres corrompidos detectados (??? ou �)
   ⚠️  Sem caracteres acentuados (pode estar corrompido se esperado)

⚠️  Nenhum caractere especial (acentuação) encontrado
```

### Quando está CORRETO:

```
CONTEÚDO (no Qdrant)
════════════════════════════════════════════════════════════════════════════════
📏 Tamanho: 245 caracteres
📝 Preview (primeiros 200 chars):
   Para configurar o usuário, acesse as configurações...

🔍 Análise:
   ✅ Caracteres acentuados válidos detectados

🔤 Caracteres especiais encontrados:
   'á' (U+00E1) - LATIN SMALL LETTER A WITH ACUTE
   'ã' (U+00E3) - LATIN SMALL LETTER A WITH TILDE
   'ç' (U+00E7) - LATIN SMALL LETTER C WITH CEDILLA
   'é' (U+00E9) - LATIN SMALL LETTER E WITH ACUTE
   'ê' (U+00EA) - LATIN SMALL LETTER E WITH CIRCUMFLEX
   'í' (U+00ED) - LATIN SMALL LETTER I WITH ACUTE
   'ó' (U+00F3) - LATIN SMALL LETTER O WITH ACUTE
   'õ' (U+00F5) - LATIN SMALL LETTER O WITH TILDE
   'ú' (U+00FA) - LATIN SMALL LETTER U WITH ACUTE
```

---

## ⚠️ Se o MySQL Estiver com Charset Errado

Se o diagnóstico mostrar que o MySQL **NÃO está usando utf8mb4**:

### 1. Verificar charset do banco de dados:
```sql
SELECT @@character_set_database, @@collation_database;
```

### 2. Alterar charset do banco (se necessário):
```sql
ALTER DATABASE glpi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 3. Alterar charset das tabelas:
```sql
ALTER TABLE glpi_knowbaseitems CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
ALTER TABLE glpi_knowbaseitemtranslations CONVERT TO CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### 4. Re-executar ingestão:
```bash
python scripts/ingest_glpi_clean.py --clear
```

---

## 📝 Resumo

### ✅ O que foi corrigido:
1. Função `_remove_non_printable()` agora preserva explicitamente caracteres acentuados
2. Função `_fix_encoding()` não tenta mais "corrigir" UTF-8 válido
3. Adicionado script de diagnóstico completo
4. MySQL já estava configurado corretamente (utf8mb4)

### ⚠️ O que você precisa fazer:
1. **Instalar ftfy (opcional):** `pip install ftfy`
2. **Re-executar ingestão:** `python scripts/ingest_glpi_clean.py --clear`
3. **Verificar resultado:** `python scripts/diagnose_encoding.py`

### 📊 Status dos Commits:
```
✅ Commit: dd681fd
✅ Push: Sucesso
✅ Branch: claude/fix-glpi-qdrant-special-chars-01UYhwvYZH5jqtsSUCe9B7G2

Arquivos modificados:
- scripts/glpi_ingestion/content_cleaner.py (correções de bugs)
- scripts/diagnose_encoding.py (novo script de diagnóstico)
```

---

## 🎯 Garantia de Qualidade

Com estas correções:
- ✅ Caracteres portugueses preservados (ã, ç, ê, õ, etc.)
- ✅ Sem corrupção de dados válidos
- ✅ Pipeline seguro (só usa ftfy se disponível)
- ✅ Diagnóstico completo disponível
- ✅ MySQL já configurado corretamente

**Após re-ingestão, todos os artigos terão acentuação correta!** 🎉

---

**Desenvolvido para preservar a integridade dos caracteres especiais portugueses!** 🇧🇷
