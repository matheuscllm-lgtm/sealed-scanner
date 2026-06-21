"""Guards FP-safe da referência US (parecer do revisor 2026-06-21).

Defendem o modo de falha histórico — referência US errada/velha inflando margem
em GREEN falso — sem tocar na precisão do match:

1. `build_us_reference` exclui preço FORA da faixa plausível do tipo de produto
   (pid errado/variante trocada num refresh) -> SKU fica sem referência -> RED.
2. `run()` rebaixa GREEN -> YELLOW quando a referência passou da validade.

Ambos só REDUZEM falsos positivos; nunca criam um deal.
"""
import argparse
import csv
import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sealed_arbitrage_scanner as S  # noqa: E402
import build_us_reference as B  # noqa: E402

TITLE = "Surging Sparks Booster Box (English)"
SKU_ID = "ssp-booster-box-en"


# ── 1. sanity-band guard (build_us_reference) ──────────────────────────────
def test_sanity_band_excludes_out_of_band_price():
    band = B.SANITY_BANDS_USD["Mini Tin"]
    # um bundle de US$230 pego por engano num SKU Mini Tin: fora da faixa.
    assert not (band[0] <= 230.0 <= band[1])
    # e um mini-tin legítimo de US$46.6 está dentro.
    assert band[0] <= 46.6 <= band[1]


def test_sanity_bands_accept_real_modern_prices():
    # preços reais (tcgcsv 2026-06) caem DENTRO das faixas — não rejeitam deal bom.
    cases = [
        ("Sleeved Booster", 15.83),
        ("Booster Bundle", 95.8),
        ("Elite Trainer Box", 602.8),
        ("Booster Box", 596.53),
        ("Premium Collection", 981.28),
        ("Mini Tin", 46.6),
        ("Tech Sticker", 45.55),
    ]
    for ptype, price in cases:
        lo, hi = B.SANITY_BANDS_USD[ptype]
        assert lo <= price <= hi, f"{ptype} {price} fora de {lo}-{hi}"


def test_unknown_product_type_has_no_band():
    assert B.SANITY_BANDS_USD.get("Nonexistent Type") is None


# ── 2. freshness guard (reference_age_days + run downgrade) ─────────────────
def test_reference_age_days_parses_and_handles_garbage():
    assert S.reference_age_days(None) is None
    assert S.reference_age_days("não-é-data") is None
    # uma data bem antiga dá idade grande e positiva.
    assert S.reference_age_days("2000-01-01T00:00:00Z") > 9000


def _run_scan_with_captured_at(tmp_path, monkeypatch, captured_at, us_price=200.0):
    monkeypatch.setattr(S, "resolve_fx_rate", lambda cfg: "manual (test)")
    monkeypatch.setattr(S, "SCRIPT_DIR", tmp_path)
    (tmp_path / "data").mkdir()
    # referência PINADA (200 USD * 5.05 / 500 -> 102%, GREEN robusto) + captured_at controlado.
    (tmp_path / "data" / "us_reference.json").write_text(
        json.dumps({"captured_at": captured_at, "prices": {SKU_ID: us_price}}), encoding="utf-8"
    )
    listings = [{"id": "GOOD", "title": TITLE, "price_brl": 500.0, "seller": "v", "url": "u"}]
    mock = tmp_path / "listings.json"
    mock.write_text(json.dumps({"listings": listings}), encoding="utf-8")
    args = argparse.Namespace(
        source="mock", mock=str(mock),
        config=str(ROOT / "config.yaml"), registry=str(ROOT / "sku_registry.yaml"),
        pool_budget="", pool_cep="", pool_min_qty=1,
    )
    assert S.run(args) == 0
    out_dir = sorted((tmp_path / "results").glob("*/"))[-1]

    def bucket(name):
        p = out_dir / f"{name}.csv"
        return {r["ID Anúncio"] for r in csv.DictReader(p.open(encoding="utf-8"))} if p.exists() else set()

    return bucket("real_opportunities"), bucket("review_required")


def test_fresh_reference_keeps_green(tmp_path, monkeypatch):
    # captured_at de HOJE (idade 0) -> GREEN mantido.
    today = S.datetime.now(S.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    green, yellow = _run_scan_with_captured_at(tmp_path, monkeypatch, today)
    assert "GOOD" in green
    assert "GOOD" not in yellow


def test_stale_reference_downgrades_green_to_yellow(tmp_path, monkeypatch):
    # captured_at antigo (> 14 dias) -> GREEN rebaixado p/ YELLOW (revisão).
    green, yellow = _run_scan_with_captured_at(tmp_path, monkeypatch, "2000-01-01T00:00:00Z")
    assert "GOOD" not in green
    assert "GOOD" in yellow
