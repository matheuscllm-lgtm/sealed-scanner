"""Painel: /api/analysis read-only (última análise do jogo; 404 sem artefato)."""
import json

import pytest
from fastapi.testclient import TestClient

import panel
import snapshot


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(snapshot, "RESULTS", tmp_path)
    return TestClient(panel.app), tmp_path


ANALYSIS = {
    "scan_dir": "unified_x", "simulated": False, "cycle_days": 24,
    "net_factor": 0.70, "generated_at": "2026-08-29T00:00:00Z",
    "products": [{"sku_id": "ssp-etb-en", "produto": "SSP ETB",
                  "product_type": "Elite Trainer Box",
                  "buy": {"price_brl": 190.0},
                  "sell_now": {"gross_usd": 58.0},
                  "signals": {"price_trend": {"label": "alta"},
                              "supply": {"label": "caindo"},
                              "reprint_risk": {"label": "medio (SEM_EVIDENCIA)"}},
                  "expected": {"lucro_hoje_brl": 18.4,
                               "por_horizonte": {"60": {"lucro_esperado_brl": 30.0,
                                                        "valor_de_esperar_brl": 8.0}}},
                  "recommendation": {"state": "MANTER_60D", "confidence_pct": 75,
                                     "best_horizon_days": 60,
                                     "next_review_date": "2026-09-28",
                                     "catalyst": "oferta caindo", "risk": "-"},
                  "score": {"total": 70}}],
}


def test_api_analysis_404_sem_artefato(client):
    c, _ = client
    r = c.get("/api/analysis?game=pokemon")
    assert r.status_code == 404
    assert "analyze_sealed" in r.json()["detail"]


def test_api_analysis_le_ultimo_artefato(client):
    c, root = client
    d = root / "analysis_20260829_1"
    d.mkdir(parents=True)
    (d / "analysis.json").write_text(json.dumps(ANALYSIS), encoding="utf-8")
    r = c.get("/api/analysis?game=pokemon")
    assert r.status_code == 200
    body = r.json()
    assert body["analysis_dir"] == "analysis_20260829_1"
    assert body["count"] == 1
    p = body["products"][0]
    assert p["state"] == "MANTER_60D"
    assert p["lucro_esperado_brl"] == 30.0 and p["valor_de_esperar_brl"] == 8.0
    assert p["tendencia"] == "alta" and p["oferta"] == "caindo"


def test_api_analysis_jogo_invalido(client):
    c, _ = client
    assert c.get("/api/analysis?game=digimon").status_code == 422


def test_index_tem_aba_analise(client):
    c, _ = client
    html = c.get("/").text
    assert 'id="view"' in html and "Análise" in html
