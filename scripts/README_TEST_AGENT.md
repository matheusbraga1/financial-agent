# 🤖 Financial Agent - Script de Teste Interativo

Script completo e bonito para testar o Financial Agent no terminal antes de implementar o frontend.

## 🚀 Como Usar

### Instalação de Dependências

O script instala automaticamente as dependências necessárias (`httpx` e `rich`) na primeira execução, mas você pode instalá-las manualmente:

```bash
pip install httpx rich
```

### Iniciar o Backend

Antes de usar o script, certifique-se de que o backend está rodando:

```bash
python -m uvicorn app.main:app --reload
```

### Executar o Script

#### Modo Padrão (Streaming)
```bash
python scripts/test_agent.py
```

#### Modo Síncrono (sem streaming)
```bash
python scripts/test_agent.py --no-stream
```

#### Conectar a outro servidor
```bash
python scripts/test_agent.py --url http://192.168.1.100:8000
```

---

## 📚 Comandos Disponíveis

Durante o chat, você pode usar os seguintes comandos especiais:

| Comando | Descrição |
|---------|-----------|
| `/quit`, `/exit` | Sair do chat |
| `/clear` | Limpar histórico e iniciar nova conversa |
| `/history` | Ver histórico completo da conversa |
| `/stats` | Mostrar estatísticas da última resposta |
| `/sources` | Ver fontes detalhadas da última resposta |
| `/mode` | Alternar entre streaming e síncrono |
| `/help` | Mostrar ajuda |

---

## ✨ Funcionalidades

### 🎨 Interface Bonita
- Interface colorida usando Rich
- Exibição de markdown nas respostas
- Tabelas e painéis estilizados
- Emojis para melhor visualização
- Progress indicators

### 🔄 Dois Modos de Operação

#### Modo Streaming (Padrão)
- Respostas em tempo real (token por token)
- Melhor experiência de usuário
- Feedback imediato
- Baixa latência percebida

#### Modo Síncrono
- Aguarda resposta completa
- Melhor para análise detalhada
- Progress spinner durante processamento

### 📊 Estatísticas Detalhadas

O comando `/stats` mostra:
- ⏱️ Tempo de sessão
- 📈 Total de perguntas
- 📚 Fontes consultadas
- 🤖 Modelo usado
- 🎯 Confiança da resposta (com código de cores)

### 📑 Fontes e Contexto

O comando `/sources` exibe:
- Tabela com todas as fontes consultadas
- Score de relevância de cada fonte
- Preview do conteúdo da melhor fonte
- Categorias das fontes

### 📜 Histórico Completo

O comando `/history` mostra:
- Todas as perguntas e respostas da sessão
- Formato markdown nas respostas
- Confiança e fontes de cada resposta
- Navegação fácil pela conversa

---

## 🎯 Indicadores de Confiança

O script usa emojis para indicar a confiança da resposta:

- 🟢 **Verde** (≥ 70%): Alta confiança
- 🟡 **Amarelo** (50-70%): Média confiança
- 🔴 **Vermelho** (< 50%): Baixa confiança

---

## 💡 Exemplos de Uso

### Sessão Básica

