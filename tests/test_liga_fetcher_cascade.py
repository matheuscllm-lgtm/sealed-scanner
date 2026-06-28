"""Regressão do bug da CASCATA de navegação do fetcher local da Liga.

Cenário real (2026-06-27): uma página de produto com defeito (ex. blister
pcode 133961 -> ERR_HTTP_RESPONSE_CODE_FAILURE) fazia o `page.goto` falhar.
Como o `_LocalChromeFetcher` reaproveita UMA page por scan, a navegação de erro
(chrome-error://) ainda estava assentando quando o próximo `get()` disparava o
goto seguinte -> "interrupted by another navigation" -> CASCATEAVA e derrubava a
LISTAGEM das categorias seguintes (26/27/28/38/57 = Boxes + Prerelease).

Contrato do fix (liga_adapter._LocalChromeFetcher.get):
  1. Em falha de goto, estabiliza a página (wait_for_load_state) antes de seguir.
  2. RE-ERGUE a exceção (o caller loga "[aviso] ... falhou" e segue p/ o próximo).
  3. NÃO fecha/recria a page — fechar mata o contexto e os cookies do Cloudflare
     (foi a 1ª tentativa de fix, que quebrou o browser inteiro e foi revertida).
"""
from unittest.mock import MagicMock

import pytest

import liga_adapter as L


def _fetcher_with_mock_page(page):
    """Constrói o fetcher driblando `_ensure` (sem browser real)."""
    f = L._LocalChromeFetcher(headless=True)
    f._ctx = MagicMock()      # não-None -> _ensure() retorna cedo
    f._page = page
    return f


def test_goto_failure_stabiliza_e_reergue():
    page = MagicMock()
    page.goto.side_effect = Exception("net::ERR_HTTP_RESPONSE_CODE_FAILURE")
    f = _fetcher_with_mock_page(page)

    with pytest.raises(Exception, match="ERR_HTTP_RESPONSE_CODE_FAILURE"):
        f.get("https://www.ligapokemon.com.br/?view=prod/view&pcode=133961")

    # estabilizou a página de erro antes de re-erguer
    page.wait_for_load_state.assert_called_once()
    # NÃO fechou nem recriou a page (regressão da 1ª tentativa de fix)
    page.close.assert_not_called()
    f._ctx.new_page.assert_not_called()
    assert f._page is page


def test_goto_failure_nao_propaga_erro_da_estabilizacao():
    # Se a própria estabilização falhar, ainda re-erguemos o erro ORIGINAL do goto
    page = MagicMock()
    page.goto.side_effect = Exception("erro original do goto")
    page.wait_for_load_state.side_effect = Exception("timeout estabilizando")
    f = _fetcher_with_mock_page(page)

    with pytest.raises(Exception, match="erro original do goto"):
        f.get("https://www.ligapokemon.com.br/?view=prod/view&pcode=133961")
    page.close.assert_not_called()


def test_goto_sucesso_segue_caminho_feliz(monkeypatch):
    # Caminho feliz: o try/except não pode quebrar o get() normal.
    monkeypatch.setattr(L.time, "sleep", lambda *a, **k: None)
    page = MagicMock()
    page.goto.return_value = None
    page.title.return_value = "Liga Pokémon - Produto"  # sem "moment"/"just a"
    page.content.return_value = "<html>ok</html>"
    f = _fetcher_with_mock_page(page)

    out = f.get("https://www.ligapokemon.com.br/?view=prod/view&pcode=136616")

    assert out == b"<html>ok</html>"
    page.goto.assert_called_once()
    page.wait_for_load_state.assert_not_called()  # só estabiliza em falha
    page.close.assert_not_called()
