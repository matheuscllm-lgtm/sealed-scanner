"""Tests p/ amazon_adapter — foco na robustez 503 (fix 2026-06-05).

A Amazon BR serve 503 anti-bot intermitente. Estes testes travam:
  1. os seletores do parser (não podem regredir silenciosamente);
  2. o parse de preço BR (ponto=milhar, vírgula=decimal);
  3. o retry/backoff transformando 503 transitório em sucesso;
  4. o sinal honesto de bloqueio (SourceBlockedError) quando tudo cai —
     em vez de mascarar como "0 anúncios".
Tudo hermético: nenhum request real à Amazon.
"""
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


def test_bloqueio_total_levanta_source_blocked(monkeypatch):
    def always_503(url, *a, **k):
        raise _http_503()

    monkeypatch.setattr(A, "_fetch_retry", always_503)
    monkeypatch.setattr(A.time, "sleep", lambda *_: None)
    with pytest.raises(SourceBlockedError) as ei:
        A.fetch_listings({}, _registry(5))
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
    out = A.fetch_listings({}, _registry(5))
    assert out  # coletou anúncios → não é bloqueio


def test_registry_vazio_erra(monkeypatch):
    with pytest.raises(ValueError):
        A.fetch_listings({}, [])
