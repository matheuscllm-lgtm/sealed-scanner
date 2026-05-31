---
tags:
  - tcg
  - arbitragem
  - pokemon
  - selado
  - plan-completion
date: 2026-05-28
plan: POOL-FILL-PLAN.md
fases: 5
status: completo
frete_modelo: "base % + custo por loja (frete sobre gasto real)"
---

# Plan Completion — Pool Fill (2026-05-28)

Execução ponta-a-ponta do `sealed/POOL-FILL-PLAN.md` via `/goal execute`,
modo autônomo, com `sealed-reviewer` (agente read-only) entre cada fase.

## Objetivo (atingido)

Transformar o output de "best-seller price (ilusório)" em **preço médio
efetivo por unidade dado um budget**, considerando estoque por vendedor e
frete por lote. Resolve o problema dos vendedores qty=1 que inflam o frete.

**Goal-line:** `python sealed/sealed_arbitrage_scanner.py --source liga --pool-budget 5000`
produz aba `Pool Analysis` no XLSX com unidades + preço efetivo + margem real
recomputada vs US. ✅

## Fases e revisões

| Fase | Commit | Reviewer | Resultado |
|---|---|---|---|
| F1 — qty parse no adapter | `339ec09` | **FIX_NEEDED** (coverage 44% < 80%) | corrigido em F1.5 |
| F1.5 — qty templates dedicados | `c87bb11` | PASS (100% em 2 pcodes) | sprite imgunid + multi-template |
| F2 — peso + frete config | `9dcbe1d` | PASS | desvio lookup-by-type aceito |
| F3 — pool_fill engine | `15a1c24` | PASS | 9 tests, dados reais |
| F4 — CLI + XLSX | `7b102a6` | PASS | regressão zero confirmada |
| F5 — frete flat (calibração operador) | `0a48ff6` | (auto) | modelo flat substituiu Correios |
| F5b — frete proporcional + budget-inclusive | `9b8783a` | (auto) | budget vira teto total |
| F5c — frete = % do gasto real | `063a948` | (auto) | corrige falso-negativo (ver DRI) |
| F5d — frete base % + custo por loja | `0e17db8` | (auto) | modelo final, 2 pernas |

10 commits + 1 commit de setup (`875a5b3`). 22/22 tests passando. O modelo de
frete iterou 4× (F5 → F5d) conforme o operador refinou pra fidelidade máxima.

## Descobertas técnicas

1. **Liga usa DOIS sprites anti-scrape** — `imgnum` (preço, 5-letter classes)
   e `imgunid` (qty, 6-letter classes). Templates separados em
   `data/liga_digit_templates_qty/`. Decoder estendido pra multi-template
   por dígito (`1b.png` cobre variante de '1' que nIkOsZ usa).
2. **Qty coverage 100%** nos 2 pcodes de teste (PHF pack 9/9, PO Box 7/7)
   após F1.5.
3. **Modelo de frete final** (operador 2026-05-28, evoluiu em 4 iterações):
   - v1: fixo R$250 (1 loja) / R$350 (vários).
   - v2: proporcional ao budget (5%/7%).
   - v3 (interpretação B): % do GASTO real, não do budget — corrige pool fino.
   - **v4 final**: `frete = 5% × gasto + R$17 × (n_lojas − 1)`. Duas pernas:
     base % (internacional, escala com valor) + custo por loja adicional
     (doméstico, cada vendedor Liga → consolidador). Budget é TOTAL
     (produtos + frete <= budget). Config: `flat_base_pct`,
     `flat_per_seller_brl`. Reproduz os R$250/350 que o operador deu.
   - Modelo `per_seller` peso-based mantido como legado.

## Resultado com dados reais (modelo de frete final v4)

Scan live Liga 2026-05-28 + dados F1.5:

| SKU | Budget | Unid | Lojas | Frete | Preço efetivo | Margem real US |
|---|---:|---:|---:|---:|---:|---:|
| Phantasmal Flames Pack | R$ 5k | 129 | 7 | R$ 334,77 | R$ 38,68/un | **+41,0%** |
| Phantasmal Flames Pack | R$ 10k | 156 | 7 | R$ 415,64 | R$ 42,87/un | +27,2% |
| Perfect Order Box | R$ 5k | 5 | 1 | ~R$ 225 | ~R$ 945/un | **+18%** |

Contraste com a ilusão do "best price": PHF pack mostrava R$ 32,99 (+65%
margem) — realidade com volume + frete é ~R$ 38,68 (+41%). No R$10k o
estoque (156 packs) vira o gargalo, não o budget.

## Decisão-chave: frete sobre o GASTO REAL, não sobre o budget

O scan live de 2026-05-28 expôs um furo no modelo intermediário (frete como
% do BUDGET reservado). O caso **Destined Rivals** é o exemplo canônico de
por que mudamos pra frete sobre o gasto real em produtos.

**Contexto:** Destined Rivals pack só tinha ~19 unidades em estoque (2
vendedores) no scan. Best price R$ 32 — parecia um deal.

| | Modelo ANTIGO (% do budget) | Modelo NOVO (% do gasto) |
|---|---|---|
| Produtos comprados | R$ 607,90 (19 packs) | R$ 607,90 (19 packs) |
| Frete | R$ 350 (7% × R$ 5.000) | R$ 42,55 (7% × R$ 608 + lojas) |
| Preço efetivo | R$ 50,42/pack | R$ 34,23/pack |
| Margem real vs US | **−11,6%** ❌ FALSO-NEGATIVO | **+30,1%** ✅ REAL |

**O furo:** o modelo antigo cobrava frete como se você tivesse enchido os
R$ 5.000, mas você só conseguiu comprar R$ 608 de produto (estoque limitado).
Resultado: um frete de R$ 350 sobre R$ 608 de produto = 57% de custo de
envio → margem despencava pra negativa. **Destined Rivals nunca foi um deal
ruim — o modelo é que estava errado**, punindo o SKU por um capital que nunca
seria gasto nele.

**A correção:** frete = % do que você EFETIVAMENTE gasta + custo por loja.
Pool fino paga frete pequeno e proporcional. Destined Rivals volta a aparecer
como o YELLOW/GREEN positivo que de fato é.

Lição registrada: **frete sempre incide sobre o gasto real, nunca sobre o
budget-teto.** Modelo budget-based gera falso-negativo em qualquer SKU com
estoque insuficiente pra encher o budget.

## Reviewer findings menores (registrados pra v2)

- pool_fill: outlier filter exige ≥3 sellers (SKUs com <3 não filtram typos).
- pool_fill: `best_price` usa lista pré-outlier (edge case com único outlier).
- shipping: `peso_g: 0` cairia no fallback (cenário irreal).
- config weights_g_by_type não inclui Theme/Battle Deck/Kit (só relevante se
  categoria Kits for habilitada).
- scanner: import fallback try/except é opaco se módulo renomeado.

## Pendências (operador)

1. **Validação manual de qty** — abrir 1 SKU GREEN na Liga, contar qty real
   em 3 vendedores, comparar com `qty_avail` do adapter. (F1.5 deu 100%
   coverage mas validação visual independente não foi feita formalmente.)
2. **Calibrar os 2 números do frete com dados reais do consolidador** —
   defaults: `flat_base_pct` 5%, `flat_per_seller_brl` R$17. Reproduzem o
   R$250/350 que o operador estimou, mas se o consolidador tiver tabela
   real, ajustar em config.yaml → frete.
3. **(Opcional) Piso mínimo de frete** — modelo atual pode subestimar frete
   em lote muito pequeno (envio internacional tem custo-base). Não relevante
   nos budgets R$5-10k; só implementar se fizer lotes pequenos.

## Próximo passo (P1 em GOALS.md)

Rodar scan Liga real com `--pool-budget 5000` e validar manualmente os Top 5
GREEN do `Pool Analysis` antes de mover capital.
