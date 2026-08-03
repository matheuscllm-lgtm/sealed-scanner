"""Enriquecimento do lado de VENDA (eBay US) no pipeline — INFORMATIVO.

Invariantes travados:
  - `compute_margin` continua retornando EXATAMENTE as 4 chaves de sempre
    (a margem eBay vive em `compute_ebay_margin`, função separada);
  - `apply_ebay_reference` NUNCA muda campos de classificação
    (deal_confidence/bucket/main_risk/reject_reason/recommended_action);
  - referência ausente = no-op honesto (colunas vazias), nunca crash;
  - CSV ganha as 5 colunas eBay (sem "net"/"líquid") e `Margem vs eBay %`
    sai formatada ×100 como as demais margens;
  - orquestrador grava `run_meta.json` (rota + referências do run) e as
    contagens GREEN/YELLOW/RED são IDÊNTICAS com e sem referência eBay.
"""
import argparse
import copy
import csv
import json
import pathlib

import yaml

import sealed_arbitrage_scanner as S
import run_all_sources as ORQ

ROOT = pathlib.Path(__file__).resolve().parents[1]
TITLE = "Surging Sparks Booster Box (English)"
SKU_ID = "ssp-booster-box-en"


def _config():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


def _ebay_data(usd=350.0, status="ok", captured_at="2099-01-01T00:00:00Z"):
    entry = {"status": status}
    if status == "ok":
        entry.update({"usd": usd, "url": "https://www.ebay.com/itm/42", "junk_skipped": 0})
    return {
        "reference": "eBay US menor anúncio ativo (Browse API)",
        "captured_at": captured_at,
        "counts": {"ok": 1, "sem_anuncio": 0, "so_lixo": 0, "erro": 0},
        "entries": {SKU_ID: entry},
    }


def _high_row(price=500.0):
    row = S.ScanRow(listing_id="r1", title_br=TITLE, source="mock", seller="v",
                    url="u", price_brl=price, sku_id=SKU_ID, sku_name="SSP Box",
                    match_confidence="HIGH", deal_confidence="GREEN",
                    bucket="real_opportunities", main_risk="risco X",
                    recommended_action="ação Y", total_margin_pct=1.02)
    return row


# ── compute_ebay_margin ─────────────────────────────────────────────────────
def test_compute_ebay_margin_gross_formula_and_zero_guard():
    brl, margin = S.compute_ebay_margin(500.0, 200.0, 5.0)
    assert brl == 1000.0
    assert margin == 1.0                      # (1000-500)/500 — bruta, base compra
    brl0, margin0 = S.compute_ebay_margin(0.0, 200.0, 5.0)
    assert margin0 == 0.0                     # zero-guard: nunca divide por zero


def test_compute_margin_contract_unchanged():
    fin = S.compute_margin(100.0, 50.0, _config())
    assert set(fin) == {"us_price_brl", "gross_profit_brl", "total_margin_pct", "us_discount_pct"}


# ── apply_ebay_reference ────────────────────────────────────────────────────
_CLASSIFICATION_FIELDS = ("match_confidence", "deal_confidence", "bucket",
                          "main_risk", "recommended_action", "reject_reason",
                          "total_margin_pct", "us_discount_pct")


def test_enrichment_fills_fields_and_never_touches_classification():
    row = _high_row(price=500.0)
    before = {f: copy.deepcopy(getattr(row, f)) for f in _CLASSIFICATION_FIELDS}
    config = _config()
    config["currency"]["usd_brl"] = 5.0
    stats = S.apply_ebay_reference([row], _ebay_data(usd=350.0), config)
    assert stats["loaded"] and stats["ok"] == 1
    assert row.ebay_price_usd == 350.0
    assert row.ebay_price_brl == 1750.0
    assert row.ebay_margin_pct == 2.5         # (1750-500)/500, informativa
    assert row.ebay_url == "https://www.ebay.com/itm/42"
    assert row.ebay_status == "ok"
    after = {f: getattr(row, f) for f in _CLASSIFICATION_FIELDS}
    assert after == before                    # classificação byte-idêntica


def test_enrichment_none_is_noop():
    row = _high_row()
    assert S.apply_ebay_reference([row], None, _config()) == {"loaded": False}
    assert row.ebay_status == "" and row.ebay_price_usd is None


def test_enrichment_missing_entry_and_non_ok_status():
    config = _config()
    r1, r2 = _high_row(), _high_row()
    r2.sku_id = "outro-sku"
    data = _ebay_data(status="sem anúncio plausível")
    stats = S.apply_ebay_reference([r1, r2], data, config)
    assert r1.ebay_status == "sem anúncio plausível" and r1.ebay_price_usd is None
    assert r2.ebay_status == "sem_referencia_ebay"
    assert stats["outros"] == 1 and stats["sem"] == 1


