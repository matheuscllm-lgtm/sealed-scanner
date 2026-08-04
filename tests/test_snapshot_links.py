"""Coluna `Links` combinada da entrega de selados (`scripts/snapshot.py`).

Trava o padrão cross-scanner do operador (2026-06-19), ATUALIZADO em 2026-08-03
com o 3º link do lado de VENDA: `[oferta](url) · [TCG](url) · [eBay](url)`
(modelo de tabela do MYP). `oferta` = anúncio BR; `TCG` = referência que
classifica; `eBay` = menor anúncio ativo no eBay US (mercado de venda via
Probstein) — presente SÓ quando a referência eBay do run cobriu o SKU (URL
lida do CSV, nunca inventada). Sem nenhum link, '—'.
"""
import os
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "scripts")
)
import snapshot  # noqa: E402


def test_links_cell_combines_oferta_tcg_and_ebay(monkeypatch):
    monkeypatch.setitem(snapshot.TCG_PRODUCT_IDS, "SKU-TEST", "12345")
    r = {
        "URL": "https://produto.mercadolivre.com.br/abc",
        "SKU": "SKU-TEST",
        "eBay URL": "https://www.ebay.com/itm/42",
    }
    cell = snapshot.links_cell(r)
    assert cell == (
        "[oferta](https://produto.mercadolivre.com.br/abc) · "
        "[TCG](https://www.tcgplayer.com/product/12345) · "
        "[eBay](https://www.ebay.com/itm/42)"
    )


def test_links_cell_without_ebay_keeps_two_link_form(monkeypatch):
    # SKU sem referência eBay (coluna vazia OU CSV antigo sem a coluna):
    # a célula mantém a forma clássica de 2 links — nunca inventamos URL.
    monkeypatch.setitem(snapshot.TCG_PRODUCT_IDS, "SKU-TEST", "12345")
    for extra in ({"eBay URL": ""}, {}):
        r = {"URL": "https://produto.mercadolivre.com.br/abc", "SKU": "SKU-TEST", **extra}
        cell = snapshot.links_cell(r)
        assert cell == (
            "[oferta](https://produto.mercadolivre.com.br/abc) · "
            "[TCG](https://www.tcgplayer.com/product/12345)"
        )
        assert "eBay" not in cell


def test_links_cell_only_offer_when_no_tcg():
    r = {"URL": "https://olx.com.br/x", "SKU": "SKU-SEM-ID"}
    cell = snapshot.links_cell(r)
    assert cell == "[oferta](https://olx.com.br/x)"
    assert "TCG" not in cell


def test_links_cell_dash_when_empty():
    assert snapshot.links_cell({"URL": "", "SKU": ""}) == "—"


def test_md_link_encodes_raw_spaces_and_apostrophe():
    # Site Liga One Piece emite URL com espaço CRU e apóstrofo no prod=
    # (visto no 1º scan OP real, 2026-08-03) — link com espaço não abre a
    # página na entrega. Encodamos sem re-encodar %XX existentes.
    url = ("https://www.ligaonepiece.com.br/?view=prod/view&pcode=136997"
           "&prod=(ING) Booster Avulso - OP-17 - The World's Strongest Warriors")
    cell = snapshot.md_link("oferta", url)
    assert " " not in cell.split("](")[1]
    assert "%20" in cell
    assert "%27" in cell  # apóstrofo
    assert "pcode=136997" in cell


def test_md_link_encodes_parentheses():
    # URLs da Liga têm parênteses crus no prod= ((ING), (Kit Pré-Lançamento)).
    # Em `[label](url)` o `)` cru fecha o link no primeiro parêntese e o wrap
    # `<url>` não é respeitado por todo renderizador (oferta truncada no
    # remote-control, operador 2026-08-04) — tem que virar %28/%29.
    url = ("https://www.ligapokemon.com.br/?view=prod/view&pcode=133774"
           "&prod=(ING)%20Booster%20Avulso")
    cell = snapshot.md_link("oferta", url)
    dest = cell[len("[oferta]("):-1]
    assert "(" not in dest and ")" not in dest
    assert "%28ING%29" in dest
    assert "<" not in cell and ">" not in cell
    assert cell.startswith("[oferta](") and cell.endswith(")")


def test_md_link_does_not_double_encode_existing_percent():
    url = "https://www.ligapokemon.com.br/?view=prod/view&pcode=1&prod=Caixa%20X"
    cell = snapshot.md_link("oferta", url)
    assert "%2520" not in cell
    assert cell == "[oferta](https://www.ligapokemon.com.br/?view=prod/view&pcode=1&prod=Caixa%20X)"
