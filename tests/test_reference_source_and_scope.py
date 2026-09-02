"""Regressão das diretrizes do operador sobre referência e escopo (perfil OP):

1. Fonte de classificação configurável (`references.classification_source`):
   'ebay' faz a CLASSIFICAÇÃO (margem/GREEN) usar o menor anúncio ATIVO do
   eBay US; SKU sem anúncio plausível fica sem referência -> RED
   sem_referencia_us (nunca inventamos preço). Default ('tcg' / chave ausente)
   = comportamento histórico do Pokémon. Histórico no perfil OP: 2026-08-15
   virou ebay ("para one piece vamos tomar como referência eBay apenas");
   2026-09-02 REVERTIDO ("vamos tomar o tcg player como referencia principal
   e ebay secundaria") — o config real volta a 'tcg', e a máquina do modo
   ebay segue testada aqui com configs sintéticos.

2. "deixa decks de fora" — product_type listado em `scope.exclude` vira
   barreira DURA no classify (tipo_fora_do_escopo). No Pokémon o exclude só
   tem categorias que nunca são product_type de SKU -> no-op.
"""
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import sealed_arbitrage_scanner as S  # noqa: E402


def _config(**overrides):
    cfg = {
        "deal_criteria": {"min_total_margin_pct": 0.30,
                          "review_above_margin_pct": 2.0,
                          "max_reference_age_days": 1},
        "filters": {"min_brazil_price_brl": 0},
        "currency": {"usd_brl": 5.0},
        "scope": {},
        "references": {},
    }
    for k, v in overrides.items():
        cfg[k] = v
    return cfg


def _registry():
    return S.build_registry({"skus": [
        {"id": "op10-booster-box-en", "name": "Royal Blood Booster Box",
         "product_type": "Booster Box", "set_name": "Royal Blood",
         "match": {"set_terms": ["royal blood"],
                   "type_terms": ["booster box", "caixa de booster"],
                   "exclude_terms": []}},
        {"id": "st31-starter-deck-en", "name": "Starter Deck 31: RED Monkey.D.Luffy",
         "product_type": "Starter Deck", "set_name": "Starter Deck 31",
         "match": {"set_terms": ["st31", "st 31"],
                   "type_terms": ["starter deck", "deck inicial"],
                   "exclude_terms": []}},
    ]})


def _row(title, price):
    return S.ScanRow(listing_id="t1", title_br=title, source="liga",
                     seller="loja#1", url="https://example.com/x", price_brl=price)


# ── 1. fonte de referência configurável ────────────────────────────────────
def test_source_default_e_invalido_viram_tcg():
    assert S.classification_reference_source(_config()) == "tcg"
    assert S.classification_reference_source(
        _config(references={"classification_source": "banana"})) == "tcg"
    assert S.classification_reference_source(
        _config(references={"classification_source": "ebay"})) == "ebay"


def test_load_classification_reference_ebay(tmp_path):
    ebay = {"captured_at": "2026-08-15T12:00:00Z", "entries": {
        "op10-booster-box-en": {"usd": 250.0, "status": "ok", "url": "https://ebay.com/itm/1"},
        "op10-booster-pack-en": {"status": "sem anúncio plausível"},
    }}
    p = tmp_path / "ebay_ref.json"
    p.write_text(json.dumps(ebay), encoding="utf-8")
    cfg = _config(references={"classification_source": "ebay",
                              "ebay_file": p.name})
    ref_data, prices = S.load_classification_reference(cfg, tmp_path)
    # só status ok entra; sem anúncio plausível NÃO vira preço
    assert prices == {"op10-booster-box-en": 250.0}
    assert ref_data["captured_at"] == "2026-08-15T12:00:00Z"


