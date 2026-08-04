"""Painel local read-only (`panel.py`) — endpoints sobre o último scan.

Trava:
  - fonte única: /api/products devolve OS MESMOS grupos/margens do
    snapshot.group_products (a entrega) sobre as mesmas linhas;
  - matriz de filtros de /api/deals (bucket/fonte/margem/busca);
  - 404 instrutivo quando não há scan do jogo;
  - NENHUM endpoint escreve nada (read-only de verdade);
  - página única embutida servida em '/'.
100% offline (fixture CSV + monkeypatch da raiz de resultados do snapshot).
"""
import csv
import json
import pathlib
import sys

import pytest
from fastapi.testclient import TestClient

import sealed_arbitrage_scanner as S

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import snapshot  # noqa: E402
import panel  # noqa: E402

LABELS = [label for _, label in S.CSV_COLUMNS]


def _row(**kw):
    base = {label: "" for label in LABELS}
    base.update(kw)
    return base


def _write_scan(root: pathlib.Path, rows: list[dict], meta: dict | None = None):
    scan = root / "unified_20260803_120000"
    scan.mkdir(parents=True)
    with (scan / "unified_deals.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=LABELS)
        w.writeheader()
        w.writerows(rows)
    if meta is not None:
        (scan / "run_meta.json").write_text(json.dumps(meta), encoding="utf-8")
    return scan


@pytest.fixture()
def client(tmp_path, monkeypatch):
    rows = [
        _row(**{"ID Anúncio": "LIGA-1-1", "Título (BR)": "Surging Sparks Booster Box (English)",
                "Fonte": "liga", "Vendedor": "loja#1", "URL": "https://liga/x",
                "Preço BR (R$)": "500.0", "Qtd disponível": "3",
                "SKU": "ssp-booster-box-en",
                "Produto (canônico)": "Surging Sparks Booster Box (English)",
                "Tipo": "Booster Box", "Coleção": "Surging Sparks",
                "Preço US (US$)": "200.0", "Câmbio USD/BRL": "5.0",
                "Preço US (R$)": "1000.0", "Lucro bruto (R$)": "500.0",
                "Margem total %": "100.00", "Mais barato que US %": "50.00",
                "eBay menor anúncio (US$)": "180.0", "eBay menor anúncio (R$)": "900.0",
                "Margem vs eBay %": "80.00", "eBay URL": "https://www.ebay.com/itm/9",
                "Ref. eBay status": "ok",
                "Confiança do match": "HIGH", "Confiança do deal": "GREEN"}),
        _row(**{"ID Anúncio": "OLX-2-1", "Título (BR)": "Produto aleatório sem match",
                "Fonte": "olx", "URL": "https://olx/y", "Preço BR (R$)": "50.0",
                "Margem total %": "0.00",
                "Confiança do match": "NONE", "Confiança do deal": "RED",
                "Motivo de rejeição": "sem_match_no_registry"}),
    ]
    meta = {"schema": 1, "game": "pokemon", "route_label": "rota-teste",
            "fx": 5.0, "fx_source": "manual (test)",
            "us_ref_captured_at": "2099-01-01T00:00:00Z",
            "ebay_ref_captured_at": "2099-01-01T00:00:00Z",
            "ebay_stats": {"ok": 1, "sem": 0, "outros": 0}}
    _write_scan(tmp_path / "results", rows, meta)
    monkeypatch.setattr(snapshot, "RESULTS", tmp_path / "results")
    panel._PID_CACHE.clear()
    return TestClient(panel.app)


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert "pokemon" in r.json()["games"]


def test_index_serves_embedded_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "painel local" in r.text
    assert "somente leitura" in r.text


def test_status(client):
    st = client.get("/api/status", params={"game": "pokemon"}).json()
    assert st["scan_dir"] == "unified_20260803_120000"
    assert st["route_label"] == "rota-teste"
    assert st["buckets"] == {"GREEN": 1, "YELLOW": 0, "RED": 1}
    assert st["registry_skus"] > 100          # registry Pokémon real carregado


def test_deals_filters(client):
    all_ = client.get("/api/deals", params={"game": "pokemon"}).json()
    assert all_["count"] == 2
    green = client.get("/api/deals", params={"game": "pokemon", "bucket": "GREEN"}).json()
    assert [d["id"] for d in green["deals"]] == ["LIGA-1-1"]
    assert green["deals"][0]["tcg_url"].endswith("/product/565606")   # pid REAL do registry
    assert green["deals"][0]["ebay_url"] == "https://www.ebay.com/itm/9"
    src = client.get("/api/deals", params={"game": "pokemon", "source": "OLX"}).json()
    assert [d["id"] for d in src["deals"]] == ["OLX-2-1"]
    high = client.get("/api/deals", params={"game": "pokemon", "min_margin": 200}).json()
    assert high["count"] == 0
    q = client.get("/api/deals", params={"game": "pokemon", "q": "surging"}).json()
    assert q["count"] == 1


def test_products_matches_snapshot_grouping(client, tmp_path):
    resp = client.get("/api/products", params={"game": "pokemon"}).json()
    scan_dir = tmp_path / "results" / "unified_20260803_120000"
    expected = snapshot.group_products(snapshot.collect_rows_unified(scan_dir))
    assert resp["count"] == len(expected)
    got_green = next(p for p in resp["products"] if p["bucket"] == "GREEN")
    exp_green = next(g for g in expected if g["bucket"] == "real_opportunities")
    assert got_green["margem_pct"] == exp_green["margem"]     # fonte única, por construção
    assert got_green["ebay_brl"] == exp_green["ebay_brl"]
    assert got_green["oferta_url"] == "https://liga/x"


def test_404_when_game_has_no_scan(client):
    r = client.get("/api/deals", params={"game": "onepiece"})
    assert r.status_code == 404
    assert "run_all_sources.py --game onepiece" in r.json()["detail"]


def test_unknown_game_is_422(client):
    assert client.get("/api/status", params={"game": "magic"}).status_code == 422


def test_endpoints_are_read_only(client, tmp_path):
    scan_dir = tmp_path / "results" / "unified_20260803_120000"
    before = sorted(p.name for p in scan_dir.iterdir())
    for url, params in [("/api/status", {"game": "pokemon"}),
                        ("/api/deals", {"game": "pokemon"}),
                        ("/api/products", {"game": "pokemon"}),
                        ("/api/routes", {}), ("/health", {}), ("/", {})]:
        client.get(url, params=params)
    assert sorted(p.name for p in scan_dir.iterdir()) == before


def test_routes_endpoint_reads_configs(client):
    r = client.get("/api/routes").json()
    assert "pokemon" in r and "onepiece" in r
    assert "Probstein" in r["pokemon"].get("label", "")
