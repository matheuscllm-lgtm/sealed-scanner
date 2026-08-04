"""Cliente eBay stdlib (`lib/ebay_client.py`) — referência do lado de VENDA.

Trava: sanitização BOM/zero-width (erro recorrente nº 1 da frota), gate
`.configured` (degradação honesta sem chaves), construção de URL com
`category_ids` OPCIONAL (default SEM filtro de categoria — não chutamos ID de
categoria de selados) e retry só em erros transitórios (429/5xx/rede).
100% offline: HTTP monkeypatchado via os aliases `_urlopen`/`_sleep`.
"""
import io
import json
import time
import urllib.error
import urllib.parse

import pytest

from lib import ebay_client as EC


# ── _clean_secret ───────────────────────────────────────────────────────────
def test_clean_secret_strips_bom_zero_width_whitespace():
    assert EC._clean_secret("\ufeffabc\u200b ") == "abc"


def test_clean_secret_invisible_only_is_empty():
    # chave SÓ de invisíveis NÃO pode passar como "configurada" (truthy).
    assert EC._clean_secret("\ufeff\u200b") == ""
    assert EC._clean_secret(None) == ""
    assert EC._clean_secret("") == ""


def test_configured_requires_both_keys(monkeypatch):
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    assert not EC.EbayClient().configured
    assert not EC.EbayClient(client_id="only-id").configured
    assert EC.EbayClient(client_id="a", client_secret="b").configured


def test_invisible_only_env_key_is_not_configured(monkeypatch):
    monkeypatch.setenv("EBAY_CLIENT_ID", "\ufeff\u200b")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "x")
    assert not EC.EbayClient().configured


# ── helpers de mock HTTP ────────────────────────────────────────────────────
class _Resp:
    def __init__(self, payload):
        self._body = json.dumps(payload).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _client_with_token() -> EC.EbayClient:
    c = EC.EbayClient(client_id="a", client_secret="b")
    c._token = "tok"
    c._token_expires_at = time.time() + 9999
    return c


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.ebay.com", code, "err", {}, io.BytesIO(b""))


def _query_of(url: str) -> dict:
    return urllib.parse.parse_qs(urllib.parse.urlparse(url).query)


# ── construção de URL/params ────────────────────────────────────────────────
def test_search_has_no_category_and_no_price_floor_by_default(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["marketplace"] = req.headers.get("X-ebay-c-marketplace-id")
        return _Resp({"itemSummaries": [{"title": "x"}]})

    monkeypatch.setattr(EC, "_urlopen", fake_urlopen)
    monkeypatch.setattr(EC, "_sleep", lambda s: None)
    items = _client_with_token().search("pokemon surging sparks booster box")
    assert items == [{"title": "x"}]
    q = _query_of(seen["url"])
    assert "category_ids" not in q          # 183454 é singles-only; selado = sem filtro
    assert q["sort"] == ["price"]
    assert q["limit"] == ["50"]
    filt = q["filter"][0]
    assert "itemLocationCountry:US" in filt  # mercado de venda = eBay US (Probstein)
    assert "buyingOptions:{FIXED_PRICE}" in filt
    assert "price:[" not in filt             # selado NÃO tem piso de preço
    assert seen["marketplace"] == "EBAY_US"


def test_search_category_ids_when_pinned(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        return _Resp({"itemSummaries": []})

    monkeypatch.setattr(EC, "_urlopen", fake_urlopen)
    monkeypatch.setattr(EC, "_sleep", lambda s: None)
    _client_with_token().search("q", category_ids="99999")
    assert _query_of(seen["url"])["category_ids"] == ["99999"]


def test_search_price_filter_only_when_asked(monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        return _Resp({})

    monkeypatch.setattr(EC, "_urlopen", fake_urlopen)
    monkeypatch.setattr(EC, "_sleep", lambda s: None)
    assert _client_with_token().search("q", min_price=10.0) == []
    filt = _query_of(seen["url"])["filter"][0]
    assert "price:[10..]" in filt
    assert "priceCurrency:USD" in filt


# ── retry ───────────────────────────────────────────────────────────────────
def test_search_retries_on_retryable_then_succeeds(monkeypatch):
    calls = {"n": 0}
    sleeps: list[float] = []

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        if calls["n"] < 3:
            raise _http_error(503)
        return _Resp({"itemSummaries": [{"title": "ok"}]})

    monkeypatch.setattr(EC, "_urlopen", fake_urlopen)
    monkeypatch.setattr(EC, "_sleep", sleeps.append)
    assert _client_with_token().search("q") == [{"title": "ok"}]
    assert calls["n"] == 3
    assert len(sleeps) == 3                  # throttle antes de CADA tentativa
    assert sleeps[1] > sleeps[0]             # espera escalonada


def test_search_does_not_retry_client_error(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        raise _http_error(400)

    monkeypatch.setattr(EC, "_urlopen", fake_urlopen)
    monkeypatch.setattr(EC, "_sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        _client_with_token().search("q")
    assert calls["n"] == 1                   # 400 = request errada, retry não conserta


def test_search_raises_after_retries_exhausted(monkeypatch):
    calls = {"n": 0}

    def fake_urlopen(req, timeout=0):
        calls["n"] += 1
        raise _http_error(503)

    monkeypatch.setattr(EC, "_urlopen", fake_urlopen)
    monkeypatch.setattr(EC, "_sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        _client_with_token().search("q")
    assert calls["n"] == EC.RETRIES
