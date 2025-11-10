# Análise de Precisão do RAG e Plano de Melhorias

**Data da Análise:** 2025-11-09
**Testes Realizados:** 15 perguntas em 5 categorias
**Endpoint Testado:** POST /api/v1/chat/stream

---

## 📊 MÉTRICAS OBTIDAS

### Resultados Gerais
- **Total de testes:** 15 perguntas
- **Taxa de sucesso técnico:** 100% (0 erros HTTP)
- **Taxa de sucesso funcional:** 20% (3/15 retornaram fontes)

### Métricas de Confiança
- **Média:** 0.07 ⚠️ **CRÍTICO** (esperado: >0.6)
- **Mínima:** 0.00
- **Máxima:** 0.40
- **Abaixo de 0.5:** 15/15 (100%) ⚠️

### Métricas de Fontes
- **Média:** 0.5 documentos por resposta ⚠️ **CRÍTICO**
- **Sem fontes:** 12/15 (80%)
- **Com fontes:** 3/15 (20%)
  - Política de segurança: 5 docs (score 0.41)
  - Requisição de compra: 1 doc (score 0.22)
  - Trabalho remoto: 1 doc (score 0.25)

### Performance
- **Tempo médio:** 1.62s ✅ (bom)
- **Tempo mínimo:** 1.05s
- **Tempo máximo:** 4.45s

---

## 🔴 PROBLEMAS IDENTIFICADOS

### 1. BASE DE CONHECIMENTO VAZIA/INSUFICIENTE (Crítico)
**Sintoma:** 80% das perguntas sem fontes retornadas

**Evidências:**
- 12 de 15 perguntas retornam "Informação Não Disponível"
- Apenas 3 perguntas encontraram documentos relevantes
- Scores baixos mesmo quando encontra (0.22-0.41)

**Impacto:** **CRÍTICO** - Sistema não funcional para maioria dos casos

**Causa Raiz:**
- Qdrant collection provavelmente vazia ou com poucos docs
- Script de ingestão pode não ter sido executado
- Documentos podem não estar indexados corretamente

---

### 2. CONFIANÇA EXTREMAMENTE BAIXA (Crítico)
**Sintoma:** Média de 0.07, todas respostas <0.5

**Evidências:**
- Mesmo quando encontra fontes, confiança é baixa (máx 0.40)
- 12 respostas com confiança 0.00

**Impacto:** **CRÍTICO** - Usuários não confiarão nas respostas

**Causas Possíveis:**
- Embeddings não captura bem semântica em português
- Modelo de embedding genérico (não fine-tuned para domínio)
- Algoritmo de scoring de confiança muito conservador
- Falta de documentos relevantes impacta score

---

### 3. RESPOSTAS GENÉRICAS EXCESSIVAS (Alto)
**Sintoma:** 80% das respostas são templates "Informação Não Disponível"

**Evidências:**
```
## Informação Não Disponível
Desculpe, não tenho informações sobre esse assunto...
```

**Impacto:** **ALTO** - Experiência do usuário ruim

**Problema:**
- Fallback muito rápido para resposta genérica
- Não tenta estratégias alternativas (query expansion, etc.)

---

## 💡 PLANO DE MELHORIAS PRIORITÁRIAS

### FASE 1: CORREÇÃO CRÍTICA - Base de Conhecimento ⚠️

#### 1.1 Verificar/Popular Base Qdrant
```bash
# Verificar documentos indexados
python scripts/check_qdrant_status.py

# Re-executar ingestão se necessário
python scripts/ingest_documents.py
```

**Prioridade:** 🔴 CRÍTICA
**Tempo estimado:** 30 min
**Impacto esperado:** +60% em recall

#### 1.2 Validar Indexação
- Confirmar que documentos estão no Qdrant
- Verificar qualidade dos embeddings
- Testar busca manual por documentos

---

### FASE 2: OTIMIZAÇÃO DE PARÂMETROS 🔧

#### 2.1 Ajustar Threshold de Similaridade
```python
# Em app/core/config.py
min_similarity_score: float = 0.15  # Reduzir de 0.18 para 0.15
top_k_results: int = 15  # Aumentar de 10 para 15
```

**Justificativa:** Scores observados (0.22-0.41) indicam que threshold pode estar OK, mas top_k pode ser aumentado

**Prioridade:** 🟡 ALTA
**Tempo estimado:** 5 min
**Impacto esperado:** +15% em recall

#### 2.2 Implementar Query Expansion
```python
# Expandir perguntas com sinônimos/termos relacionados
"login" → ["login", "acesso", "entrar", "autenticação"]
"senha" → ["senha", "password", "credencial"]
```

