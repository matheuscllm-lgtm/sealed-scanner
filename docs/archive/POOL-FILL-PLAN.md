# 🔴 HISTÓRICO — NÃO SEGUIR

> **Arquivado 2026-06-03.** O "Status: ATIVO (P0)" abaixo é **obsoleto** —
> refs branch antiga `claude/tcg-sealed-arbitrage-agent-eNXVg` e workflow
> `/goal execute` + agente `sealed-reviewer` que não é o fluxo atual. A fonte
> única de verdade é o **[README.md](../../README.md)** na raiz. O conceito de
> pool-fill segue implementado (`pool_fill.py`, flag `--pool-budget`); este
> documento de planejamento é só registro histórico.

---

# Pool Fill — Realistic Avg Price + Volume Sourcing

**Status:** ATIVO (P0) — definido 2026-05-27
**Branch base:** `claude/tcg-sealed-arbitrage-agent-eNXVg` (HEAD `bfdf0d5` no momento da criação)
**Executor:** invocado por `/goal execute`
**Revisor:** `sealed-reviewer` (spawned entre cada fase via Task tool)

---

## Problema de negócio

O scanner hoje reporta "best-seller price" por SKU — mas comprar volume na Liga
implica consolidar de múltiplos vendedores, cada um com **estoque limitado** e
**frete próprio**. Vendedores com qty=1 inflam o frete por unidade e quebram a
economia. O output atual é otimista demais pra suportar decisão de capital.

**Pergunta que o scanner precisa responder após esse trabalho:**

> *"Se eu colocar R$ 5.000 nesse SKU, quantas unidades eu levo e quanto sai
> cada uma em média, considerando estoque real por vendedor e frete por loja?"*

## Objetivo concreto (goal-line)

Rodar `python sealed/sealed_arbitrage_scanner.py --pool-budget 5000` e ver
uma aba `Pool Analysis` no XLSX com, por SKU GREEN/YELLOW: **unidades em R$ 5k**,
**preço médio efetivo por unidade**, e **margem real recomputada vs US** —
com **dados empíricos** (não modelados).

## Estado base (2026-05-27)

| Peça | Estado |
|---|---|
| `liga_adapter.py` extrai preço, seller, lang, condition | ✅ |
| `liga_adapter.py` extrai **qty por vendedor** | ❌ falta |
| `sku_registry.yaml` tem `peso_g` por SKU | ❌ falta |
| `config.yaml` tem `frete_estimado_brl` table | ❌ falta |
| Módulo `pool_fill.py` | ❌ falta |
| Aba `Pool Analysis` no XLSX | ❌ falta |

---

## Fases

Cada fase = 1 PR atômico. Reviewer roda entre cada fase. Próxima fase só
começa quando reviewer der `PASS`.

### Fase 1 — Captura de qtd por vendedor `[P0]`

**Arquivos:** `sealed/liga_adapter.py`, `sealed/probe_liga_sealed.py`

**Tarefas:**
1. Rodar `python sealed/probe_liga_sealed.py "https://www.ligapokemon.com.br/?view=prod/view&pcode=134382"` (PHF pack, 9 vendedores conhecidos no scan 2026-05-27). Identificar o seletor HTML que contém qtd disponível dentro de `div.store`.
2. Em `parse_product_page` (liga_adapter.py, função em ~linha 495), adicionar extração de qtd ao loop `for store in soup.select("div.store")`. Adicionar campo `qty_avail: int | None` ao dict de listing.
3. Se qtd não parsear pra um vendedor específico, gravar `qty_avail = None` (NÃO 0, NÃO 1) — diferencia "vendedor sem info" de "vendedor com 1 unidade".

**Aceitação (machine-checkable):**
- [ ] `python sealed/liga_adapter.py` (CLI standalone) imprime listagens com `qty_avail` numérico para ≥80% dos vendedores em 2 pcodes de teste: 134382 (PHF pack) e 135530 (Perfect Order Box).
- [ ] Listings com `qty_avail = None` < 20% do total.
- [ ] Nenhum scan existente quebra: `python sealed/sealed_arbitrage_scanner.py --source mock` ainda produz output válido.

