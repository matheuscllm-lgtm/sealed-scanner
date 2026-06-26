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


# --- guard de carta avulsa: single NÃO casa box SKU (margem fantasma) ------
def test_single_card_nao_casa_box(registry):
    # Caso real (scan Amazon 2026-06-06): single promo cujo título cita o set E
    # "Elite Trainer Box" casava pre-etb-en → +272% fantasma. Agora: 0 candidatos.
    fantasma = "Pokemon - Eevee SVP 173 – Prismatic Evolutions – Elite Trainer Box Promo - Single Card"
    assert S.match_listing(fantasma, registry) == []


def test_selado_real_ainda_casa(registry):
    # O ETB selado de verdade do mesmo set NÃO pode ser barrado pelo guard.
    real = "Pokémon TCG Prismatic Evolutions Elite Trainer Box (English)"
    assert ids(real, registry) == ["pre-etb-en"]


def test_sealed_single_booster_pack_nao_e_barrado():
    # "single" sozinho é legítimo em selado (Sealed Single Booster Pack) — só
    # 'single card' (e afins) é single de verdade. Não pode disparar o guard.
    assert S.looks_like_single_card("Pokemon 151 - Sealed Single Booster Pack - English") is False


@pytest.mark.parametrize("title,expected", [
    ("Eevee SVP 173 Prismatic Evolutions Single Card", True),   # EN explícito
    ("Charizard SVP 044 Promo", True),                          # código SVP
    ("Pikachu 238/191 Surging Sparks", True),                   # numeração de carta
    ("Carta Avulsa Pikachu Prismatic", True),                   # PT
    ("Prismatic Evolutions Elite Trainer Box", False),          # selado
    ("Mega Evolution Booster Box", False),                      # selado
    ("Sealed Single Booster Pack 151", False),                  # 'single' ok em selado
])
def test_looks_like_single_card(title, expected):
    assert S.looks_like_single_card(title) is expected


# --- guard de acessório PURO: 'Acessórios' não casa box SKU -----------------
def test_acessorio_puro_nao_casa_box(registry):
    # Caso real (scan default 2026-06-06, ML): acessório vendido à parte casava
    # ah-etb-en (ETB real ~R$400) com R$95 → +885% fantasma.
    aces = "Elite Trainer Box - Ascended Heroes - Acessórios Inglês"
    assert S.match_listing(aces, registry) == []


def test_binder_collection_NAO_e_barrado(registry):
    # CRÍTICO: 'binder collection' é o type_term dos 4 Collection Box selados —
    # o guard de acessório NÃO pode barrá-lo (seria falso-negativo de SKU curado).
    # O "Fichário Binder +440%" do scan é bug de PREÇO do registry (mew-collection-box
    # US ref de produto caro vs type_term do binder barato), tratado fora do matcher.
    assert S.looks_like_accessory("Scarlet & Violet 151 Binder Collection") is False
    assert "mew-collection-box" in ids("Scarlet & Violet 151 Binder Collection English", registry)


def test_etb_real_nao_e_barrado_por_acessorio(registry):
    assert "ah-etb-en" in ids("Pokémon Ascended Heroes Elite Trainer Box Inglês", registry)


@pytest.mark.parametrize("title,expected", [
    ("Elite Trainer Box Acessórios", True),
    ("Porta Cartas Pokémon Toploader", True),
    ("Playmat Charizard", True),
    ("Sleeve Dragonite Etb Ascended Heroes (65 Sleeves)", True),  # pacote de sleeves = acessório
    ("Pacote 100 Sleeves Pokémon", True),
    ("Deck Protector Pikachu", True),
    ("Sleeved Booster Pack Surging Sparks", False),   # 'sleeve' é selado — NÃO barrar
    ("Booster Avulso Megaevolução", False),           # Sleeved Booster real (sem contador)
    ("Scarlet & Violet 151 Binder Collection", False),  # binder collection = selado real
    ("Prismatic Evolutions Collection Box", False),   # 'collection box' é selado
    ("Mega Evolution Booster Bundle", False),         # selado
])
def test_looks_like_accessory(title, expected):
    assert S.looks_like_accessory(title) is expected


def test_sleeve_pack_nao_casa_etb(registry):
    # Caso real (scan 2026-06-26, ML): "Sleeve Dragonite Etb Ascended Heroes
    # (65 Sleeves)" R$64,50 casava ah-etb-en e dava +1600% (margem_anomala). Pior:
    # virava a oferta de referência do grupo e escondia o ETB GREEN real da entrega.
    # O contador "65 Sleeves" é prova de pacote de protetores avulso = acessório.
    sleeve = "Sleeve Dragonite Etb Ascended Heroes (65 Sleeves)"
    assert S.looks_like_accessory(sleeve) is True
    assert S.match_listing(sleeve, registry) == []
