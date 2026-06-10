"""Tests p/ amazon_adapter — foco na robustez 503 (fix 2026-06-05).

A Amazon BR serve 503 anti-bot intermitente. Estes testes travam:
  1. os seletores do parser (não podem regredir silenciosamente);
  2. o parse de preço BR (ponto=milhar, vírgula=decimal);
  3. o retry/backoff transformando 503 transitório em sucesso;
  4. o sinal honesto de bloqueio (SourceBlockedError) quando tudo cai —
     em vez de mascarar como "0 anúncios".
Tudo hermético: nenhum request real à Amazon.
"""
import json
import pathlib
import urllib.error

import pytest

import amazon_adapter as A
from lib.errors import SourceBlockedError

FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "amazon_search.html"


@pytest.fixture(scope="module")
def html():
    return FIXTURE.read_text(encoding="utf-8")


def _http_503(url="https://www.amazon.com.br/s?k=x"):
    return urllib.error.HTTPError(url, 503, "Service Unavailable", {}, None)


def _http_404(url="https://www.amazon.com.br/s?k=x"):
    return urllib.error.HTTPError(url, 404, "Not Found", {}, None)


# --- 1. seletores do parser ------------------------------------------------
def test_parse_extrai_resultados_validos(html):
    results = A.parse_search_results(html)
    # 2 válidos; o sem-preço é descartado.
    assert len(results) == 2
    first = results[0]
    assert "Destined Rivals" in first["title"]
    assert first["price_brl"] == 489.90
    assert first["asin"] == "B0ABCDE123"
    assert first["url"].startswith("https://www.amazon.com.br/")


def test_parse_descarta_sem_preco(html):
    asins = {r["asin"] for r in A.parse_search_results(html)}
    assert "B0NOPRICE0" not in asins  # sem preço → fora


# --- 2. preço BR -----------------------------------------------------------
@pytest.mark.parametrize("text,expected", [
    ("R$ 1.412,58", 1412.58),
    ("R$ 489,90", 489.90),
    ("R$ 3.800", 3800.0),
    ("", None),
    ("grátis", None),
])
def test_price_to_float_br(text, expected):
    assert A._price_to_float(text) == expected


# --- 3. retry / backoff ----------------------------------------------------
def test_fetch_retry_recupera_apos_503(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(url, timeout=30):
        calls["n"] += 1
        if calls["n"] < 3:      # 503 nas 2 primeiras, OK na 3ª
            raise _http_503()
        return "<html>ok</html>"

    monkeypatch.setattr(A, "_fetch", fake_fetch)
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)  # não dorme no teste
    out = A._fetch_retry("https://x", attempts=3, base_sleep=0.0)
    assert out == "<html>ok</html>"
    assert calls["n"] == 3