**Não-objetivo:** OLX/Amazon adapters — Liga first.

---

### Fase 2 — Config de peso + tabela de frete `[P0]`

**Arquivos:** `sealed/sku_registry.yaml`, `sealed/config.yaml`

**Tarefas:**
1. Adicionar `peso_g` por SKU. Defaults por tipo:
   - Booster Pack avulso: **40g**
   - Booster Bundle: **500g**
   - Elite Trainer Box: **1500g**
   - Booster Box: **1200g**
   - Collection Box: **1100g**
   - Tin: **300g**
   - Blister: **80g**
2. Em `config.yaml`, adicionar seção `frete`:
   ```yaml
   frete:
     destino_cep: "01310-100"   # PLACEHOLDER — operador substitui
     estimado_brl:
       until_500g: 22
       until_1kg: 35
       until_2kg: 45
       until_3kg: 60
     fallback_brl: 50           # usado se peso > 3kg ou desconhecido
   ```
3. Criar `sealed/lib/shipping.py` com `compute_shipping(peso_g: int, cep: str = None) -> float` — por enquanto só consulta a tabela; Correios API real fica fora de escopo.

**Aceitação (machine-checkable):**
- [ ] Importar `from sealed.lib.shipping import compute_shipping` e chamar para todos 55 SKUs sem KeyError nem TypeError.
- [ ] `peso_g` presente em 100% dos SKUs do registry.
- [ ] Teste `test_shipping_basic()` valida que pack avulso 40g retorna 22.0, ETB 1500g retorna 45.0.

**Decisão necessária do operador antes da fase 5:** CEP destino real (default placeholder funciona pra desenvolvimento).

---

### Fase 3 — Engine `pool_fill.py` `[P0]`

**Arquivo novo:** `sealed/pool_fill.py`
**Arquivo novo:** `sealed/tests/test_pool_fill.py`

**API pública:**
```python
from dataclasses import dataclass

@dataclass
class BreakdownItem:
    seller: str
    qty_bought: int
    unit_price: float
    frete: float
    gasto_total: float
    effective_unit_price: float

@dataclass
class PoolResult:
    total_units: int
    total_spent_brl: float
    avg_price_per_unit: float          # efetivo (incl. frete amortizado)
    inflation_vs_best_price: float     # % acima do "melhor preço"
    recomputed_margin_vs_us: float     # margem real
    breakdown: list[BreakdownItem]
    skipped_sellers: list[tuple[str, str]]  # (seller, reason)

def fill_pool(
    listings: list[dict],              # output do liga_adapter
    sku: str,                          # SKU canônico a consolidar
    budget_brl: float,
    us_price_brl: float,
    *,
    peso_g: int,
    shipping_table: dict,
    skip_qty_unknown: bool = False,
    min_qty_per_seller: int = 1,
    max_effective_price: float | None = None,
) -> PoolResult: ...
```

**Algoritmo:**
1. Filtra listings ao SKU alvo.
2. Descarta outliers: preço > 2× mediana do grupo.
3. Para cada vendedor, calcula `effective_price = unit + (frete / qty_v)`.
4. Ordena ASC por `effective_price`.
5. Greedy fill até budget esgotar OU `effective_price` ultrapassar `max_effective_price`.
6. Retorna PoolResult.

**Aceitação (machine-checkable):**
- [ ] Test fixture com os dados reais do scan 2026-05-27 (Phantasmal Flames pack, 9 vendedores) + qty placeholders proporcionais ao cenário "realista" do plan original. Resultado esperado: ~60 unidades, preço médio R$ 37.80 ± 5%.
- [ ] Test fixture Perfect Order Booster Box (8 vendedores): ~6 unidades, R$ 807 ± 30.
- [ ] Outlier teste: vendedor com R$ 925 (typo real do scan) DEVE ser descartado.
- [ ] `min_qty_per_seller=3` filtra vendedores com qty < 3.

**Sem dependências externas além do que já existe** (sealed/ já usa Python stdlib + openpyxl + yaml + bs4).

---

### Fase 4 — Integração CLI + XLSX `[P1]`

**Arquivos:** `sealed/sealed_arbitrage_scanner.py`

