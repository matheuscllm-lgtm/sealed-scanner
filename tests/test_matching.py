"""Tests para o matcher determinístico — foco na regra `era_umbrella`.

Casos reais pegos no scan 2026-06-03 (Amazon usa "Mega Evolution - <subset>"
como prefixo de era, o que fazia os SKUs meg-* da era casarem junto com o SKU
do sub-set → REVIEW ambíguo + avaliação perdida). A regra umbrella resolve isso
genericamente: quando um SKU umbrella casa junto com um sub-set específico, o
umbrella perde.
"""
import pathlib

import yaml
import pytest

import sealed_arbitrage_scanner as S

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "sku_registry.yaml"


@pytest.fixture(scope="module")
def registry():
    return S.build_registry(yaml.safe_load(REGISTRY.read_text(encoding="utf-8")))


def ids(title, reg):
    return sorted(s.id for s in S.match_listing(title, reg))


# --- a era Mega tem 5 SKUs umbrella (o set-base) -------------------------
def test_meg_skus_flagged_umbrella(registry):
    umbrella = {s.id for s in registry if s.era_umbrella}
    assert umbrella == {
        "meg-booster-box", "meg-sleeved-booster", "meg-booster-bundle",
        "meg-mini-tin", "meg-mini-tin-display",
    }


# --- sub-set prefixado pela era → resolve no sub-set, não no umbrella -----
@pytest.mark.parametrize("title,expected", [
    # Amazon "Mega Evolution - <subset>" (o bug que motivou a regra):
    ("Pokémon TCG: Mega Evolution—Phantasmal Flames Booster Bundle (6 Booster Packs)", "phf-bundle-en"),
    ("Pokémon TCG: Mega Evolution - Ascended Heroes - Booster Bundle - Inglês", "ah-bundle-en"),
    ("Pokemon TCG - Mega Evolution: Ascended Heroes 10-Card Booster Pack (English)", "ah-pack-en"),
    ("Pokémon TCG: Mega Evolution - Phantasmal Flames Booster Pack (10 Cards)", "phf-pack-en"),
    # Os 2 sub-sets que o band-aid antigo cobria seguem certos:
    ("Pokémon TCG: Mega Evolution - Perfect Order - Booster Bundle - Inglês", "po-bundle-en"),
    ("Pokémon TCG: Mega Evolution - Chaos Rising - Booster Bundle", "cr-bundle-en"),
])
def test_subset_beats_era_umbrella(title, expected, registry):
    assert ids(title, registry) == [expected]


# --- set-base puro (sem sub-set) → o umbrella é preservado ----------------
@pytest.mark.parametrize("title,expected", [
    ("Pokemon TCG Mega Evolution Booster Bundle Inglês", "meg-booster-bundle"),
    ("Mega Evolution Booster Box (English)", "meg-booster-box"),
])
def test_pure_base_set_keeps_umbrella(title, expected, registry):
    assert ids(title, registry) == [expected]


# --- ambiguidade legítima continua sendo REVIEW (não engolida pela regra) -
def test_legit_ambiguity_still_review(registry):
    # Anúncio nomeia os dois sets (White Flare / Black Bolt) — sem umbrella envolvido.
    dual = "Booster Avulso Fogo Branco / Raio Preto Pokémon TCG"
    assert len(S.match_listing(dual, registry)) == 2
