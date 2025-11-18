# Scripts de Manutenção de Sessões

Este diretório contém scripts utilitários para manutenção e debug do sistema de sessões e histórico de chat.

## 📋 Scripts Disponíveis

### 1. cleanup_orphan_sessions.py
**Propósito:** Limpar sessões órfãs (user_ids que não existem mais na tabela users)

**Uso:**
```bash
python scripts/cleanup_orphan_sessions.py
```

**O que faz:**
- Identifica sessões com user_ids inexistentes
- Mostra detalhes das sessões órfãs
- Pergunta confirmação antes de deletar
- Remove sessões e mensagens órfãs (CASCADE)
- Mantém integridade referencial do banco

**Quando usar:**
- Após deletar usuários do sistema
- Ao migrar/restaurar bancos de dados
- Quando houver inconsistências de dados
- Para limpeza periódica

---

### 2. create_test_sessions.py
**Propósito:** Criar sessões e mensagens de teste para usuários existentes

**Uso:**
```bash
python scripts/create_test_sessions.py
```

**O que faz:**
- Busca usuários ativos no banco
- Cria 2 sessões por usuário
- Adiciona 4 mensagens por sessão (alternando user/assistant)
- Verifica se as sessões foram criadas corretamente

**Quando usar:**
- Para testes de desenvolvimento
- Para popular banco de dados vazio
- Para verificar funcionalidade de histórico
- Para demos e apresentações

---

## 🐛 Problema Identificado e Resolvido

### Sintoma
A API não estava retornando sessões para os usuários autenticados.

### Causa Raiz
Havia **sessões órfãs** no banco de dados:
- Sessões com `user_id` de usuários que não existem mais (IDs 14-24)
- Todos os usuários atuais (IDs 1-11) não tinham nenhuma sessão
- Violação de integridade referencial

### Como isso aconteceu
Possíveis cenários:
1. Usuários foram deletados mas sessões permaneceram
2. Bancos foram recriados/limpos em momentos diferentes
3. Foreign key constraints não estavam ativas durante inserções antigas
4. Testes deixaram dados órfãos

### Solução Aplicada
1. ✅ Identificadas 8 sessões órfãs (27 mensagens)
2. ✅ Limpeza completa das sessões órfãs
3. ✅ Criação de 10 sessões de teste (40 mensagens)
4. ✅ Verificação de funcionamento

### Estado Atual
```
✓ 11 usuários cadastrados
✓ 10 sessões ativas (2 por usuário de teste)
✓ 40 mensagens de teste
✓ Integridade referencial mantida
✓ API funcionando corretamente
```

---

## 📊 Estrutura do Banco de Dados

### Tabela: conversations
```sql
CREATE TABLE conversations (
    session_id TEXT PRIMARY KEY,
    user_id TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
```

### Tabela: messages
```sql
CREATE TABLE messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
    content TEXT,
    answer TEXT,
    sources_json TEXT,
    model_used TEXT,
    confidence REAL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(session_id) REFERENCES conversations(session_id) ON DELETE CASCADE
)
```

### Tabela: feedback
```sql
CREATE TABLE feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    message_id INTEGER NOT NULL,
    rating TEXT NOT NULL,
    comment TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY(session_id) REFERENCES conversations(session_id) ON DELETE CASCADE,
    FOREIGN KEY(message_id) REFERENCES messages(id) ON DELETE CASCADE
)
```

---

## 🔍 Endpoints de Sessões

### GET /api/v1/chat/sessions
Lista sessões do usuário autenticado com paginação

**Parâmetros:**
- `limit` (default: 20): Número de sessões por página
- `offset` (default: 0): Offset para paginação

**Resposta:**
```json
{
  "sessions": [
    {
      "session_id": "uuid",
      "created_at": "2025-11-18T...",
      "message_count": 4,
      "last_message": "Última mensagem..."
    }
  ],
  "total": 10,
  "limit": 20,
  "offset": 0,
  "has_more": false
}
```

### GET /api/v1/chat/history
Retorna histórico de uma sessão específica

**Parâmetros:**
- `session_id` (required): ID da sessão
- `limit` (default: 50): Limite de mensagens

### DELETE /api/v1/chat/sessions/{session_id}
Deleta uma sessão e todo seu histórico

---

## 🛠️ Manutenção Recomendada

### Diária
- Nenhuma ação necessária (purge automático configurado)

### Semanal
- Verificar crescimento do banco `chat_history.db`
- Monitorar uso de espaço em disco

### Mensal
- Executar `cleanup_orphan_sessions.py` se houver deletação de usuários
- Revisar retention policy (padrão: 90 dias)

### Antes de Deploy
- Backup dos bancos: `users.db`, `chat_history.db`, `auth.db`
- Verificar integridade referencial
- Testar endpoints de sessões

---

## 📚 Referências

- **Repositório:** `app/infrastructure/repositories/conversation_repository.py`
- **Use Case:** `app/application/use_cases/chat/manage_conversation_use_case.py`
- **Endpoints:** `app/presentation/api/v1/endpoints/chat.py`
