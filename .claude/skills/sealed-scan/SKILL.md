---
name: sealed-scan
description: Use when the operator wants to run the sealed products arbitrage scanner ("roda o selados", "scan sealed", "roda o sealed scanner", "deals de selados", "roda o Liga selados", "selados da Liga", "panorama de selados"). O scanner tem 4 fontes BR (Liga, OLX, MercadoLivre, Amazon); ao pedir o scan, PERGUNTE qual fonte rodar (AskUserQuestion — Liga $0 é o default recomendado; Amazon é opt-in pago), rode via run_liga_local.py (só Liga) ou run_all_sources.py (multi-fonte), e entregue SEMPRE via scripts/snapshot.py — tabela markdown modelo MYP adaptado a selados, agrupada por produto, com Ref. Nacional (R$), Ref. TCG (US$→R$), Margem bruta % por linha e os dois links [oferta](BR) · [TCG](TCGplayer) em toda linha, colada VERBATIM no chat. Nunca montar tabela à mão.
---

# Sealed Products Scanner — caminho único de execução e entrega (multi-fonte)

## Overview

Um caminho só para "rodar o scanner de **produtos selados** (booster box, ETB,
fat pack, lata, blister, kit, pré-lançamento…) e me entregar no padrão": pergunte
a fonte, rode o pipeline, e entregue **sempre** via `scripts/snapshot.py`
(tabela markdown em R$, `Margem bruta %` por linha, dois links
`[oferta] · [TCG]`). **Nunca** remonte a tabela à mão. **Não** rode fonte solta
em diretório fora do repo (padrão heterogêneo antigo) — a saída canônica é
`results/unified_*/` dentro do repo.

**Repo canônico:** `~/sealed-arbitrage-scanner`
(`C:\Users\mathe\sealed-arbitrage-scanner`). Fonte de verdade do "como rodar" e
do contrato de entrega é o `CLAUDE.md` desse repo + o manual da frota
(`~/scanners-commons`) — se algo aqui divergir, o `CLAUDE.md` do repo manda.

> ⚠️ **Invariantes de SELADO (não negociar):**
> - **SEM PISO de preço** — o piso R$50 da frota vale só para singles. Selado:
>   `config.yaml → filters.min_brazil_price_brl: 0` (operador, 2026-06-27).
>   Único critério de GREEN é **margem bruta ≥ 30%**. NÃO reintroduza piso.
> - **Threshold é FRAÇÃO** (`0.30` em `deal_criteria.min_total_margin_pct`) —
>   convenção Selados/CardTrader/COMC; MYP/Liga-singles/eBay usam inteiro.
> - **Margem BRUTA pura**: `(Ref. TCG − preço BR) / preço BR`, sem frete/taxa/IOF.
> - Margem > 200% → RED `margem_anomala` (referência ou match provavelmente errado).
> - **Nunca inventar preço; nunca recomendar compra** — capital é do operador.

## Passo 0 — SEMPRE pergunte a fonte primeiro

Quando o operador pedir um scan **sem** dizer a fonte, **pare e pergunte** via
`AskUserQuestion` (header "Fonte"). Se ele já disse ("roda o Liga selados",
"scan selados na Amazon"), pule a pergunta.

| # | Fonte(s) | Comando | Custo |
|---|----------|---------|-------|
| 1 | **Liga** (default recomendado) | `run_liga_local.py` | $0 (Chrome real local) |
| 2 | Default multi-fonte (Liga+OLX+ML) | `run_all_sources.py` | ~16 créditos Firecrawl (OLX+ML ~8 cada) |
| 3 | Amazon (opt-in) | `run_all_sources.py --sources amazon` | **~51 créditos Firecrawl/run** — avise antes |
| 4 | Todas | `run_all_sources.py --sources liga,olx,mercadolivre,amazon` | soma dos acima |

## Referência e custo

- **Preço de referência** = TCGplayer US (preço **Market** do selado, via espelho
  `tcgcsv.com`), convertido USD→BRL ao vivo (câmbio AwesomeAPI).
- **Referência fresca:** se `data/us_reference.json` tiver mais de
  `max_reference_age_days: 14`, rode antes
  `.venv\Scripts\python.exe build_us_reference.py` — senão o freshness-downgrade
  rebaixa GREEN→YELLOW.
- **Liga é local-only e $0**: Chrome real via patchright, **janela visível**
  (o Cloudflare da Liga dá **0 produtos em headless** — validado 2026-05-29) e IP
  residencial (datacenter/nuvem é barrado). Numa sessão de NUVEM: não tente
  coletar; entregue o último `results/unified_*` existente via `snapshot.py`,
  dizendo de quando é o scan.

## Procedimento

### 1. Ambiente
```powershell
cd C:\Users\mathe\sealed-arbitrage-scanner
# Use SEMPRE o Python da venv do repo: .venv\Scripts\python.exe
```

