"""Tests p/ olx_adapter — foco na robustez de acesso (fix 2026-06-05).

A OLX serve Cloudflare WAF managed-rule / IP-reputation block (a 1ª request
num IP frio às vezes passa, depois escala e mantém o block). Estes testes
travam:
  1. os seletores do parser __NEXT_DATA__ (não podem regredir);
  2. o parse de preço BR (ponto=milhar, vírgula=decimal);
  3. a detecção de página de block do Cloudflare;
  4. o retry/backoff do _UrllibFetcher (block transitório → recupera;
     RemoteDisconnected → retenta; tudo falha → propaga);
  5. o sinal honesto de bloqueio (SourceBlockedError) só quando TODAS as
     queries falham e nada é coletado — em vez de abortar no 1º block ou
     mascarar como "0 anúncios";
  6. o _FirecrawlFetcher (Tier 2): extrai rawHtml do envelope da API e passa
     pelo MESMO parser; block mesmo via proxy → SourceBlockedError honesto.
Tudo hermético: nenhum request real à OLX nem ao Firecrawl.
"""
import http.client
import pathlib
import urllib.error

import pytest

import olx_adapter as O
from lib.errors import SourceBlockedError

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "olx_search.html"

_BLOCK_HTML = (
    "<html><head><title>Attention Required! | Cloudflare</title></head>"
    "<body>Sorry, you have been blocked</body></html>"
)


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8")


def _http_403(url="https://www.olx.com.br/brasil?q=x"):
    return urllib.error.HTTPError(url, 403, "Forbidden", {}, None)


# --- 1. seletores do parser ------------------------------------------------
def test_parse_extrai_resultados_validos(html):
    results = O.parse_search_results(html)
    # 2 válidos; o sem-preço é descartado.
    assert len(results) == 2
    first = results[0]
    assert "Surging Sparks" in first["title"]
    assert first["price_brl"] == 1412.58
    assert str(first["list_id"]) == "1500000001"
    assert first["seller"] == "OLX (individual)"
    assert first["location"] == "São Paulo - SP"


def test_parse_marca_profissional(html):
    by_id = {str(r["list_id"]): r for r in O.parse_search_results(html)}
    assert by_id["1500000002"]["seller"] == "OLX (profissional)"
    assert by_id["1500000002"]["price_brl"] == 450.0


def test_parse_descarta_sem_preco(html):
    ids = {str(r["list_id"]) for r in O.parse_search_results(html)}
    assert "1500000003" not in ids  # priceValue null → fora


def test_parse_sem_next_data_retorna_vazio():
    assert O.parse_search_results("<html><body>nada</body></html>") == []


# --- 2. preço BR -----------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("R$ 1.412,58", 1412.58),
    ("R$ 450", 450.0),
    ("R$ 3.800", 3800.0),
    ("", None),
    ("combinar", None),
])
def test_price_to_float_br(text, expected):
    assert O._price_to_float(text) == expected


# --- 3. detecção de block --------------------------------------------------
def test_is_block_page_detecta_cloudflare():
    assert O._is_block_page(_BLOCK_HTML) is True


def test_is_block_page_falso_em_html_normal(html):
    assert O._is_block_page(html) is False


