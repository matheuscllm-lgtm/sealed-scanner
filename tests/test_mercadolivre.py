"""Tests do adapter Mercado Livre — herméticos (sem rede).

Cobrem o que o probe ao vivo 2026-06-06 mediu e o que a §10/§12 do handoff
alerta: parser dos seletores reais, a ARMADILHA do preço riscado (--previous
vem antes do atual no DOM), detecção do anti-bot próprio do ML
(account-verification, ≠ Cloudflare da OLX), BLOQUEADA honesto só quando TODAS
as queries falham, e o transporte Firecrawl (POST mockado, sem rede).
"""
import pathlib

import pytest

import mercadolivre_adapter as M
from lib.errors import SourceBlockedError

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "mercadolivre_search.html"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8")


# --- parser: seletores reais -------------------------------------------------
def test_parse_drops_card_without_price(html):
    # 4 cards na fixture; o sem-preço (card 4) é descartado → 3.
    rows = M.parse_search_results(html)
    assert len(rows) == 3


def test_parse_fields(html):
    rows = M.parse_search_results(html)
    en = next(r for r in rows if "Surging Sparks" in r["title"] and "English" in r["title"])
    assert en["price_brl"] == 1299.0
    assert en["ml_id"] == "MLB3399887766"
    assert "source" not in en  # source só é setado em fetch_listings, não no parser
    assert en["seller"].startswith("ML ")


def test_price_with_cents(html):
    rows = M.parse_search_results(html)
    copag = next(r for r in rows if "Copag" in r["title"])
    assert copag["price_brl"] == 208.89  # fraction 208 + cents 89


# --- ARMADILHA: preço riscado (--previous) vem ANTES do atual no DOM ---------
def test_strikethrough_price_picks_current_not_previous(html):
    rows = M.parse_search_results(html)
    promo = next(r for r in rows if "Prismatic" in r["title"])
    # DOM real medido: fractions=[449 (riscado), 413 (atual)]. Tem que pegar 413.
    assert promo["price_brl"] == 413.0
    assert promo["price_brl"] != 449.90


def test_no_previous_prices_leak():
    rows = M.parse_search_results(FIXTURE.read_text(encoding="utf-8"))
    assert 449.90 not in {r["price_brl"] for r in rows}


# --- detecção de block (anti-bot do ML, NÃO Cloudflare) ----------------------
def test_is_block_page_detects_ml_antibot():
    assert M._is_block_page("<html>...gz/account-verification...</html>")
    assert M._is_block_page("suspicious-traffic-frontend")


def test_is_block_page_ignores_cloudflare_and_normal():
    # tokens do CF (OLX) NÃO são block do ML; página normal também não.
    assert not M._is_block_page("you have been blocked")  # esse é o da OLX
    assert not M._is_block_page("<li class='ui-search-layout__item'>")


# --- price helper ------------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("1.299", 1299.0),
    ("1.412,58", 1412.58),
    ("R$ 75,05", 75.05),
    ("", None),
    ("grátis", None),
])
def test_price_to_float(text, expected):
    assert M._price_to_float(text) == expected


# --- id extraction -----------------------------------------------------------
def test_extract_id_from_mlb_url():
    assert M._extract_id("https://www.mercadolivre.com.br/x/p/MLB-3399887766#position=1") == "MLB3399887766"
    assert M._extract_id("https://produto.mercadolivre.com.br/MLB-3307553361-foo") == "MLB3307553361"


def test_extract_id_fallback_to_path():
    # Sem MLB id → estabiliza no path (não vira string vazia).
    assert M._extract_id("https://www.mercadolivre.com.br/algum-slug?x=1#y") == "/algum-slug"


# --- queries derivadas do registry ------------------------------------------
def test_derive_queries_only_en():
    reg = [
        {"language": "EN", "product_type": "Booster Box"},
        {"language": "PT", "product_type": "Elite Trainer Box"},  # PT → ignorado
        {"language": "EN", "product_type": "Tin"},
    ]
    qs = M._derive_queries(reg)
    assert "pokemon-booster-box-ingles" in qs
    assert "pokemon-tin-ingles" in qs
    assert "pokemon-elite-trainer-box-ingles" not in qs  # era PT


# --- fetch_listings: fetcher mockado (sem rede) ------------------------------
class _FakeFetcher:
    """Mock do _Fetcher: serve a fixture, ou levanta block, conforme configurado."""
    def __init__(self, html=None, block=False):
        self._html = html
        self._block = block
        self.calls = 0

    def get_html(self, url):
        self.calls += 1
        if self._block:
            raise SourceBlockedError("mercadolivre", "anti-bot (mock)", "hint")
        return self._html

    def close(self):
        pass


_REG = [{"language": "EN", "product_type": "Booster Box"}]


