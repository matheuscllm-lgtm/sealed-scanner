"""Garante que o scanner é 100% margem BRUTA.

Regra do operador:
  - GREEN  = match HIGH + margem bruta >= 30%
  - YELLOW = match ambíguo (REVIEW: 1 anúncio casa com 2+ SKUs) — NUNCA por margem
  - RED    = sem match, sem referência US, preço inválido/baixo, ou margem < 30%
  - Margem líquida NÃO é calculada nem exibida em lugar nenhum.
  - Custos operacionais ficam FORA do scanner.
"""
import dataclasses
import pathlib

import yaml
import pytest

import sealed_arbitrage_scanner as S

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def registry():
    data = yaml.safe_load((ROOT / "sku_registry.yaml").read_text(encoding="utf-8"))
    return S.build_registry(data)


@pytest.fixture(scope="module")
def config():
    return yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))


# US ref controlado (não depende do JSON real): só o booster box do Surging Sparks.
US_REF = {"ssp-booster-box-en": 100.0}


def _row(title, price):
    return S.ScanRow(listing_id="t1", title_br=title, source="mock",
                     seller="v", url="u", price_brl=price)


# --- estrutura: zero margem líquida em qualquer saída ------------------------
def test_no_net_margin_columns():
    keys = [k for k, _ in S.CSV_COLUMNS]
    labels = [lbl for _, lbl in S.CSV_COLUMNS]
    assert not any("net" in k for k in keys), keys
    assert not any(("líquid" in lbl.lower()) or ("liquid" in lbl.lower()) for lbl in labels), labels


def test_scanrow_has_no_net_fields():
    names = {f.name for f in dataclasses.fields(S.ScanRow)}
    assert "net_profit_brl" not in names
    assert "net_margin_pct" not in names


def test_compute_margin_is_gross_only(config):
    fin = S.compute_margin(100.0, 50.0, config)
    assert set(fin) == {"us_price_brl", "gross_profit_brl", "total_margin_pct", "us_discount_pct"}
    assert not any("net" in k for k in fin)


def test_config_has_no_operational_costs(config):
    assert "fees" not in config
    assert "frete" not in config
    assert "review_floor_pct" not in config.get("deal_criteria", {})


# --- classificação por margem bruta ------------------------------------------
def test_green_is_high_match_and_gross_margin(registry, config):
    fx = config["currency"]["usd_brl"]
    us_brl = 100.0 * fx
    price = us_brl * 0.5  # margem bruta = 100% -> >= 30%
    row = S.classify(_row("Surging Sparks Booster Box (English)", price),
                     registry, US_REF, config)
    assert row.match_confidence == "HIGH"
    assert row.deal_confidence == "GREEN"
    assert row.bucket == "real_opportunities"
    assert row.total_margin_pct >= 0.30


def test_margin_band_30_to_40_is_green_not_yellow(registry, config):
    # Antes (modelo antigo) 30-40% era YELLOW. Agora YELLOW é só match ambíguo,
    # então ~35% de margem bruta com match HIGH tem de ser GREEN (dead elif morto).
    fx = config["currency"]["usd_brl"]
    us_brl = 100.0 * fx
    price = us_brl / 1.35  # margem bruta ~= 35%
    row = S.classify(_row("Surging Sparks Booster Box (English)", price),
                     registry, US_REF, config)
    assert row.deal_confidence == "GREEN"


def test_low_gross_margin_is_red(registry, config):
    fx = config["currency"]["usd_brl"]
    us_brl = 100.0 * fx
    price = us_brl * 0.95  # margem bruta ~5% < 30%
    row = S.classify(_row("Surging Sparks Booster Box (English)", price),
                     registry, US_REF, config)
    assert row.match_confidence == "HIGH"
    assert row.deal_confidence == "RED"
    assert row.reject_reason == "margem_total_abaixo_do_minimo"


