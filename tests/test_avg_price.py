"""Tests for avg_price_for_sku — preço médio ponderado por SKU (sem frete).

Caso de uso (operador 2026-06-05): estoque pequeno por vendedor → comprar
volume = varrer vários logistas a preços diferentes. A média ponderada pela
qty disponível é o custo real por unidade. Reusa o filtro de outlier do
fill_pool, então typos (ex.: R$ 925 num pack de R$ 33) são descartados.
"""
import pytest

from pool_fill import avg_price_for_sku, SkuAverage


def test_weighted_average_drops_outlier_and_weights_by_qty():
    # 8 vendedores reais + 1 outlier typo (R$ 925.33) que DEVE cair.
    listings = [
        {"seller": "a", "price_brl": 32.99, "qty_avail": None},  # qty desconhecida -> peso 1
        {"seller": "b", "price_brl": 33.00, "qty_avail": 54},
        {"seller": "c", "price_brl": 34.90, "qty_avail": 5},
        {"seller": "d", "price_brl": 35.00, "qty_avail": 6},
        {"seller": "e", "price_brl": 36.90, "qty_avail": 35},
        {"seller": "f", "price_brl": 39.80, "qty_avail": 12},
        {"seller": "g", "price_brl": 40.00, "qty_avail": 15},
        {"seller": "h", "price_brl": 59.90, "qty_avail": 29},
        {"seller": "typo", "price_brl": 925.33, "qty_avail": 3},  # outlier
    ]
    r = avg_price_for_sku(listings, us_price_brl=53.47, sku="phf-pack-en")
    assert isinstance(r, SkuAverage)
    assert r.n_outliers_dropped == 1          # o typo caiu
    assert r.n_sellers == 8                    # 8 mantidos
    assert r.qty_unknown_sellers == 1          # vendedor "a"
    assert r.total_qty == 157                  # 1+54+5+6+35+12+15+29
    assert r.best_price == pytest.approx(32.99)
    # média ponderada (sem o outlier): 6305.69 / 157 ~ 40.16
    assert r.weighted_avg_price == pytest.approx(40.16, abs=0.02)
    # margem total no preço médio: (53.47 - 40.16)/40.16*100 ~ 33.1%
    assert 32.0 < r.avg_margin_pct < 34.5


def test_no_qty_falls_back_to_simple_average():
    # Todas as qty desconhecidas -> peso 1 cada -> média simples.
    listings = [
        {"seller": "a", "price_brl": 100.0, "qty_avail": None},
        {"seller": "b", "price_brl": 120.0, "qty_avail": None},
    ]
    r = avg_price_for_sku(listings, us_price_brl=200.0)
    assert r.qty_unknown_sellers == 2
    assert r.total_qty == 2
    assert r.weighted_avg_price == pytest.approx(110.0)
    assert r.n_outliers_dropped == 0           # <3 listings -> sem filtro de mediana


def test_qty_weighting_pulls_average_toward_high_stock_seller():
    # Vendedor barato com MUITO estoque domina a média ponderada.
    listings = [
        {"seller": "cheap", "price_brl": 100.0, "qty_avail": 100},
        {"seller": "pricey", "price_brl": 200.0, "qty_avail": 1},
    ]
    r = avg_price_for_sku(listings, us_price_brl=150.0)
    # (100*100 + 200*1)/101 = 10200/101 ~ 100.99
    assert r.weighted_avg_price == pytest.approx(100.99, abs=0.02)
    assert r.total_qty == 101


def test_empty_listings_is_safe():
    r = avg_price_for_sku([], us_price_brl=50.0)
    assert r.n_sellers == 0
    assert r.total_qty == 0
    assert r.weighted_avg_price == 0.0
    assert r.avg_margin_pct == 0.0
