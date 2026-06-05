"""pool_fill.py — greedy volume-fill por SKU dado um budget.

Problema que resolve: scanner reporta "best-seller price" por SKU, mas
comprar volume na Liga implica consolidar de N vendedores, cada um com
estoque limitado e frete próprio. Vendedor com qty=1 + frete R$ 22
significa preço efetivo R$ X+22 por unidade — quebra a economia.

Este módulo calcula, dado:
  - lista de ofertas (preço, qty, vendedor) — output do liga_adapter
  - budget em BRL
  - peso unitário do produto (pra calcular frete por loja)
  - tabela de frete por peso

→ preço médio efetivo por unidade depois de comprar até esgotar budget
  ou estoque disponível, amortizando frete sobre qty comprada de cada loja.

Algoritmo:
  1. Filtra outliers (preço > 2× mediana — typos/scams).
  2. Filtra vendedores com qty_avail < min_qty_per_seller.
  3. Calcula effective_price(v) = price + frete / qty_disponivel.
  4. Ordena ASC por effective_price.
  5. Greedy: do mais barato pro mais caro, compra MAX(qty disponível, qty
     que cabe no budget remanescente).
  6. Retorna PoolResult com breakdown completo.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from typing import Iterable

__all__ = ["BreakdownItem", "PoolResult", "SkuAverage", "fill_pool", "avg_price_for_sku"]


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
    sku: str
    budget_brl: float
    total_units: int
    total_spent_brl: float           # gasto em PRODUTOS (sem frete)
    total_freight_brl: float         # frete total do lote
    total_outlay_brl: float          # produtos + frete (capital real necessário)
    avg_price_per_unit: float        # efetivo (incl. frete) = total_outlay / units
    inflation_vs_best_price: float   # % acima do "melhor preço"
    recomputed_margin_vs_us: float   # margem real (vs US ref), já com frete
    n_sellers_used: int
    freight_model: str = "per_seller"
    breakdown: list[BreakdownItem] = field(default_factory=list)
    skipped_sellers: list[tuple[str, str]] = field(default_factory=list)  # (seller, reason)


def _frete_for_qty(frete_unit: float, qty: int) -> float:
    """Frete amortizado por unidade. Frete é fixo por loja, qty diluí."""
    if qty <= 0:
        return float("inf")
    return frete_unit / qty


def _filter_outliers(listings: Iterable[dict], outlier_factor: float = 2.0) -> tuple[list[dict], list[tuple[str, str]]]:
    """Descarta listings com price > mediana × factor (typos/scams).

    Mediana precisa de >=3 pontos pra ser estável; com menos, devolve tudo.
    Devolve (kept, skipped[(seller, motivo)]). Reusado por fill_pool e
    avg_price_for_sku pra que ambos rejeitem os mesmos typos.
    """
    listings = list(listings)
    prices = sorted(l["price_brl"] for l in listings)
    if len(prices) < 3:
        return listings, []
    threshold = statistics.median(prices) * outlier_factor
    kept: list[dict] = []
    skipped: list[tuple[str, str]] = []
    for l in listings:
        if l["price_brl"] > threshold:
            skipped.append((l.get("seller", "?"), f"outlier price > {threshold:.2f} (median × {outlier_factor})"))
        else:
            kept.append(l)
    return kept, skipped


def fill_pool(
    listings: Iterable[dict],
    sku: str,
    budget_brl: float,
    us_price_brl: float,
    *,
    frete_unit: float = 0.0,
    freight_model: str = "per_seller",
    flat_base_pct: float = 0.05,
    flat_per_seller_brl: float = 17.0,
    skip_qty_unknown: bool = False,
    min_qty_per_seller: int = 1,
    max_effective_price: float | None = None,
    outlier_factor: float = 2.0,
) -> PoolResult:
    """Greedy fill volume por SKU.

    Dois modelos de frete:

    freight_model='per_seller' (legado): cada vendedor cobra `frete_unit`
        fixo; o frete amortiza sobre a qty comprada daquela loja. Usado
        quando cada compra é enviada separada.

    freight_model='flat' (operador 2026-05-28): frete fixo do LOTE inteiro,
        independente de quantos vendedores — modelo de consolidador/redirecionador.
        flat_single_seller_brl se o pool toca 1 vendedor; flat_multi_seller_brl
        se toca 2+. O frete é adicionado ao gasto em produtos (não sai do
        budget de produtos). No modo flat o frete não influencia o ranking
        por vendedor, então a ordenação é por preço unitário puro.

    freight_model='none' (operador 2026-06-05): SEM frete. O pool mostra só o
        custo consolidado das mercadorias (o que cabe no budget, mais barato
        primeiro), sem inventar frete — que depende do lote/remessa, decidido
        fora do scanner. total_freight=0; outlay=produtos; margem é a bruta.

    Args:
        listings: dicts com price_brl, qty_avail (int|None), seller.
        sku: identificador (só guardado no result).
        budget_brl: capital TOTAL (produtos + frete). No modo flat o frete sai
                    de dentro do budget. No per_seller o budget é gasto total
                    incluindo os fretes por loja.
        us_price_brl: preço de referência US em BRL.
        frete_unit: frete por loja (só usado em per_seller).
        freight_model: 'per_seller' | 'flat' | 'none' (none = freight-free).
        flat_base_pct / flat_per_seller_brl: modelo flat final (operador
            2026-05-28). frete = base_pct × gasto_em_produtos
            + per_seller × (n_lojas − 1). base_pct = perna internacional +
            1ª loja (escala com valor); per_seller = perna doméstica por loja
            ADICIONAL. Restrição produtos + frete <= budget. Pools finos pagam
            frete pequeno; pools com muitas lojas pagam o doméstico de cada uma.
        skip_qty_unknown: ignora listings com qty_avail=None.
        min_qty_per_seller: descarta vendedores com qty < N.
        max_effective_price: teto de effective price por vendedor (só per_seller).
        outlier_factor: descarta price > median × N (typos).

    Returns:
        PoolResult com breakdown + skipped + métricas (margem inclui frete, salvo no modelo 'none').
    """
    is_flat = freight_model == "flat"
    # 'none' (operador 2026-06-05): freight-free. Zera o frete e segue pelo
    # caminho per_seller (que então ordena por preço puro) → o pool reporta só
    # o custo de mercadoria, sem frete fabricado.
    if freight_model == "none":
        frete_unit = 0.0
    listings = list(listings)
    skipped: list[tuple[str, str]] = []

    # Step 1: filter outliers (mediana precisa de >=3 pontos pra ser estável)
    prices = sorted(l["price_brl"] for l in listings)
    listings, _outliers = _filter_outliers(listings, outlier_factor)
    skipped.extend(_outliers)

    # Step 2: filter qty conditions
    cand = []
    for l in listings:
        qty = l.get("qty_avail")
        if qty is None:
            if skip_qty_unknown:
                skipped.append((l.get("seller", "?"), "qty_avail desconhecido (skip_qty_unknown=True)"))
                continue
            qty = 1  # pessimist fallback
        if qty < min_qty_per_seller:
            skipped.append((l.get("seller", "?"), f"qty {qty} < min_qty_per_seller {min_qty_per_seller}"))
            continue
        # Effective price: no flat o frete é do lote, não por vendedor → ranking por preço puro
        if is_flat:
            eff = l["price_brl"]
        else:
            eff = l["price_brl"] + _frete_for_qty(frete_unit, qty)
            if max_effective_price is not None and eff > max_effective_price:
                skipped.append((l.get("seller", "?"), f"effective price R${eff:.2f} > teto R${max_effective_price:.2f}"))
                continue
        cand.append({**l, "_qty": qty, "_eff": eff})

    # Step 3: sort ASC by effective price (= preço puro no flat)
    cand.sort(key=lambda c: c["_eff"])

    def _greedy(goods_budget: float, per_seller_frete: float) -> tuple[list[BreakdownItem], int, float, list]:
        """Compra cheapest-first até esgotar goods_budget ou estoque.
        Devolve (breakdown, total_units, goods_spent, skipped_local)."""
        rem = goods_budget
        units = 0
        spent = 0.0
        bd: list[BreakdownItem] = []
        skip_local: list[tuple[str, str]] = []
        for c in cand:
            unit_price = c["price_brl"]
            qty_avail = c["_qty"]
            if rem < unit_price + per_seller_frete:
                skip_local.append((c.get("seller", "?"), f"budget restante R${rem:.2f} < preço+frete R${unit_price + per_seller_frete:.2f}"))
                continue
            max_units = min(qty_avail, int((rem - per_seller_frete) // unit_price))
            if max_units <= 0:
                skip_local.append((c.get("seller", "?"), "max_units=0 (não cabe nem 1)"))
                continue
            gasto = max_units * unit_price + per_seller_frete
            bd.append(BreakdownItem(
                seller=c.get("seller", "?"),
                qty_bought=max_units,
                unit_price=unit_price,
                frete=per_seller_frete,
                gasto_total=gasto,
                effective_unit_price=gasto / max_units,
            ))
            rem -= gasto
            spent += gasto
            units += max_units
        return bd, units, spent, skip_local

    # Step 4: greedy fill
    # Flat (modelo final): frete = base_pct × gasto  +  per_seller × (n_lojas-1).
    #   base_pct  = perna internacional + 1ª loja (escala com valor do lote)
    #   per_seller = perna doméstica por loja ADICIONAL (cada vendedor Liga
    #                manda o pacote dele ao consolidador)
    # Single-pass: ao abrir uma loja nova (além da 1ª), reserva per_seller do
    # budget; cada unidade consome price × (1 + base_pct). Garante
    # produtos + frete <= budget sem chicken-egg.
    if is_flat:
        rem = budget_brl
        units = 0
        goods_spent = 0.0
        breakdown = []
        for c in cand:
            unit_price = c["price_brl"]
            qty_avail = c["_qty"]
            seller_cost = 0.0 if not breakdown else flat_per_seller_brl
            eff_unit_cost = unit_price * (1.0 + flat_base_pct)  # custo no "espaço de budget"
            if rem < seller_cost + eff_unit_cost:
                skipped.append((c.get("seller", "?"), f"budget restante R${rem:.2f} não cobre loja+1un (R${seller_cost + eff_unit_cost:.2f})"))
                continue
            max_units = min(qty_avail, int((rem - seller_cost) // eff_unit_cost))
            if max_units <= 0:
                skipped.append((c.get("seller", "?"), "max_units=0 (não cabe nem 1)"))
                continue
            seller_goods = max_units * unit_price
            seller_freight = seller_cost + seller_goods * flat_base_pct
            breakdown.append(BreakdownItem(
                seller=c.get("seller", "?"),
                qty_bought=max_units,
                unit_price=unit_price,
                frete=seller_freight,
                gasto_total=seller_goods + seller_freight,
                effective_unit_price=(seller_goods + seller_freight) / max_units,
            ))
            rem -= seller_cost + max_units * eff_unit_cost
            units += max_units
            goods_spent += seller_goods
        n_sellers = len(breakdown)
        total_freight = goods_spent * flat_base_pct + flat_per_seller_brl * max(0, n_sellers - 1)
        total_outlay = goods_spent + total_freight
    else:
        # per_seller: frete por loja sai do budget total dentro de cada gasto.
        breakdown, units, total_with_frete, sk = _greedy(budget_brl, frete_unit)
        skipped += sk
        total_freight = sum(b.frete for b in breakdown)
        goods_spent = total_with_frete - total_freight
        total_outlay = total_with_frete

    total_units = units
    best_price = prices[0] if prices else 0.0

    # Step 5: métricas (avg e margem JÁ incluem frete)
    avg = (total_outlay / total_units) if total_units > 0 else 0.0
    infl = (avg / best_price - 1.0) * 100 if best_price > 0 and total_units > 0 else 0.0
    margin = ((us_price_brl - avg) / avg * 100) if avg > 0 else 0.0

    return PoolResult(
        sku=sku,
        budget_brl=budget_brl,
        total_units=total_units,
        total_spent_brl=goods_spent,
        total_freight_brl=total_freight,
        total_outlay_brl=total_outlay,
        avg_price_per_unit=avg,
        inflation_vs_best_price=infl,
        freight_model=freight_model,
        recomputed_margin_vs_us=margin,
        n_sellers_used=len(breakdown),
        breakdown=breakdown,
        skipped_sellers=skipped,
    )


@dataclass
class SkuAverage:
    """Preço médio ponderado por quantidade de um SKU, SEM frete."""
    sku: str
    n_sellers: int
    total_qty: int                 # soma das qty (desconhecida conta como 1)
    qty_unknown_sellers: int       # quantos vendedores tinham qty desconhecida
    best_price: float              # menor preço (pós-outlier)
    weighted_avg_price: float      # média ponderada por qty, sem frete
    us_price_brl: float
    avg_margin_pct: float          # margem total (vs US) no preço médio
    n_outliers_dropped: int


def avg_price_for_sku(
    listings: Iterable[dict],
    *,
    us_price_brl: float,
    sku: str = "",
    outlier_factor: float = 2.0,
) -> SkuAverage:
    """Preço médio ponderado por quantidade (SEM frete) de um SKU.

    Caso de uso (operador 2026-06-05): o estoque por vendedor costuma ser
    pequeno, então comprar volume = varrer vários logistas a preços
    diferentes. A média ponderada pela qty disponível é o custo real por
    unidade ao montar o lote. O frete fica FORA de propósito — depende do
    tamanho da remessa/lote, decidido fora do scanner (foi por isso que a
    "margem líquida" saiu). A margem aqui é a TOTAL (bruta) no preço médio.

    - Filtra outliers (typos) com o mesmo critério do fill_pool.
    - Pondera por qty_avail; vendedor com qty desconhecida entra com peso 1.
    """
    listings = list(listings)
    kept, _ = _filter_outliers(listings, outlier_factor)
    n_outliers = len(listings) - len(kept)
    if not kept:
        return SkuAverage(sku, 0, 0, 0, 0.0, 0.0, us_price_brl, 0.0, n_outliers)

    total_w = 0
    weighted_sum = 0.0
    qty_unknown = 0
    min_price = float("inf")
    for l in kept:
        price = float(l["price_brl"])
        qty = l.get("qty_avail")
        if qty is None:
            qty = 1
            qty_unknown += 1
        w = max(1, int(qty))
        total_w += w
        weighted_sum += price * w
        min_price = min(min_price, price)

    avg = weighted_sum / total_w if total_w else 0.0
    margin = ((us_price_brl - avg) / avg * 100.0) if avg > 0 else 0.0
    return SkuAverage(
        sku=sku,
        n_sellers=len(kept),
        total_qty=total_w,
        qty_unknown_sellers=qty_unknown,
        best_price=min_price,
        weighted_avg_price=avg,
        us_price_brl=us_price_brl,
        avg_margin_pct=margin,
        n_outliers_dropped=n_outliers,
    )
