"""Tests for pool_fill.py.

Fixtures usam DADOS REAIS do scan 2026-05-27 22:25 UTC + qtys capturadas
pelo adapter F1.5 (sprite imgunid). Outlier R$ 925.33 do PHF pack é typo
real da Liga e DEVE ser descartado pelo filtro de mediana.
"""
import pytest

from pool_fill import fill_pool


@pytest.fixture
def phf_pack_listings():
    """9 vendedores do PHF pack (pcode=134382) no scan 2026-05-27.
    qtys reais via F1.5; outlier R$ 925.33 incluído pra exercitar filtro."""
    return [
        {"seller": "loja#645953", "price_brl": 32.99, "qty_avail": None, "sku": "phf-pack-en"},
        {"seller": "loja#126907", "price_brl": 33.00, "qty_avail": 54,   "sku": "phf-pack-en"},
        {"seller": "loja#32035",  "price_brl": 34.90, "qty_avail": 5,    "sku": "phf-pack-en"},
        {"seller": "loja#597556", "price_brl": 35.00, "qty_avail": 6,    "sku": "phf-pack-en"},
        {"seller": "loja#64102",  "price_brl": 36.90, "qty_avail": 35,   "sku": "phf-pack-en"},
        {"seller": "loja#657636", "price_brl": 39.80, "qty_avail": 12,   "sku": "phf-pack-en"},
        {"seller": "loja#316637", "price_brl": 40.00, "qty_avail": 15,   "sku": "phf-pack-en"},
        {"seller": "loja#461",    "price_brl": 59.90, "qty_avail": 29,   "sku": "phf-pack-en"},
        {"seller": "loja#553317", "price_brl": 925.33, "qty_avail": 3,   "sku": "phf-pack-en"},  # outlier (typo)
    ]


@pytest.fixture
def po_box_listings():
    """7 vendedores do Perfect Order Box (pcode=135530), scan 2026-05-27."""
    return [
        {"seller": "loja#39542",  "price_brl": 899.70, "qty_avail": 10, "sku": "po-box-en"},
        {"seller": "loja#549403", "price_brl": 940.00, "qty_avail": 1,  "sku": "po-box-en"},
        {"seller": "loja#680279", "price_brl": 989.90, "qty_avail": 1,  "sku": "po-box-en"},
        {"seller": "loja#772665", "price_brl": 998.90, "qty_avail": 2,  "sku": "po-box-en"},
        {"seller": "loja#712975", "price_brl": 999.00, "qty_avail": 4,  "sku": "po-box-en"},
        {"seller": "loja#127360", "price_brl": 999.90, "qty_avail": 5,  "sku": "po-box-en"},
        {"seller": "loja#61167",  "price_brl": 999.99, "qty_avail": 8,  "sku": "po-box-en"},
    ]


def test_phf_pack_outlier_filtered(phf_pack_listings):
    """O vendedor R$ 925.33 (typo de R$ 32) deve ser filtrado por outlier."""
    result = fill_pool(
        listings=phf_pack_listings,
        sku="phf-pack-en",
        budget_brl=5000.0,
        us_price_brl=54.54,
        frete_unit=22.0,
        skip_qty_unknown=True,
    )
    sellers_used = [b.seller for b in result.breakdown]
    assert "loja#553317" not in sellers_used
    # E aparece na lista de skipped com motivo "outlier"
    skipped_sellers = {s for s, _ in result.skipped_sellers}
    assert "loja#553317" in skipped_sellers
    reason = next(r for s, r in result.skipped_sellers if s == "loja#553317")
    assert "outlier" in reason.lower()


def test_phf_pack_5k_fills_substantial_volume(phf_pack_listings):
    """Com 159 unidades de estoque real disponível e budget R$5k, devemos
    consolidar 120-140 packs com preço médio efetivo R$ 36-39 (real-data)."""
    result = fill_pool(
        listings=phf_pack_listings,
        sku="phf-pack-en",
        budget_brl=5000.0,
        us_price_brl=54.54,
        frete_unit=22.0,
        skip_qty_unknown=True,
    )
    assert 120 <= result.total_units <= 140, (
        f"esperado 120-140 unidades, got {result.total_units}"
    )
    assert 36.0 <= result.avg_price_per_unit <= 39.0, (
        f"esperado R$36-39 médio, got R${result.avg_price_per_unit:.2f}"
    )
    assert result.total_spent_brl <= 5000.0
    assert result.recomputed_margin_vs_us > 30.0  # PHF é um deal forte