### 2. Rodar o scan (fonte do Passo 0)
```powershell
# Só Liga (wrapper amigável: checa deps, janela default, snapshot automático no fim):
.venv\Scripts\python.exe run_liga_local.py
.venv\Scripts\python.exe run_liga_local.py --categorias 10,27 --max-por-categoria 10

# Multi-fonte (ou fonte específica):
.venv\Scripts\python.exe run_all_sources.py --sources liga,olx,mercadolivre
```
- Ambos gravam a saída canônica `results/unified_<stamp>/unified_deals.csv` —
  exatamente o que o `snapshot.py` lê.
- **NÃO feche a janela do Chrome** durante a coleta da Liga. Scan completo
  ~15–20 min; rode detached/background se preferir não bloquear o chat.
- Bloqueio de uma fonte (ex.: WAF da OLX) é não-fatal: o orquestrador registra e
  segue; só falha se NENHUMA fonte entregar.
- Categorias da Liga vêm do `config.yaml → liga.categorias` (default: todas as 10,
  incl. 24 Latas e 57 Pré-Lançamento); `run_liga_local.py --categorias` sobrepõe.

### 3. Entregar — SEMPRE via `scripts/snapshot.py`, saída VERBATIM
```powershell
.venv\Scripts\python.exe scripts\snapshot.py
```
(`run_liga_local.py` já chama isso no fim.) Sem argumentos pega o
`results/unified_*` **mais recente** e escreve `snapshots/scan-<YYYY-MM-DD-HHMM>.md`
(UTC). Abra o `.md` e **cole o conteúdo VERBATIM no chat**.

## Contrato de entrega (não negociável)

- **Cole a saída do `scripts/snapshot.py` VERBATIM.** PROIBIDO montar/reformatar
  tabela à mão, reordenar/renomear colunas, tirar um link ou "resumir" linhas.
  Se a entrega não saiu do `snapshot.py`, pare e gere por ele.
- **Toda linha, em TODO bucket** (GREEN, YELLOW, RED do ranking completo) leva os
  **dois links**: `Links` = `[oferta](url BR) · [TCG](url TCGplayer)` numa célula
  só. Links lidos do CSV/registry — **nunca invente URL**.
- **Mostre TODAS as linhas**: a seção "Produtos acionáveis (GREEN+YELLOW)" **e**
  o "Ranking completo por produto" (inclui RED). Entrega "vazia" (0 GREEN) ainda
  é a tabela completa — nunca texto solto.
- Entrega **agrupada por produto** (SKU canônico) com a escada de ofertas por
  unidade; colunas canônicas travadas em `tests/test_snapshot_links.py` e
  `tests/test_snapshot_grouping.py` — a fonte de verdade do layout é o próprio
  `snapshot.py`.
- **Honestidade de preço:** fonte falhou → linha marcada fallback/erro, nunca
  fabrica número. Preço 0/malformado fica RED pelo zero-guard (0% < 30%).
- Arquivo `.xlsx`/`.md` só se o operador pedir explicitamente; entrega = tabela
  no chat. Recorrência é **manual** — não criar agendamento.

## Common Mistakes

| Erro | Correção |
|------|----------|
| Rodar o scan sem perguntar a fonte | Pergunte via `AskUserQuestion` (menu do Passo 0) primeiro |
| Rodar `sealed_arbitrage_scanner.py --source X` pra produção | É debug single-source: grava `results/<stamp>/` por-bucket, que o `snapshot.py` NÃO lê — a entrega sairia da run unified antiga. Use `run_liga_local.py` ou `run_all_sources.py` |
| `--no-janela`/headless no scan da Liga | CF da Liga = 0 produtos em headless. Janela visível é o default — não mexa |
| Rodar Amazon sem avisar o custo | ~51 créditos Firecrawl/run; é opt-in — confirme com o operador |
| Rodar fonte solta em diretório fora do repo | Padrão heterogêneo antigo. Saída canônica = `results/unified_*` dentro do repo |
| Montar a tabela à mão a partir do CSV/XLSX | Rode `scripts/snapshot.py` e cole VERBATIM |
| Dropar o link `[TCG]` pra caber na largura | Os 2 links são obrigatórios em toda linha, todo bucket |
| Reintroduzir o piso R$50 | Selado **não tem piso**; só margem bruta ≥30%. Piso é das singles |
| Threshold como inteiro (`30`) | Selados usa **fração** (`0.30`) em `deal_criteria.min_total_margin_pct` |
| Referência US velha (>14 dias) | Rode `build_us_reference.py` antes, senão GREEN vira YELLOW |
| Coletar Liga da nuvem/IP datacenter | CF barra; entregue o último `results/unified_*` com a data do scan |
| Tratar preço fallback como real | Fonte tcgcsv/câmbio falhou → linha fallback/erro; não opere em cima |
| Confundir com o scanner de singles da Liga | `liga-pokemon-scanner` é carta avulsa: threshold inteiro, COM piso R$50 |