def test_fetch_listings_happy_path(monkeypatch, html):
    fake = _FakeFetcher(html=html)
    monkeypatch.setattr(M, "_make_fetcher", lambda cfg: fake)
    rows = M.fetch_listings({"mercadolivre": {}}, _REG)
    assert len(rows) == 3
    assert all(r["source"] == "mercadolivre" for r in rows)
    assert all(r["id"].startswith("ML-") for r in rows)
    # ids únicos por anúncio (dedup)
    assert len({r["ml_id"] for r in rows}) == 3


def test_fetch_listings_blocked_all_queries_raises(monkeypatch):
    # Todas as queries batem no anti-bot e nada coletado → BLOQUEADA honesto.
    fake = _FakeFetcher(block=True)
    monkeypatch.setattr(M, "_make_fetcher", lambda cfg: fake)
    with pytest.raises(SourceBlockedError):
        M.fetch_listings({"mercadolivre": {}}, _REG)


def test_fetch_listings_empty_registry_raises():
    with pytest.raises(ValueError):
        M.fetch_listings({"mercadolivre": {}}, [])


# --- transporte Firecrawl: POST mockado --------------------------------------
def test_firecrawl_fetcher_parses_rawhtml(monkeypatch, html):
    captured = {}

    def fake_call(self, url):
        captured["url"] = url
        return {"success": True, "data": {"rawHtml": html}}

    monkeypatch.setattr(M._FirecrawlFetcher, "_call", fake_call)
    fetcher = M._FirecrawlFetcher("fake-key", wait_ms=14000)
    out = fetcher.get_html("https://lista.mercadolivre.com.br/x")
    assert "ui-search-layout__item" in out
    assert captured["url"].startswith("https://lista.mercadolivre.com.br")


def test_firecrawl_fetcher_block_in_response_raises(monkeypatch):
    def fake_call(self, url):
        return {"success": True, "data": {"rawHtml": "<html>/gz/account-verification</html>"}}

    monkeypatch.setattr(M._FirecrawlFetcher, "_call", fake_call)
    fetcher = M._FirecrawlFetcher("fake-key")
    with pytest.raises(SourceBlockedError):
        fetcher.get_html("https://lista.mercadolivre.com.br/x")


def test_make_fetcher_firecrawl_needs_key(monkeypatch):
    monkeypatch.delenv("FIRECRAWL_API_KEY", raising=False)
    monkeypatch.delenv("MERCADOLIVRE_MODE", raising=False)
    monkeypatch.setattr(M, "_load_dotenv_if_present", lambda: None)
    with pytest.raises(RuntimeError, match="FIRECRAWL_API_KEY"):
        M._make_fetcher({"mode": "firecrawl"})


def test_make_fetcher_mode_default_is_firecrawl(monkeypatch):
    # firecrawl-first: sem mode explícito, default = firecrawl (≠ OLX urllib).
    monkeypatch.delenv("MERCADOLIVRE_MODE", raising=False)
    monkeypatch.setenv("FIRECRAWL_API_KEY", "fake-key")
    monkeypatch.setattr(M, "_load_dotenv_if_present", lambda: None)
    fetcher = M._make_fetcher({})
    assert isinstance(fetcher, M._FirecrawlFetcher)


# --- id ÚNICO entre queries (regressão: booster-box vs booster-bundle) --------
def test_fetch_listings_ids_unique_across_queries(monkeypatch):
    # Booster Box e Booster Bundle geram queries cujo 2º token é o mesmo
    # ("booster"). Antes do fix, slug=query.split("-")[1] + `kept` resetando por
    # query faziam dois anúncios DISTINTOS receberem o mesmo id "ML-booster-1".
    reg = [
        {"language": "EN", "product_type": "Booster Box"},
        {"language": "EN", "product_type": "Booster Bundle"},
    ]

    def _card(mlid, title):
        return (
            '<li class="ui-search-layout__item">'
            f'<a class="poly-component__title" href="https://www.mercadolivre.com.br/p/MLB-{mlid}">{title}</a>'
            '<div class="poly-price__current"><span class="andes-money-amount">'
            '<span class="andes-money-amount__fraction">100</span></span></div></li>'
        )

    class _PerQueryFetcher:
        # Cada query devolve um anúncio com ml_id diferente (senão o dedup por
        # ml_id removeria o 2º e a colisão de id nem apareceria).
        def get_html(self, url):
            mlid = "111" if "bundle" in url else "222"
            return "<html>" + _card(mlid, "Pokemon EN") + "</html>"

        def close(self):
            pass

    monkeypatch.setattr(M, "_make_fetcher", lambda cfg: _PerQueryFetcher())
    rows = M.fetch_listings({"mercadolivre": {}}, reg)
    assert len(rows) == 2
    ids = [r["id"] for r in rows]
    assert len(set(ids)) == len(ids)  # ids globalmente únicos entre queries