def test_anomalous_margin_is_red_not_false_green(registry, config):
    # Margem absurda (>= review_above_margin_pct) num match HIGH é artefato —
    # acessório barato casando SKU caro — não oportunidade. Reproduz o
    # falso-GREEN do "151 Binder Collection" (fichário avulso ~R$230 vs US$240).
    # Tem de cair em RED `margem_anomala`, NUNCA GREEN nem YELLOW.
    assert config["deal_criteria"].get("review_above_margin_pct") is not None
    fx = config["currency"]["usd_brl"]
    us_brl = 100.0 * fx
    price = us_brl / 5.0  # margem bruta ~400% (acima do teto de 200%)
    row = S.classify(_row("Surging Sparks Booster Box (English)", price),
                     registry, US_REF, config)
    assert row.match_confidence == "HIGH"
    assert row.deal_confidence == "RED"
    assert row.bucket == "rejected"
    assert row.reject_reason == "margem_anomala"


def test_high_but_plausible_margin_stays_green(registry, config):
    # Logo ABAIXO do teto continua GREEN: o guard não engole oportunidade real.
    fx = config["currency"]["usd_brl"]
    us_brl = 100.0 * fx
    ceiling = config["deal_criteria"]["review_above_margin_pct"]  # 2.0
    price = us_brl / (1 + (ceiling - 0.2))  # margem ~ (teto - 20pp)
    row = S.classify(_row("Surging Sparks Booster Box (English)", price),
                     registry, US_REF, config)
    assert row.deal_confidence == "GREEN"
    assert row.total_margin_pct < ceiling


def test_no_match_is_red(registry, config):
    row = S.classify(_row("Produto Aleatório Sem Set Conhecido XYZ", 500.0),
                     registry, US_REF, config)
    assert row.match_confidence == "NONE"
    assert row.deal_confidence == "RED"


def test_no_us_reference_is_red(registry, config):
    # HIGH-match num SKU fora do US_REF -> RED sem_referencia_us (nunca inventa preço).
    row = S.classify(_row("Surging Sparks Elite Trainer Box (English)", 500.0),
                     registry, US_REF, config)
    assert row.match_confidence == "HIGH"
    assert row.deal_confidence == "RED"
    assert row.reject_reason == "sem_referencia_us"


def test_yellow_is_ambiguous_match_only(config):
    # Dois SKUs casam o mesmo título -> REVIEW -> YELLOW (independe de margem).
    a = S.Sku(id="x-a", name="A", product_type="Elite Trainer Box", set_name="X",
              language="EN", set_terms=["setx"], type_terms=["elite trainer box"],
              exclude_terms=[])
    b = S.Sku(id="x-b", name="B", product_type="Elite Trainer Box", set_name="X",
              language="EN", set_terms=["setx"], type_terms=["elite trainer box"],
              exclude_terms=[])
    row = S.classify(_row("SetX Elite Trainer Box", 500.0), [a, b],
                     {"x-a": 100.0, "x-b": 100.0}, config)
    assert row.match_confidence == "REVIEW"
    assert row.deal_confidence == "YELLOW"
    assert row.bucket == "review_required"


# --- preço inválido -> RED (não crash, não falso GREEN) ----------------------
def test_parse_price_defensive():
    assert S._parse_price("88.5") == 88.5
    assert S._parse_price(None) == 0.0
    assert S._parse_price("") == 0.0
    assert S._parse_price("R$ 100") == 0.0  # malformado -> 0.0


def test_invalid_price_is_red_never_false_green(registry, config):
    # Preço malformado vira 0.0 (via _parse_price) e 0.0 < preço mínimo -> RED.
    # NUNCA vira GREEN (preço 0 daria margem infinita se não fosse barrado).
    price = S._parse_price("R$ 100")  # -> 0.0
    row = S.classify(_row("Surging Sparks Booster Box (English)", price),
                     registry, US_REF, config)
    assert row.deal_confidence == "RED"
    assert row.reject_reason == "abaixo_do_preco_minimo"
