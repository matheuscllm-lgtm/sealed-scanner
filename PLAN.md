# Plan — TCG Sealed Arbitrage Scanner

**Data:** 2026-05-25
**Branch:** `claude/tcg-sealed-arbitrage-agent-eNXVg`
**PR:** #1 (draft) — https://github.com/matheuscllm-lgtm/tcg-arbitrage-scanners/pull/1

## Objetivo

Scanner que encontra produtos **selados** de Pokémon TCG com pelo menos
**~30-40% de delta** entre o preço Brasil e o TCGPlayer US — comprar barato
no Brasil, revender nos EUA, lucrar.

## Estado atual — projeto **funcional do celular**

| Peça | Estado |
|---|---|
| Pipeline (match → margem → classificação → CSV/XLSX) | ✅ |
| Modelo de margem (≥ 40% margem total como filtro principal) | ✅ |
| `bulk_qty` por SKU — packs assumem 24 unid p/ amortizar frete fixo | ✅ |
| Fonte US: TCGPlayer Market via [tcgcsv.com](https://tcgcsv.com) | ✅ operacional |
| Fonte BR: **OLX** (`--source olx`) — live, sem CF, sem auth | ✅ operacional |
| Fonte BR: **Amazon BR** (`--source amazon`) — live | ✅ operacional |
| Adapter Liga BR (`--source liga`) | ❌ CF hard-block + cloudscraper testado (também bloqueado) |
| Adapter Mercado Livre | ❌ API fechada + HTML anti-bot |
| Registry: **55 SKUs** — boxes, ETBs (regular + PC), bundles + **booster packs** dos 13 sets ativos | ✅ |
| Exclude_terms abrangente: PT/JP/CN/KR/ES/FR/DE/IT + acessórios (case, acrylic, magnetic, etc.) | ✅ |
| Matcher com `requires_terms` (PC ETBs sem colisão com ETB regular) | ✅ |
| Sort por margem desc, near-misses no print, snapshot Markdown Obsidian-friendly | ✅ |
| `scripts/snapshot.py` — gera nota datada `sealed/snapshots/scan-*.md` para vault | ✅ |

**O projeto entrega valor agora, do celular, sem dependência da Liga.**

## Como rodar

```bash
python sealed/sealed_arbitrage_scanner.py --source olx       # busca live OLX
python sealed/sealed_arbitrage_scanner.py --source amazon    # busca live Amazon BR
python sealed/sealed_arbitrage_scanner.py --source mock      # offline, exercita pipeline
python sealed/build_us_reference.py                          # refresh diário de preços US
```

Saídas em `sealed/results/<timestamp>/` com 3 CSVs (real_opportunities,
review_required, rejected) + 1 XLSX com 5 sheets.

## Leitura de mercado atual (2026-05-25 18:36 UTC)

OLX + Amazon merged: **1 GREEN, 2 YELLOW, 28 RED, 31 matches total**.

🟢 **GREEN — único deal real:**

> **Phantasmal Flames Booster Pack (Inglês) em BH a R$ 35**
> Margem total **+65.9%** / 39.7% mais barato que TCGPlayer.
> Líquido estimado +R$ 7.81/pack (22% net) assumindo compra de 24 packs.
> US Market ~US$ 10.75 = R$ 58.05 por pack.

🟡 **YELLOW — perto do alvo:**
- Chaos Rising ETB (OLX, RJ) R$ 346 — 39.4% margem total
- Chaos Rising Booster Bundle (Amazon) R$ 199.99 — 31.8% margem total

O snapshot completo com 31 matches ranqueados fica em
`sealed/snapshots/scan-YYYY-MM-DD-HHMM.md` (Obsidian frontmatter pronto).

## Caminhos para destravar mais oportunidades

1. **Esperar inventário melhor** — rodar o scanner periodicamente; deals
   aparecem quando vendedores precisam vender rápido. (GH Actions cron + alerta
   por email/Telegram é o próximo passo natural — lembrar do quota cap do MYP repo.)
2. **Expandir registry** para sets mais antigos (Crown Zenith, Silver Tempest,
   Lost Origin, Astral Radiance, etc.) — qualquer pode ter um deal pontual.
3. **Liga adapter** — quando estiver em casa: rodar `probe_liga_sealed.py`
   na máquina, colar saída, ajusto seletores. Liga tende a ter mais
   inventário individual e preços mais agressivos que OLX.
4. **Proxy residencial** ($20-50/mês: Bright Data, Smartproxy) — destrava CF
   neste ambiente e permite rodar Liga + scanner automatizado na nuvem 24/7.

## Decisões abertas

- Subir threshold pra 30% (mais cobertura, menos margem) ou manter 40%?
- Adicionar alerta automático (Telegram/email) quando um GREEN aparecer?
- GH Actions cron diário pra refresh + scan + commit do snapshot de resultados?

## Resumo numa linha

Scanner pronto e medindo o mercado real do OLX. O mercado **agora** está
eficiente; o pipeline pega o próximo deal real assim que aparecer.

---

Estado vivo: `SESSION-HANDOFF.md`. Especificação: `AGENT.md`. Setup: `README.md`.