def test_fetch_retry_propaga_404_sem_retry(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(url, timeout=30):
        calls["n"] += 1
        raise _http_404()

    monkeypatch.setattr(A, "_fetch", fake_fetch)
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    with pytest.raises(urllib.error.HTTPError):
        A._fetch_retry("https://x", attempts=3)
    assert calls["n"] == 1  # 404 não é retentável


def test_fetch_retry_desiste_apos_attempts(monkeypatch):
    monkeypatch.setattr(A, "_fetch", lambda *a, **k: (_ for _ in ()).throw(_http_503()))
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    with pytest.raises(urllib.error.HTTPError):
        A._fetch_retry("https://x", attempts=3)


# --- 4. sinal de bloqueio honesto -----------------------------------------
def _registry(n):
    return [{"id": f"sku{i}", "set": "Destined Rivals", "product_type": "booster box"}
            for i in range(n)]


# fallback_browser/firecrawl: False mantém estes testes no caminho urllib-puro,
# determinístico e SEM rede/browser (mesmo com FIRECRAWL_API_KEY no ambiente).
_NO_FC = {"amazon": {"fallback_firecrawl": False, "fallback_browser": False}}


def test_bloqueio_total_levanta_source_blocked(monkeypatch):
    def always_503(url, *a, **k):
        raise _http_503()

    monkeypatch.setattr(A, "_fetch_retry", always_503)
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    with pytest.raises(SourceBlockedError) as ei:
        A.fetch_listings(_NO_FC, _registry(5))
    assert ei.value.source == "amazon"


def test_sucesso_parcial_nao_levanta(monkeypatch, html):
    calls = {"n": 0}

    def half_fail(url, *a, **k):
        calls["n"] += 1
        if calls["n"] % 2 == 0:
            raise _http_503()
        return html

    monkeypatch.setattr(A, "_fetch_retry", half_fail)
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    out = A.fetch_listings(_NO_FC, _registry(5))
    assert out  # coletou anúncios → não é bloqueio


def test_registry_vazio_erra(monkeypatch):
    with pytest.raises(ValueError):
        A.fetch_listings({}, [])


# --- 5. fallback Firecrawl ------------------------------------------------
class _FakeResp:
    """Context manager que imita urllib.request.urlopen p/ a REST do Firecrawl."""
    def __init__(self, payload):
        self._b = json.dumps(payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self._b


def test_fetch_firecrawl_devolve_rawhtml(monkeypatch, html):
    monkeypatch.setattr(A, "_firecrawl_key", lambda: "fake-key")
    monkeypatch.setattr(A.urllib.request, "urlopen",
                        lambda req, timeout=90: _FakeResp({"success": True, "data": {"rawHtml": html}}))
    out = A._fetch_firecrawl("https://www.amazon.com.br/s?k=x")
    assert "s-search-result" in out


def test_fetch_firecrawl_sem_key_erra(monkeypatch):
    monkeypatch.setattr(A, "_firecrawl_key", lambda: None)
    with pytest.raises(RuntimeError):
        A._fetch_firecrawl("https://x")


def test_fetch_firecrawl_success_false_erra(monkeypatch):
    monkeypatch.setattr(A, "_firecrawl_key", lambda: "fake-key")
    monkeypatch.setattr(A.urllib.request, "urlopen",
                        lambda req, timeout=90: _FakeResp({"success": False, "error": "blocked"}))
    with pytest.raises(RuntimeError):
        A._fetch_firecrawl("https://x")


def test_firecrawl_recupera_quando_urllib_falha(monkeypatch, html):
    """urllib esgota → Firecrawl entrega → coleta anúncios, sem BLOQUEADA.
    (Firecrawl é opt-in desde 2026-06-10: precisa de fallback_firecrawl: true.)"""
    monkeypatch.setattr(A, "_fetch_retry", lambda url, *a, **k: (_ for _ in ()).throw(_http_503()))
    monkeypatch.setattr(A, "_firecrawl_key", lambda: "fake-key")
    monkeypatch.setattr(A, "_fetch_firecrawl", lambda url, **k: html)
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    cfg = {"amazon": {"fallback_browser": False, "fallback_firecrawl": True}}
    out = A.fetch_listings(cfg, _registry(3))
    assert out  # recuperado via Firecrawl


def test_bloqueio_real_so_quando_ambas_rotas_falham(monkeypatch):
    """urllib E Firecrawl falham → aí sim SourceBlockedError honesto."""
    monkeypatch.setattr(A, "_fetch_retry", lambda url, *a, **k: (_ for _ in ()).throw(_http_503()))
    monkeypatch.setattr(A, "_firecrawl_key", lambda: "fake-key")
    monkeypatch.setattr(A, "_fetch_firecrawl",
                        lambda url, **k: (_ for _ in ()).throw(RuntimeError("fc down")))
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    cfg = {"amazon": {"fallback_browser": False, "fallback_firecrawl": True}}
    with pytest.raises(SourceBlockedError):
        A.fetch_listings(cfg, _registry(5))


# --- 6. fallback browser ($0, default desde 2026-06-10) --------------------
class _FakeBrowser:
    """Dublê da _BrowserSession — sem Chrome real no teste."""
    def __init__(self, html=None, exc=None):
        self.html, self.exc = html, exc
        self.calls = 0
        self.closed = False

    def get_html(self, url):
        self.calls += 1
        if self.exc is not None:
            raise self.exc
        return self.html

    def close(self):
        self.closed = True


def test_browser_recupera_quando_urllib_falha(monkeypatch, html):
    """urllib esgota → browser ($0) entrega → coleta anúncios, sem BLOQUEADA."""
    fake = _FakeBrowser(html=html)
    monkeypatch.setattr(A, "_BrowserSession", lambda **k: fake)
    monkeypatch.setattr(A, "_fetch_retry", lambda url, *a, **k: (_ for _ in ()).throw(_http_503()))
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    out = A.fetch_listings({}, _registry(3))  # default: browser ON, firecrawl OFF
    assert out
    assert fake.calls >= 1
    assert fake.closed  # sessão fechada no fim do run


def test_firecrawl_default_off_nao_dispara(monkeypatch):
    """Default 2026-06-10: com browser falhando e firecrawl SEM opt-in, NÃO
    gasta crédito (mesmo com key no ambiente) → bloqueio honesto."""
    fc = {"n": 0}
    fake = _FakeBrowser(exc=RuntimeError("browser down"))
    monkeypatch.setattr(A, "_BrowserSession", lambda **k: fake)
    monkeypatch.setattr(A, "_fetch_retry", lambda url, *a, **k: (_ for _ in ()).throw(_http_503()))
    monkeypatch.setattr(A, "_firecrawl_key", lambda: "fake-key")

    def fc_spy(url, **k):
        fc["n"] += 1
        return "<html></html>"

    monkeypatch.setattr(A, "_fetch_firecrawl", fc_spy)
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    with pytest.raises(SourceBlockedError):
        A.fetch_listings({}, _registry(5))
    assert fc["n"] == 0  # nenhum crédito gasto


def test_escada_browser_depois_firecrawl(monkeypatch, html):
    """Com firecrawl opt-in: urllib falha → browser falha → firecrawl entrega."""
    fake = _FakeBrowser(exc=RuntimeError("browser down"))
    monkeypatch.setattr(A, "_BrowserSession", lambda **k: fake)
    monkeypatch.setattr(A, "_fetch_retry", lambda url, *a, **k: (_ for _ in ()).throw(_http_503()))
    monkeypatch.setattr(A, "_firecrawl_key", lambda: "fake-key")
    monkeypatch.setattr(A, "_fetch_firecrawl", lambda url, **k: html)
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    cfg = {"amazon": {"fallback_firecrawl": True}}
    out = A.fetch_listings(cfg, _registry(3))
    assert out  # recuperado via Firecrawl no degrau 3


def test_fetch_retry_browser_nao_retenta_block(monkeypatch):
    """SourceBlockedError (captcha real) propaga na hora — retry não resolve."""
    fake = _FakeBrowser(exc=SourceBlockedError("amazon", "captcha", "hint"))
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    with pytest.raises(SourceBlockedError):
        A._fetch_retry_browser(fake, "https://x", attempts=3)
    assert fake.calls == 1