def test_enrichment_skips_rows_without_sku():
    row = S.ScanRow(listing_id="x", title_br="?", source="mock", seller="v",
                    url="u", price_brl=100.0)   # NONE/REVIEW: sem sku_id
    S.apply_ebay_reference([row], _ebay_data(), _config())
    assert row.ebay_status == "" and row.ebay_price_usd is None


def test_settings_defaults_and_disable():
    assert S.ebay_reference_settings({})["enabled"] is True
    assert S.ebay_reference_settings({})["reference_file"] == "data/ebay_reference.json"
    cfg = {"route": {"extra_sell_references": {"ebay": {"enabled": False}}}}
    assert S.ebay_reference_settings(cfg)["enabled"] is False


# ── CSV ─────────────────────────────────────────────────────────────────────
def test_csv_has_ebay_columns_without_net_labels():
    labels = [lbl for _, lbl in S.CSV_COLUMNS]
    for expected in ("eBay menor anúncio (US$)", "eBay menor anúncio (R$)",
                     "Margem vs eBay %", "eBay URL", "Ref. eBay status"):
        assert expected in labels
    assert not any(("líquid" in l.lower()) or ("liquid" in l.lower()) for l in labels)


def test_cell_value_formats_ebay_margin_pct():
    row = _high_row()
    row.ebay_margin_pct = 0.4567
    assert S.cell_value(row, "ebay_margin_pct") == "45.67"
    row.ebay_margin_pct = None
    assert S.cell_value(row, "ebay_margin_pct") == ""


# ── orquestrador fim-a-fim (Namespace mínimo, estilo test_reference_guards) ──
def _run_orchestrator(tmp_path, monkeypatch, with_ebay: bool):
    monkeypatch.setattr(S, "resolve_fx_rate", lambda cfg: "manual (test)")
    monkeypatch.setattr(ORQ, "SCRIPT_DIR", tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    today = S.datetime.now(S.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (tmp_path / "data" / "us_reference.json").write_text(
        json.dumps({"captured_at": today, "prices": {SKU_ID: 200.0}}), encoding="utf-8")
    if with_ebay:
        (tmp_path / "data" / "ebay_reference.json").write_text(
            json.dumps(_ebay_data(usd=250.0, captured_at=today)), encoding="utf-8")
    listings = [{"id": "GOOD", "title": TITLE, "price_brl": 500.0, "seller": "v", "url": "u"},
                {"id": "MISS", "title": "Produto Aleatório XYZ", "price_brl": 50.0,
                 "seller": "v", "url": "u"}]
    mock = tmp_path / "listings.json"
    mock.write_text(json.dumps({"listings": listings}), encoding="utf-8")
    args = argparse.Namespace(
        sources="mock", mock=str(mock),
        config=str(ROOT / "config.yaml"), registry=str(ROOT / "sku_registry.yaml"),
    )
    assert ORQ.run(args) == 0
    out_dir = sorted((tmp_path / "results").glob("unified_*/"))[-1]
    rows = list(csv.DictReader((out_dir / "unified_deals.csv").open(encoding="utf-8")))
    return out_dir, rows


def test_orchestrator_without_ebay_file_runs_and_leaves_columns_empty(tmp_path, monkeypatch):
    out_dir, rows = _run_orchestrator(tmp_path, monkeypatch, with_ebay=False)
    good = next(r for r in rows if r["ID Anúncio"] == "GOOD")
    assert good["eBay menor anúncio (US$)"] == ""
    assert good["Ref. eBay status"] == ""     # arquivo ausente = no-op total, sem status
    meta = json.loads((out_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["schema"] == 1
    assert meta["ebay_ref_captured_at"] == ""
    assert meta["route_label"]                      # rota do config.yaml presente


def test_orchestrator_with_ebay_fills_columns_and_keeps_classification(tmp_path, monkeypatch):
    _, rows_without = _run_orchestrator(tmp_path, monkeypatch, with_ebay=False)
    out_dir, rows_with = _run_orchestrator(tmp_path, monkeypatch, with_ebay=True)

    def verdicts(rows):
        return {r["ID Anúncio"]: r["Confiança do deal"] for r in rows}

    assert verdicts(rows_with) == verdicts(rows_without)   # eBay NUNCA reclassifica

    good = next(r for r in rows_with if r["ID Anúncio"] == "GOOD")
    assert good["eBay menor anúncio (US$)"] == "250.0"
    assert float(good["eBay menor anúncio (R$)"]) == 250.0 * 5.05
    assert good["eBay URL"] == "https://www.ebay.com/itm/42"
    assert good["Ref. eBay status"] == "ok"
    # margem informativa ×100 com 2 casas (mesma formatação das demais margens)
    esperado = (250.0 * 5.05 - 500.0) / 500.0 * 100
    assert abs(float(good["Margem vs eBay %"]) - esperado) < 0.01

    meta = json.loads((out_dir / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["ebay_ref_captured_at"] != ""
    assert meta["ebay_stats"]["ok"] == 1
