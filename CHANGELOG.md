# CHANGELOG — Sealed Arbitrage Scanner

Registro datado de mudanças relevantes. O repo não usa versionamento semântico
(SemVer); as entradas são por data. Fonte única de estado segue o `README.md`.

## 2026-06-17 — Entrega via `snapshot.py` vira convenção OBRIGATÓRIA

- **`scripts/snapshot.py` reescrito** pra ser o gerador canônico da entrega:
  - Passa a ler o **`unified_deals.csv`** (saída de `run_all_sources.py`), que é
    o que o orquestrador realmente produz — antes lia só os CSV por bucket
    (`real_opportunities.csv` etc.) que o `run_all_sources.py` **não** escreve,
    forçando tabela montada à mão. Modo legado por-bucket preservado via `--all`.
  - **Adiciona a coluna `Qtd disponível`** (invariante #2) na tabela de entrega —
    estava ausente.
  - Mantém os **dois links clicáveis verificáveis** por linha: anúncio BR (`URL`)
    + página TCGPlayer de referência (`tcgplayer_product_id` do registry).
  - Nova seção **🟢🟡 Deals acionáveis** com **todos** os GREEN/YELLOW (sem curar)
    + **flag ⚠️** e motivo nos deals que precisam de conferência manual (match
    ambíguo YELLOW / margem-variante anômala).
  - `--scan-dir` aponta uma run específica; default = `results/unified_*` mais recente.
- **README invariante #7 reescrito**: entrega = tabela no chat **gerada via
  `snapshot.py`, NUNCA à mão**; nova seção "Entrega da tabela no chat (OBRIGATÓRIO
  via snapshot.py)" com comando literal, colunas, links e regra de XLSX-sob-demanda.
  `snapshot.py` entra como passo 3 da sequência canônica; XLSX vira passo 4 opcional.
- **RUNBOOK** atualizado: entrega padrão = tabela no chat via `snapshot.py`; XLSX
  condensado/Drive passam a ser explicitamente "só quando o operador pedir o arquivo".
- XLSX sob demanda (`build_delivery_xlsx.py`) **preservado** — o selado é o caso de
  uso real em que o operador pede o arquivo pra importar em lote.
