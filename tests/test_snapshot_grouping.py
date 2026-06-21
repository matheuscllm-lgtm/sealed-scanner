"""Agrupamento por produto da entrega de selados (`scripts/snapshot.py`).

Trava o modelo de entrega 2026-06-20 (padrão MYP cross-scanner): a entrega
consolida os anúncios brutos pelo SKU canônico e expõe, por produto, a
**referência nacional** (menor BR disponível), a **referência TCGplayer**, a
quantidade total e o nº de ofertas, além da escada de unidades disponíveis.
"""
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import snapshot  # noqa: E402


def _row(**kw):
    """Linha mínima no formato do unified_deals.csv já enriquecido por
    collect_rows_unified (campos _bucket / _total)."""
    base = {
        "SKU": "meg-booster-bundle",
        "Produto (canônico)": "Mega Evolution Booster Bundle (English)",
        "Tipo": "Booster Bundle",
        "Coleção": "Mega Evolution",
        "Vendedor": "loja#1",
        "URL": "https://liga/x",
        "Preço BR (R$)": "180.00",
        "Qtd disponível": "5",
        "Preço US (US$)": "60.04",
        "Preço US (R$)": "300.00",
        "Margem total %": "66.7",
        "Risco principal": "",
        "_bucket": "real_opportunities",
        "_total": 66.7,
    }
    base.update(kw)
    return base


def test_groups_same_sku_into_one_product():
    rows = [
        _row(Vendedor="loja#A", **{"Preço BR (R$)": "179.00", "Qtd disponível": "1", "Margem total %": "67.6", "_total": 67.6}),
        _row(Vendedor="loja#B", **{"Preço BR (R$)": "185.00", "Qtd disponível": "10", "Margem total %": "62.2", "_total": 62.2}),
        _row(Vendedor="loja#C", **{"Preço BR (R$)": "190.00", "Qtd disponível": "4", "Margem total %": "57.9", "_total": 57.9}),
    ]
    groups = snapshot.group_products(rows)
    assert len(groups) == 1
    g = groups[0]
    assert g["n_ofertas"] == 3
    # referência nacional = menor BR disponível
    assert g["br_ref"] == 179.00
    # quantidade total = soma de todas as ofertas
    assert g["qtd_total"] == 15
    # referência TCG preservada
    assert g["tcg_brl"] == 300.00
    # escada ordenada por BR asc (unidade mais barata primeiro)
    assert [x["Vendedor"] for x in g["ladder"]] == ["loja#A", "loja#B", "loja#C"]


def test_margin_recomputed_on_national_reference():
    rows = [
        _row(**{"Preço BR (R$)": "100.00", "Preço US (R$)": "150.00", "Margem total %": "50.0", "_total": 50.0}),
        _row(Vendedor="loja#2", **{"Preço BR (R$)": "200.00", "Preço US (R$)": "150.00", "Margem total %": "-25.0", "_total": -25.0}),
    ]
    g = snapshot.group_products(rows)[0]
    assert g["br_ref"] == 100.00
    assert round(g["margem"], 1) == 50.0       # (150-100)/100
    assert round(g["delta"], 2) == 50.00


def test_best_bucket_wins_when_listings_mixed():
    rows = [
        _row(**{"_bucket": "rejected", "Preço BR (R$)": "300.00", "Margem total %": "0.0", "_total": 0.0}),
        _row(Vendedor="loja#2", **{"_bucket": "real_opportunities", "Preço BR (R$)": "179.00", "Margem total %": "67.6", "_total": 67.6}),
    ]
    g = snapshot.group_products(rows)[0]
    assert g["bucket"] == "real_opportunities"
    assert snapshot.group_status_label(g).startswith("🟢")


def test_distinct_skus_stay_separate_and_sorted_by_margin():
    rows = [
        _row(SKU="low", **{"Produto (canônico)": "Low", "Preço BR (R$)": "100", "Preço US (R$)": "120", "Margem total %": "20.0", "_total": 20.0, "_bucket": "rejected"}),
        _row(SKU="high", **{"Produto (canônico)": "High", "Preço BR (R$)": "100", "Preço US (R$)": "200", "Margem total %": "100.0", "_total": 100.0}),
    ]
    groups = snapshot.group_products(rows)
    assert [g["sku"] for g in groups] == ["high", "low"]  # melhor margem primeiro


def test_ambiguous_without_sku_grouped_by_title():
    rows = [
        _row(SKU="", **{"Produto (canônico)": "", "Título (BR)": "Caixa misteriosa", "Margem total %": "40.0", "_total": 40.0}),
        _row(SKU="", **{"Produto (canônico)": "", "Título (BR)": "Caixa misteriosa", "Vendedor": "loja#2", "Margem total %": "40.0", "_total": 40.0}),
    ]
    groups = snapshot.group_products(rows)
    assert len(groups) == 1
    assert groups[0]["n_ofertas"] == 2


def test_group_links_cell_uses_cheapest_offer():
    rows = [
        _row(Vendedor="caro", **{"Preço BR (R$)": "300", "URL": "https://liga/caro", "Margem total %": "0.0", "_total": 0.0}),
        _row(Vendedor="barato", **{"Preço BR (R$)": "179", "URL": "https://liga/barato", "Margem total %": "67.6", "_total": 67.6}),
    ]
    g = snapshot.group_products(rows)[0]
    cell = snapshot.group_links_cell(g)
    assert "https://liga/barato" in cell
    assert "https://liga/caro" not in cell
