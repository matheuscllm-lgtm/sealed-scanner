"""Coluna `Links` combinada da entrega de selados (`scripts/snapshot.py`).

Trava o padrão cross-scanner do operador (2026-06-19): link da oferta (anúncio BR)
+ referência TCGplayer na MESMA coluna, formato `[oferta](url) · [TCG](url)`
(modelo de tabela do MYP). Antes os links ficavam embutidos nas células de preço.
"""
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import snapshot  # noqa: E402


def test_links_cell_combines_oferta_and_tcg(monkeypatch):
    monkeypatch.setitem(snapshot.TCG_PRODUCT_IDS, "SKU-TEST", "12345")
    r = {"URL": "https://produto.mercadolivre.com.br/abc", "SKU": "SKU-TEST"}
    cell = snapshot.links_cell(r)
    assert cell == (
        "[oferta](https://produto.mercadolivre.com.br/abc) · "
        "[TCG](https://www.tcgplayer.com/product/12345)"
    )


def test_links_cell_only_offer_when_no_tcg():
    r = {"URL": "https://olx.com.br/x", "SKU": "SKU-SEM-ID"}
    cell = snapshot.links_cell(r)
    assert cell == "[oferta](https://olx.com.br/x)"
    assert "TCG" not in cell


def test_links_cell_dash_when_empty():
    assert snapshot.links_cell({"URL": "", "SKU": ""}) == "—"