def test_phf_pack_skipped_qty_unknown(phf_pack_listings):
    """loja#645953 tem qty_avail=None — deve ser pulada com skip_qty_unknown=True."""
    result = fill_pool(
        listings=phf_pack_listings,
        sku="phf-pack-en",
        budget_brl=5000.0,
        us_price_brl=54.54,
        frete_unit=22.0,
        skip_qty_unknown=True,
    )
    sellers_used = {b.seller for b in result.breakdown}
    assert "loja#645953" not in sellers_used


def test_phf_pack_qty_unknown_as_pessimist_default(phf_pack_listings):
    """skip_qty_unknown=False → qty=None vira qty=1 (pior caso, vendedor irrelevante)."""
    result = fill_pool(
        listings=phf_pack_listings,
        sku="phf-pack-en",
        budget_brl=5000.0,
        us_price_brl=54.54,
        frete_unit=22.0,
        skip_qty_unknown=False,
        min_qty_per_seller=1,
    )
    # loja#645953 entra no candidato pool mas com qty=1 + frete=22 → eff R$ 54.99,
    # ainda viável mas pouco atraente. Pode ou não ser usado dependendo do greedy.
    # O importante: a função não crasha.
    assert result.total_units > 0


def test_phf_pack_min_qty_filter(phf_pack_listings):
    """min_qty_per_seller=10 filtra qty=5 (loja#32035), qty=6 (loja#597556), qty=3 (outlier)."""
    result = fill_pool(
        listings=phf_pack_listings,
        sku="phf-pack-en",
        budget_brl=5000.0,
        us_price_brl=54.54,
        frete_unit=22.0,
        skip_qty_unknown=True,
        min_qty_per_seller=10,
    )
    sellers_used = {b.seller for b in result.breakdown}
    assert "loja#32035" not in sellers_used  # qty=5
    assert "loja#597556" not in sellers_used  # qty=6
    # qty>=10: 126907(54), 64102(35), 657636(12), 316637(15), 461(29)
    assert len(sellers_used) <= 5


def test_po_box_5k(po_box_listings):
    """Perfect Order Box: 31 unidades estoque disponível.
    Budget R$5k cobre ~5-6 boxes. Preço efetivo próximo ao melhor preço (R$900-960)."""
    result = fill_pool(
        listings=po_box_listings,
        sku="po-box-en",
        budget_brl=5000.0,
        us_price_brl=1122.86,
        frete_unit=50.0,
        skip_qty_unknown=True,
    )
    assert 4 <= result.total_units <= 7
    assert 850 <= result.avg_price_per_unit <= 970
    assert result.recomputed_margin_vs_us > 10  # PO Box ainda dá margem


def test_po_box_smaller_budget(po_box_listings):
    """Budget R$ 1k = 1 box do mais barato (R$899.70 + R$50 frete = R$949.70)."""
    result = fill_pool(
        listings=po_box_listings,
        sku="po-box-en",
        budget_brl=1000.0,
        us_price_brl=1122.86,
        frete_unit=50.0,
        skip_qty_unknown=True,
    )
    assert result.total_units == 1
    assert result.breakdown[0].seller == "loja#39542"  # menor preço
    assert result.breakdown[0].unit_price == 899.70


def test_empty_listings_returns_zero():
    result = fill_pool(
        listings=[],
        sku="nonexistent",
        budget_brl=5000.0,
        us_price_brl=100.0,
        frete_unit=20.0,
    )
    assert result.total_units == 0
    assert result.total_spent_brl == 0.0
    assert result.avg_price_per_unit == 0.0


def test_max_effective_price_filter(phf_pack_listings):
    """max_effective_price descarta long-tail caro."""
    result = fill_pool(
        listings=phf_pack_listings,
        sku="phf-pack-en",
        budget_brl=5000.0,
        us_price_brl=54.54,
        frete_unit=22.0,
        skip_qty_unknown=True,
        max_effective_price=40.0,  # rejeita loja#461 (R$ 59.90)
    )
    sellers_used = {b.seller for b in result.breakdown}
    assert "loja#461" not in sellers_used


