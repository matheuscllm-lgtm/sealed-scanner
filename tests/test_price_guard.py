"""Regressão (PR #22): preço malformado não vira falso GREEN nem derruba o run.

`run()` guarda o parse de `price_brl` (try/except -> 0.0). Um preço 0.0 cai no
filtro de preço mínimo -> RED, então um anúncio com preço lixo ("R$ 100", None,
"") nunca é GREEN — preço 0 daria margem infinita se não fosse barrado.
"""
import argparse
import csv
import json
import pathlib

import yaml
import pytest

import sealed_arbitrage_scanner as S

ROOT = pathlib.Path(__file__).resolve().parents[1]
# SKU real com referência US alta -> com preço válido baixo seria GREEN.
TITLE = "Surging Sparks Booster Box (English)"
SKU_ID = "ssp-booster-box-en"


@pytest.fixture(scope="module")
def registry():
    return S.build_registry(yaml.safe_load((ROOT / "sku_registry.yaml").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def test_classify_zero_price_is_red_not_green(registry, config):
    # Preço 0.0 (o que o guard de run() produz pra preço malformado) num SKU que
    # casa HIGH e tem referência US: tem de ser RED, jamais GREEN.
    row = S.ScanRow(listing_id="z", title_br=TITLE, source="mock", seller="v",
                    url="u", price_brl=0.0)
    out = S.classify(row, registry, {SKU_ID: 288.61}, config)
    assert out.match_confidence == "HIGH"
    assert out.deal_confidence == "RED"
    assert out.deal_confidence != "GREEN"
    assert out.reject_reason == "abaixo_do_preco_minimo"


def _read_bucket(out_dir, name):
    p = out_dir / f"{name}.csv"
    return list(csv.DictReader(p.open(encoding="utf-8"))) if p.exists() else []


def test_run_malformed_price_is_red_never_green(tmp_path, monkeypatch):
    # Trava o câmbio no fallback do config (sem rede).
    monkeypatch.setattr(S, "resolve_fx_rate", lambda cfg: "manual (test)")
    # Isola results/ e us_reference num tmp (run() usa SCRIPT_DIR pra ambos).
    monkeypatch.setattr(S, "SCRIPT_DIR", tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "us_reference.json").write_text(
        (ROOT / "data" / "us_reference.json").read_text(encoding="utf-8"), encoding="utf-8")

    listings = [
        {"id": "GOOD", "title": TITLE, "price_brl": 500.0, "seller": "v", "url": "u"},
        {"id": "BAD", "title": TITLE, "price_brl": "R$ 100", "seller": "v", "url": "u"},
    ]
    mock = tmp_path / "listings.json"
    mock.write_text(json.dumps({"listings": listings}), encoding="utf-8")

    args = argparse.Namespace(
        source="mock", mock=str(mock),
        config=str(ROOT / "config.yaml"), registry=str(ROOT / "sku_registry.yaml"),
        pool_budget="", pool_cep="", pool_min_qty=1,
    )
    rc = S.run(args)
    assert rc == 0  # preço lixo NÃO derruba o run inteiro

    out_dir = sorted((tmp_path / "results").glob("*/"))[-1]
    green = {r["ID Anúncio"] for r in _read_bucket(out_dir, "real_opportunities")}
    red = {r["ID Anúncio"] for r in _read_bucket(out_dir, "rejected")}

    assert "GOOD" in green          # controle: preço válido -> GREEN (teste não-vazio)
    assert "BAD" not in green       # preço malformado NUNCA é GREEN
    assert "BAD" in red             # preço malformado -> RED