def test_classify_ebay_ref_margem_e_sem_referencia():
    cfg = _config(references={"classification_source": "ebay"})
    reg = _registry()
    ebay_prices = {"op10-booster-box-en": 250.0}
    # com referência eBay: margem (250*5 - 888.20)/888.20 = 40.7% -> GREEN
    row = S.classify(_row("(ING) Caixa de Booster - OP-10 - Royal Blood", 888.20),
                     reg, ebay_prices, cfg)
    assert row.deal_confidence == "GREEN"
    assert row.us_price_usd == 250.0
    # sem referência eBay (SKU fora do dict): RED honesto, mensagem cita eBay
    row2 = S.classify(_row("(ING) Deck Inicial - ST-31 - RED Monkey.D.Luffy", 94.90),
                      reg, ebay_prices, cfg)
    assert row2.deal_confidence == "RED"
    assert row2.reject_reason == "sem_referencia_us"
    assert "eBay" in row2.main_risk


def test_rebuild_hint_por_fonte():
    assert S.reference_rebuild_hint(_config()) == "build_us_reference.py"
    assert S.reference_rebuild_hint(
        _config(references={"classification_source": "ebay"})) == "build_ebay_reference.py"


# ── 2. scope.exclude por product_type ──────────────────────────────────────
def test_starter_deck_excluido_por_scope():
    cfg = _config(scope={"exclude": ["Starter Deck", "Starter Deck Display"]},
                  references={"classification_source": "ebay"})
    reg = _registry()
    row = S.classify(_row("(ING) Deck Inicial - ST-31 - RED Monkey.D.Luffy", 94.90),
                     reg, {"st31-starter-deck-en": 30.0}, cfg)
    assert row.deal_confidence == "RED"
    assert row.reject_reason == "tipo_fora_do_escopo"
    # box segue normal com o mesmo config
    row2 = S.classify(_row("(ING) Caixa de Booster - OP-10 - Royal Blood", 888.20),
                      reg, {"op10-booster-box-en": 250.0}, cfg)
    assert row2.deal_confidence == "GREEN"


def test_exclude_pokemon_e_noop():
    """Exclude histórico do Pokémon (Raw Singles etc.) nunca casa product_type
    de SKU — comportamento intacto."""
    cfg = _config(scope={"exclude": ["Raw Singles", "Graded Cards",
                                     "Opened Products", "Damaged Products"]})
    reg = _registry()
    row = S.classify(_row("(ING) Caixa de Booster - OP-10 - Royal Blood", 888.20),
                     reg, {"op10-booster-box-en": 250.0}, cfg)
    assert row.deal_confidence == "GREEN"


def test_config_onepiece_do_repo_esta_com_as_diretrizes():
    """Trava o config real: classificação = TCG (operador 2026-09-02, reverte
    2026-08-15); eBay secundária/informativa; decks fora (categorias e scope)."""
    import yaml
    cfg = yaml.safe_load((pathlib.Path(__file__).resolve().parents[1]
                          / "config_onepiece.yaml").read_text(encoding="utf-8"))
    assert cfg["references"]["classification_source"] == "tcg"
    assert cfg["references"]["us_file"] == "data/us_reference_onepiece.json"
    # eBay segue como referência de VENDA secundária (colunas + link [eBay]).
    assert cfg["route"]["extra_sell_references"]["ebay"]["enabled"] is True
    assert (cfg["route"]["extra_sell_references"]["ebay"]["reference_file"]
            == "data/ebay_reference_onepiece.json")
    assert 36 not in cfg["liga"]["categorias"]
    assert "Starter Deck" in cfg["scope"]["exclude"]
    # Operador 2026-08-17 (lista BUSCAR): cases/collections/tins/gift no
    # escopo — Booster Box Case saiu do exclude; Latas(24) e Kits(38) entram.
    assert "Booster Box Case" not in cfg["scope"]["exclude"]
    for cat in (24, 38):
        assert cat in cfg["liga"]["categorias"]
    for t in ("Booster Box Case", "Treasure Booster Set", "Illustration Box",
              "Devil Fruits Collection", "Tin Pack Set", "Gift Collection"):
        assert t in cfg["scope"]["include"], t