# --- 4. retry / backoff (_UrllibFetcher) -----------------------------------
def test_urllib_fetcher_recupera_apos_block(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(url, timeout=30):
        calls["n"] += 1
        if calls["n"] < 3:      # block nas 2 primeiras, OK na 3ª
            raise SourceBlockedError("olx", "block", "")
        return "<html>ok</html>"

    monkeypatch.setattr(O, "_fetch", fake_fetch)
    monkeypatch.setattr(O.time, "sleep", lambda *_: None)
    out = O._UrllibFetcher(retries=4, backoff=0.0).get_html("https://x")
    assert out == "<html>ok</html>"
    assert calls["n"] == 3


def test_urllib_fetcher_retenta_remote_disconnected(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(url, timeout=30):
        calls["n"] += 1
        if calls["n"] < 2:
            raise http.client.RemoteDisconnected("Remote end closed connection")
        return "<html>ok</html>"

    monkeypatch.setattr(O, "_fetch", fake_fetch)
    monkeypatch.setattr(O.time, "sleep", lambda *_: None)
    out = O._UrllibFetcher(retries=4, backoff=0.0).get_html("https://x")
    assert out == "<html>ok</html>"
    assert calls["n"] == 2


def test_urllib_fetcher_desiste_apos_retries(monkeypatch):
    def always_block(url, timeout=30):
        raise SourceBlockedError("olx", "block", "")

    monkeypatch.setattr(O, "_fetch", always_block)
    monkeypatch.setattr(O.time, "sleep", lambda *_: None)
    with pytest.raises(SourceBlockedError):
        O._UrllibFetcher(retries=3, backoff=0.0).get_html("https://x")


# --- 5. sinal de bloqueio honesto (fetch_listings) -------------------------
def _registry(n):
    return [{"id": f"sku{i}", "set": "Surging Sparks",
             "product_type": "Booster Box", "language": "EN"}
            for i in range(n)]


def test_bloqueio_total_levanta_source_blocked(monkeypatch):
    # _derive_queries do registry "Booster Box" → 1 query; força block nela.
    class _Blocked(O._Fetcher):
        def get_html(self, url):
            raise SourceBlockedError("olx", "block", "")

    monkeypatch.setattr(O, "_make_fetcher", lambda cfg: _Blocked())
    monkeypatch.setattr(O.time, "sleep", lambda *_: None)
    with pytest.raises(SourceBlockedError) as ei:
        O.fetch_listings({}, _registry(3))
    assert ei.value.source == "olx"


def test_nao_aborta_no_primeiro_block_se_outra_query_passa(monkeypatch, html):
    # registry com Booster Box + Sleeved Booster → 3 queries; uma falha, resto OK.
    reg = [
        {"id": "a", "product_type": "Booster Box", "language": "EN"},
        {"id": "b", "product_type": "Sleeved Booster", "language": "EN"},
    ]
    calls = {"n": 0}

    class _Flaky(O._Fetcher):
        def get_html(self, url):
            calls["n"] += 1
            if calls["n"] == 1:                 # 1ª query bloqueia
                raise SourceBlockedError("olx", "block", "")
            return html                          # demais entregam anúncios

    monkeypatch.setattr(O, "_make_fetcher", lambda cfg: _Flaky())
    monkeypatch.setattr(O.time, "sleep", lambda *_: None)
    out = O.fetch_listings({}, reg)
    assert out                                   # coletou → NÃO levanta block
    assert calls["n"] >= 2                        # não abortou no 1º block


def test_registry_vazio_erra():
    with pytest.raises(ValueError):
        O.fetch_listings({}, [])


# --- 6. _FirecrawlFetcher (Tier 2) -----------------------------------------
def test_firecrawl_fetcher_extrai_rawhtml(monkeypatch, html):
    captured = {}

    def fake_call(self, url):
        captured["url"] = url
        return {"success": True, "data": {"rawHtml": html}}

    monkeypatch.setattr(O._FirecrawlFetcher, "_call", fake_call)
    f = O._FirecrawlFetcher("fc-test")
    out = f.get_html("https://www.olx.com.br/brasil?q=booster+box")
    # o HTML retornado passa pelo MESMO parser sem alteração de transporte
    assert "__NEXT_DATA__" in out
    assert len(O.parse_search_results(out)) == 2
    assert captured["url"].startswith("https://www.olx.com.br/")


def test_firecrawl_fetcher_block_mesmo_via_proxy(monkeypatch):
    def fake_call(self, url):
        return {"success": True, "data": {"rawHtml": _BLOCK_HTML}}

    monkeypatch.setattr(O._FirecrawlFetcher, "_call", fake_call)
    with pytest.raises(SourceBlockedError):
        O._FirecrawlFetcher("fc-test").get_html("https://x")


def test_firecrawl_fetcher_vazio_erra(monkeypatch):
    def fake_call(self, url):
        return {"success": True, "data": {"rawHtml": ""}}

    monkeypatch.setattr(O._FirecrawlFetcher, "_call", fake_call)
    with pytest.raises(RuntimeError):
        O._FirecrawlFetcher("fc-test").get_html("https://x")


def test_make_fetcher_mode_desconhecido_erra():
    with pytest.raises(ValueError):
        O._make_fetcher({"mode": "telepatia"})


def test_make_fetcher_firecrawl_sem_key_erra(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("OLX_MODE", raising=False)
    monkeypatch.setattr(O, "_load_dotenv_if_present", lambda: None)
    with pytest.raises(RuntimeError):
        O._make_fetcher({"mode": "firecrawl"})