**Prioridade:** 🟡 ALTA
**Tempo estimado:** 2h
**Impacto esperado:** +25% em recall

---

### FASE 3: MELHORIAS DE RESPOSTA 📝

#### 3.1 Implementar Fallback Inteligente
Em vez de resposta genérica, tentar:
1. Buscar com threshold menor (0.10)
2. Buscar apenas por keywords
3. Sugerir documentos relacionados mesmo com score baixo
4. Usar LLM para gerar resposta baseada em conhecimento geral

**Prioridade:** 🟢 MÉDIA
**Tempo estimado:** 3h
**Impacto esperado:** Melhor UX mesmo sem docs

#### 3.2 Melhorar Cálculo de Confiança
```python
def calculate_confidence(sources, llm_response):
    # Considerar:
    # - Score médio das fontes
    # - Número de fontes
    # - Overlap entre pergunta e resposta
    # - Certeza do LLM
    ...
```

**Prioridade:** 🟢 MÉDIA
**Tempo estimado:** 2h
**Impacto esperado:** Confiança mais realista

---

### FASE 4: EMBEDDINGS E MODELO 🤖

#### 4.1 Testar Modelo Embedding Multilingual Melhor
```python
# Testar modelos:
# - "intfloat/multilingual-e5-large" (atual - 1024 dim)
# - "sentence-transformers/paraphrase-multilingual-mpnet-base-v2" (768 dim)
# - "neuralmind/bert-base-portuguese-cased" (português específico)
```

**Prioridade:** 🟢 BAIXA
**Tempo estimado:** 4h (incluindo re-indexação)
**Impacto esperado:** +10-20% em qualidade de busca

#### 4.2 Fine-tuning do Embedding (Futuro)
Treinar modelo com pares pergunta-resposta do domínio

**Prioridade:** 🔵 FUTURO
**Tempo estimado:** 1-2 dias
**Impacto esperado:** +30-40% em qualidade

---

## 🎯 MELHORIAS IMEDIATAS A IMPLEMENTAR

### 1. Ajustar Parâmetros de Busca (5 min)
```python
# app/core/config.py
top_k_results: int = 15  # +50%
min_similarity_score: float = 0.12  # Mais permissivo
```

### 2. Adicionar Log de Debug (10 min)
```python
# Para entender o que está acontecendo
logger.debug(f"Query: {question}")
logger.debug(f"Sources found: {len(sources)}, scores: {[s.score for s in sources]}")
logger.debug(f"Top source: {sources[0].title if sources else 'None'}")
```

### 3. Implementar Resposta com Docs de Baixo Score (30 min)
```python
# Se não encontrar com threshold padrão, tentar mais permissivo
if not sources:
    sources = search(min_score=0.05, limit=5)
    if sources:
        response += "\n\n> Nota: Estas informações podem não ser totalmente relevantes."
```

---

## 📈 METAS PÓS-MELHORIAS

### Curto Prazo (após Fase 1 e 2)
- ✅ Recall > 70% (atualmente ~20%)
- ✅ Confiança média > 0.5 (atualmente 0.07)
- ✅ <30% respostas "Não Disponível" (atualmente 80%)

### Médio Prazo (após Fase 3)
- ✅ Recall > 85%
- ✅ Confiança média > 0.65
- ✅ <15% respostas genéricas

### Longo Prazo (após Fase 4)
- ✅ Recall > 90%
- ✅ Confiança média > 0.75
- ✅ <5% respostas genéricas

---

## 🔬 PRÓXIMOS PASSOS

1. **IMEDIATO:** Verificar se Qdrant tem documentos indexados
2. **HOJE:** Implementar melhorias das Fases 1 e 2
3. **ESTA SEMANA:** Fase 3 (Fallbacks)
4. **PRÓXIMA SEMANA:** Avaliar necessidade de Fase 4

---

## 📝 NOTAS TÉCNICAS

### Perguntas que Funcionaram (3/15)
1. ✅ "Qual a política de segurança..." → 5 docs, conf 0.40
2. ✅ "Como fazer requisição de compra?" → 1 doc, conf 0.31
3. ✅ "Política de trabalho remoto" → 1 doc, conf 0.33

### Padrão de Sucesso
- Perguntas mais específicas/técnicas
- Vocabulário que match com docs existentes
- Tópicos com docs específicos na base

### Perguntas que Falharam (12/15)
- Perguntas genéricas ("Como fazer login?")
- Tópicos sem docs específicos
- Vocabulário coloquial vs. técnico

---

**Conclusão:** Sistema tem potencial mas requer melhorias críticas na base de conhecimento e parâmetros de busca. Com as melhorias propostas, esperamos alcançar >70% de recall e confiança >0.5 em 1-2 dias de trabalho.