# --------------------------------------------------------------------------
# Modelo de frete FLAT final (operador 2026-05-28):
#   frete = flat_base_pct × gasto  +  flat_per_seller_brl × (n_lojas − 1)
#   base = perna internacional + 1a loja; per_seller = doméstico por loja
#   adicional. Budget é TOTAL (produtos + frete <= budget).
# --------------------------------------------------------------------------
def test_flat_freight_multi_seller(phf_pack_listings):
    """PHF pack R$5k, flat final. Frete = 5% do gasto + R$17 por loja extra."""
    result = fill_pool(
        listings=phf_pack_listings,
        sku="phf-pack-en",
        budget_brl=5000.0,
        us_price_brl=54.54,
        freight_model="flat",
        flat_base_pct=0.05,
        flat_per_seller_brl=17.0,
        skip_qty_unknown=True,
    )
    assert result.freight_model == "flat"
    assert result.n_sellers_used >= 2
    # frete = 5% do gasto + R$17 por loja alem da 1a
    expected_freight = result.total_spent_brl * 0.05 + 17.0 * (result.n_sellers_used - 1)
    assert abs(result.total_freight_brl - expected_freight) < 0.01
    assert result.total_outlay_brl <= 5000.01
    assert abs(result.total_spent_brl + result.total_freight_brl - result.total_outlay_brl) < 0.01
    assert abs(result.avg_price_per_unit - result.total_outlay_brl / result.total_units) < 0.01


def test_flat_freight_single_seller(po_box_listings):
    """Budget R$ 1200 TOTAL em PO Box. Frete single (R$60=5%) sai do budget →
    produtos com R$1140 → 1 box (R$899.70) do vendedor mais barato → 1 loja."""
    result = fill_pool(
        listings=po_box_listings,
        sku="po-box-en",
        budget_brl=1000.0,
        us_price_brl=1122.86,
        freight_model="flat",
        flat_base_pct=0.05,
        flat_per_seller_brl=17.0,
        skip_qty_unknown=True,
    )
    assert result.n_sellers_used == 1
    assert result.total_units == 1
    # 1 loja: frete = 5% × 899.70 + R$17×0 = 44.99 (sem custo por loja extra)
    assert abs(result.total_freight_brl - 899.70 * 0.05) < 0.01
    assert abs(result.total_outlay_brl - (899.70 + 899.70 * 0.05)) < 0.01
    assert result.total_outlay_brl <= 1000.01


def test_flat_freight_thin_pool_not_punished():
    """Pool fino (poucas unidades) NAO leva frete cheio do budget — era o bug
    do modelo A. Com B: 2 packs a R$32-33 = frete 7% × 65, nao 7% × 5000."""
    thin = [
        {"seller": "lojaA", "price_brl": 32.0, "qty_avail": 1},
        {"seller": "lojaB", "price_brl": 33.0, "qty_avail": 1},
    ]
    result = fill_pool(
        listings=thin,
        sku="thin",
        budget_brl=5000.0,
        us_price_brl=44.55,
        freight_model="flat",
        flat_base_pct=0.05,
        flat_per_seller_brl=17.0,
        skip_qty_unknown=True,
    )
    assert result.total_units == 2
    # 2 lojas: frete = 5% × 65 + R$17×1 = 3.25 + 17 = 20.25 (nao 7% × 5000)
    assert abs(result.total_freight_brl - (65.0 * 0.05 + 17.0)) < 0.01
    assert result.recomputed_margin_vs_us > 0


def test_flat_freight_comes_out_of_budget(phf_pack_listings):
    """Garante que outlay NUNCA passa do budget (frete é interno, não adicional)."""
    for budget in (1000.0, 5000.0, 10000.0):
        result = fill_pool(
            listings=phf_pack_listings,
            sku="phf-pack-en",
            budget_brl=budget,
            us_price_brl=54.54,
            freight_model="flat",
            flat_base_pct=0.05,
            flat_per_seller_brl=17.0,
            skip_qty_unknown=True,
        )
        assert result.total_outlay_brl <= budget + 0.01, (
            f"budget {budget}: outlay {result.total_outlay_brl} passou do budget"
        )


def test_flat_freight_margin_includes_shipping(phf_pack_listings):
    """No flat, a margem vs US é recomputada COM frete no custo."""
    result = fill_pool(
        listings=phf_pack_listings,
        sku="phf-pack-en",
        budget_brl=5000.0,
        us_price_brl=54.54,
        freight_model="flat",
        flat_base_pct=0.05,
        flat_per_seller_brl=17.0,
        skip_qty_unknown=True,
    )
    expected_margin = (54.54 - result.avg_price_per_unit) / result.avg_price_per_unit * 100
    assert abs(result.recomputed_margin_vs_us - expected_margin) < 0.1


def test_flat_freight_empty_pool_zero_freight():
    """Pool vazio → 0 unidades, 0 frete (não cobra frete sem comprar nada)."""
    result = fill_pool(
        listings=[],
        sku="x",
        budget_brl=5000.0,
        us_price_brl=100.0,
        freight_model="flat",
    )
    assert result.total_units == 0
    assert result.total_freight_brl == 0.0
    assert result.total_outlay_brl == 0.0
