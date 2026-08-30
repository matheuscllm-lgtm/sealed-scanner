"""Port do histórico tcgcsv: datas clampadas, regra de preço não-reverse,
cache JSON, rejeição de corpo não-7z (magic byte) e pct_changes."""
import json
from datetime import date

import pytest

from lib import tcgcsv_history as hist


def test_target_dates_clampa_earliest_e_futuro():
    today = date(2024, 4, 1)
    out = hist.target_dates(today, (30, 90, 365))
    assert 30 in out and out[30] == date(2024, 3, 2)
    assert 90 not in out        # 2024-01-02 < EARLIEST (2024-02-08)
    assert 365 not in out


def test_best_market_ignora_reverse_e_pega_maior():
    rows = [{"productId": 1, "subTypeName": "Normal", "marketPrice": 10.0},
            {"productId": 1, "subTypeName": "Holofoil", "marketPrice": 12.0},
            {"productId": 1, "subTypeName": "Reverse Holofoil", "marketPrice": 99.0},
            {"productId": 2, "subTypeName": "Normal", "marketPrice": 0},
            {"productId": 3, "subTypeName": "Normal", "marketPrice": "x"}]
    assert hist._best_market_from_rows(rows) == {"1": 12.0}


def test_price_map_usa_cache_json(tmp_path):
    d = date(2026, 8, 1)
    (tmp_path / "cat3-2026-08-01.json").write_text(json.dumps({"77": 5.0}))
    assert hist.price_map_for_date(d, "3", tmp_path) == {"77": 5.0}


def test_price_map_retry_dias_anteriores(tmp_path, monkeypatch):
    # sem rede: o download é neutralizado — só o cache d-2 responde
    monkeypatch.setattr(hist, "_download", lambda d, c: None)
    d = date(2026, 8, 3)
    (tmp_path / "cat3-2026-08-01.json").write_text(json.dumps({"77": 5.0}))
    assert hist.price_map_for_date(d, "3", tmp_path) == {"77": 5.0}


def test_download_rejeita_corpo_nao_7z(tmp_path, monkeypatch):
    class FakeResp:
        def __init__(self, body):
            self.body = body

        def read(self):
            return self.body

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(hist.urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResp(b"<html>challenge</html>"))
    assert hist._download(date(2026, 8, 1), tmp_path) is None
    assert not list(tmp_path.glob("*.7z"))     # cache NÃO envenenado

    monkeypatch.setattr(hist.urllib.request, "urlopen",
                        lambda req, timeout=0: FakeResp(hist.MAGIC_7Z + b"resto"))
    ap = hist._download(date(2026, 8, 1), tmp_path)
    assert ap is not None and ap.read_bytes().startswith(hist.MAGIC_7Z)


def test_pct_changes():
    maps = {30: {"9": 100.0}, 90: {"9": 80.0}, 180: {}}
    out = hist.pct_changes("9", 110.0, maps)
    assert out[30] == pytest.approx(0.10)
    assert out[90] == pytest.approx(0.375)
    assert 180 not in out
    assert hist.pct_changes("9", 0.0, maps) == {}