**Tarefas:**
1. Novas flags CLI:
   - `--pool-budget BRL` (múltiplos via vírgula: `--pool-budget 1000,5000,10000`). Default: desligado.
   - `--pool-cep CEP` — sobrescreve `config.frete.destino_cep`.
   - `--pool-min-qty N` — filtra vendedores com qty < N. Default: 1.
2. Pra cada SKU GREEN/YELLOW, chamar `pool_fill.fill_pool()` em cada budget configurado.
3. Nova aba XLSX `Pool Analysis`. Colunas:
   - SKU
   - Produto
   - Tipo
   - # Vendedores total
   - Melhor preço unit (R$)
   - Preço efetivo @ R$1k / @ R$5k / @ R$10k
   - Unidades @ R$1k / @ R$5k / @ R$10k
   - # Lojas necessárias @ R$5k
   - Margem real vs US (@ R$5k)
   - Skipped (qty unknown / outliers / acima do teto)
4. No `Summary` sheet, seção nova "Top 5 SKUs por margem realista em R$ 5k".

**Aceitação (machine-checkable):**
- [ ] `python sealed/sealed_arbitrage_scanner.py --source mock --pool-budget 5000` produz XLSX com aba `Pool Analysis` populada com ≥1 SKU.
- [ ] Coluna "Preço efetivo @ R$5k" tem valores numéricos (não NaN) pra todos GREEN.
- [ ] Coluna "Preço efetivo" ≥ coluna "Melhor preço unit" (sempre — frete só inflaciona).
- [ ] Comportamento sem `--pool-budget` é idêntico ao atual (regressão zero).

---

### Fase 5 — Calibração com dado real `[P1]`

**Tarefas (mistas operador + agente):**
1. **Operador:** abrir 1 SKU GREEN na Liga (recomendado: Phantasmal Flames pack pcode=134382), anotar qtd real de 3-5 vendedores. Comparar com o que o adapter capturou pós-Fase-1. Tolerância: ±10%.
2. **Operador:** fazer 3 cotações Correios reais pro CEP destino (pacote 40g / 500g / 1.5kg). Atualizar `config.yaml → frete.estimado_brl`.
3. **Agente:** rerun do scan e gera `sealed/snapshots/calibration-<data>.md` com diff dos fretes estimados (pré) vs reais (pós) + impacto no preço efetivo dos 3 top SKUs.

**Aceitação:**
- [ ] Snapshot de calibração existe.
- [ ] Diff entre fretes estimados e reais documentado.
- [ ] Se diff > 25% em algum peso → ajustar tabela; se < 15% → marcar como calibrado e fechar a fase.

---

## Fora de escopo (explícito)

- ❌ Cotação Correios API automatizada (v2 — risco bloqueio).
- ❌ OLX/Amazon ganhando qty (Liga first; OLX é 1 vendedor por anúncio).
- ❌ Otimizador multi-objetivo (greedy by effective_price é suficiente).
- ❌ Modelagem de risco de cancelamento por vendedor (assume compra atômica).

## Riscos conhecidos

| Risco | Mitigação |
|---|---|
| Seletor de qtd na Liga muda | Fase 1: defensive `qty_avail = None`, scanner continua emitindo deals com flag de incerteza |
| Frete real ≠ estimado por região/loja | Fase 5 calibra; documentar incerteza na coluna XLSX |
| Vendedor com qty alta que não cumpre (cancelamento) | Fora de escopo v1. Próxima iteração: penalizar reputação baixa |
| Outliers de typo sobrevivem ao filtro 2× mediana | Test fixture cobre o caso real (R$ 925 no PHF); se reaparecer, refinar pra 1.5× |

## Sequência

```
F1 (qty parse)       ~2h  →  PR atômico → reviewer
F2 (peso + frete)    ~1h  →  PR atômico → reviewer
F3 (pool_fill engine) ~3h  →  PR atômico c/ tests → reviewer
F4 (XLSX + CLI)      ~2h  →  PR atômico → reviewer
F5 (calibração)      ~1h operador + ~30min agente → reviewer
```

**Total executor:** ~8h autônomo. **Total operador:** ~1h (CEP + cotações + validação manual qty 1 SKU).