```bash
$ python scripts/test_agent.py

╔════════════════════════════════════════════════════════════════╗
║  Financial Agent - Terminal Interativo                         ║
╚════════════════════════════════════════════════════════════════╝

URL: http://localhost:8000
Modo: Streaming ✓
Sessão: Nova conversa
Perguntas: 0

Comandos: /help (ajuda) | /quit (sair) | /clear (limpar) | /stats (estatísticas)
────────────────────────────────────────────────────────────────

✨ Chat iniciado! Digite sua pergunta ou /help para ajuda.

> Como faço para resetar minha senha?

👤 Você: Como faço para resetar minha senha?

🤖 Assistente: Para resetar sua senha, siga os seguintes passos:

1. Acesse a página de login
2. Clique em "Esqueci minha senha"
3. Digite seu e-mail cadastrado
4. Verifique sua caixa de entrada...

🟢 Confiança: 85.3% | Fontes: 3

> /sources

📚 Fontes Consultadas (3)
┏━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━┳━━━━━━━━┓
┃ # ┃ Título                   ┃ Categoria   ┃ Score  ┃
┡━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━╇━━━━━━━━┩
│ 1 │ Recuperação de Senha     │ TI/Suporte  │ 92.5%  │
│ 2 │ Manual do Usuário        │ TI/Docs     │ 78.2%  │
│ 3 │ FAQ - Acesso ao Sistema  │ TI/FAQ      │ 65.1%  │
└───┴──────────────────────────┴─────────────┴────────┘

📄 Preview da Melhor Fonte
┌────────────────────────────────────────┐
│ Para recuperar sua senha, acesse o     │
│ portal e clique em "Esqueci minha      │
│ senha". Um e-mail será enviado com...  │
└────────────────────────────────────────┘

> /quit

👋 Encerrando chat...
Total de perguntas: 1
Duração da sessão: 0:02:15
```

### Alternar Modos

```bash
> /mode

✓ Modo alterado para: Síncrono

> Qual o horário de funcionamento?

👤 Você: Qual o horário de funcionamento?

⠋ Processando sua pergunta...

🤖 Assistente: Nosso horário de funcionamento é...
```

---

## 🐛 Troubleshooting

### Erro de Conexão

Se você ver:
```
❌ Erro: Não foi possível conectar ao servidor em http://localhost:8000
```

**Solução:**
1. Certifique-se de que o backend está rodando:
   ```bash
   python -m uvicorn app.main:app --reload
   ```
2. Verifique se a porta 8000 está livre
3. Tente usar `--url` com outra URL

### Timeout

Se você ver:
```
❌ Erro: Timeout ao aguardar resposta do servidor
```

**Solução:**
1. Verifique sua conexão com o backend
2. O modelo pode estar demorando - tente usar modo síncrono
3. Aumente o timeout no código se necessário

### Encoding no Windows

Se você ver caracteres estranhos no Windows, o script já trata isso automaticamente, mas certifique-se de usar um terminal moderno (Windows Terminal é recomendado).

---

## 🔧 Customização

### Alterar Timeouts

Edite estas linhas no script:

```python
# Para requisições síncronas
timeout_config = httpx.Timeout(10.0, read=120.0)

# Para streaming
timeout_config = httpx.Timeout(10.0, read=300.0)
```

### Alterar Número de Fontes Exibidas

```python
# Na função print_sources(), altere:
for i, source in enumerate(self.last_sources[:10], 1):  # Mostra 10
```

### Alterar Preview de Conteúdo

```python
# Na função print_sources(), altere:
content_preview = best_source.get("content", "")[:200]  # 200 caracteres
```

---

## 📝 Notas

- O script mantém o histórico da conversa localmente (não persiste entre execuções)
- Use `/clear` para iniciar uma nova conversa sem reiniciar o script
- O modo streaming é recomendado para melhor experiência
- Todas as respostas em markdown são renderizadas corretamente

---

## 🎯 Próximos Passos

Este script é perfeito para:
1. ✅ Testar o backend antes de implementar o frontend
2. ✅ Validar respostas do agente
3. ✅ Debugar problemas de integração
4. ✅ Demonstrar funcionalidades
5. ✅ Treinar o modelo com feedback real

Quando o frontend estiver pronto, você pode usar este script como referência para:
- Implementar a lógica de streaming
- Exibir fontes e confiança
- Gerenciar sessões
- Tratar erros adequadamente

---

## 📞 Suporte

Se encontrar problemas:
1. Verifique os logs do backend
2. Use `/help` para ver comandos disponíveis
3. Teste com `/mode` para alternar entre streaming e síncrono
4. Use `--url` para verificar se está conectando no servidor correto

---

**Desenvolvido para testar o Financial Agent de forma completa e profissional! 🚀**
