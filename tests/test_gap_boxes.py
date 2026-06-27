"""Gap 4ª leva — família BOXES (collection/premium/special/illustration/figure/
pin/poster). Títulos REAIS da Liga (scan 2026-06-27), refs tcgcsv reais. Cada
variante fixada por Pokémon/identificador; box exclui tin/deck/etb/booster."""
import pathlib
import yaml
import pytest
import sealed_arbitrage_scanner as S

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "sku_registry.yaml"


@pytest.fixture(scope="module")
def registry():
    return S.build_registry(yaml.safe_load(REGISTRY.read_text(encoding="utf-8")))


def ids(t, reg):
    return sorted(s.id for s in S.match_listing(t, reg))


@pytest.mark.parametrize("title,expected", [
    ("(ING) Collection Box - Zacian do Lupo Ex (English)", "zacian-hop-box"),
    ("(ING) Collection Box - Mega Latias Ex Box (English)", "mega-latias-box"),
    ("(ING) Collection Box - Dia de Pokémon 2026 (English)", "pokemon-day-2026-box"),
    ("(ING) Collection Box - Mega Kangaskhan ex (English)", "mega-kangaskhan-box"),
    ("(ING) Caixa - Escarlate e Violeta 10.5 - Fogo Branco e Raio Preto - Coleção Pôster (English)", "unova-poster-collection"),
    ("(ING) Collection Box - Mewtwo da Equipe Rocket Ex (English)", "team-rocket-mewtwo-box"),
    ("(ING) Collection Box Premium - Escarlate e Violeta - Bellibolt Ex da Kissera (English)", "iono-bellibolt-premium"),
    ("(ING) Collection Box Ilustração Parceiro Inicial - Serie 2 (English)", "first-partner-illustration-s2"),
    ("(ING) Collection Box Especial - Charizard Ex (English)", "charizard-special-box"),
    ("(ING) Collection Box - Mega Lucario ex Figure Collection (English)", "mega-lucario-figure"),
    ("(ING) Collection Box Premium - Escarlate e Violeta - Garchomp da Cíntia Ex (English)", "cynthia-garchomp-premium"),
    ("(ING) Collection Box Premium - Mega Venusaur ex (English)", "mega-venusaur-premium"),
    ("(ING) Collection Box Premium - Mega Zygarde ex (English)", "mega-zygarde-premium"),
    ("(ING) Caixa - Megaevolução - Ascended Heroes - First Partners Deluxe Pin Collection (English)", "ascended-heroes-pin-collection"),
    ("(ING) Coleção Ilustração - Escarlate e Violeta 10.5 - Fogo Branco e Raio Preto - Victini (English)", "unova-victini-illustration"),
    ("(ING) Collection Box Especial - Accessory Pouch Prismatic Evolutions (English)", "prismatic-accessory-pouch"),
    ("(ING) Collection Box Premium - Salamence ex e Reshiram ex (English)", "salamence-reshiram-premium"),
    ("(ING) Collection Box Ilustração Parceiro Inicial - Serie 1 (English)", "first-partner-illustration-s1"),
    ("(ING) Collection Box Premium - Hydreigon ex e Dragapult ex (English)", "hydreigon-dragapult-premium"),
])
def test_box_casa_pela_variante(title, expected, registry):
    assert ids(title, registry) == [expected]


_NEW = {"zacian-hop-box", "mega-latias-box", "pokemon-day-2026-box", "mega-kangaskhan-box",
        "unova-poster-collection", "team-rocket-mewtwo-box", "iono-bellibolt-premium",
        "first-partner-illustration-s2", "charizard-special-box", "mega-lucario-figure",
        "cynthia-garchomp-premium", "mega-venusaur-premium", "mega-zygarde-premium",
        "ascended-heroes-pin-collection", "unova-victini-illustration", "prismatic-accessory-pouch",
        "salamence-reshiram-premium", "first-partner-illustration-s1", "hydreigon-dragapult-premium"}


@pytest.mark.parametrize("title", [
    "(ING) Coleção Treinador Avançado - Escarlate e Violeta - Destinos de Paldea (English)",  # ETB
    "(ING) Caixa de Booster - Megaevolução 1 - Megaevolução (English)",  # booster box
    "(ING) Lata Mewtwo Ex da Equipe Rocket (English)",  # tin, não box
    "(ING) Battle Deck - Baralho Batalha de Liga - Mewtwo Ex da Equipe Rocket (English)",  # deck
    "(ING) Lata Mega Charizard X ex (English)",  # tin, não charizard-special-box
])
def test_box_nao_casa_ruido(title, registry):
    assert not [s for s in ids(title, registry) if s in _NEW]


def test_series_1_vs_2(registry):
    assert "first-partner-illustration-s1" not in ids(
        "(ING) Collection Box Ilustração Parceiro Inicial - Serie 2 (English)", registry)
