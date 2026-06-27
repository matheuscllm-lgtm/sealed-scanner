"""Gap 4ª leva — 2 boosters SWSH antigos (Astral Radiance, Silver Tempest) +
2 blisters 3-pack (Phantasmal Flames Sneasel, Destined Rivals Zebstrika).
Títulos REAIS da Liga; refs tcgcsv reais; variante por Pokémon/set."""
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
    ("(ING) Booster Pack - Espada e Escudo 10 - Estrelas Radiantes (English)", "astral-radiance-pack"),
    ("(ING) Booster Pack - Espada e Escudo 12 - Tempestade Prateada (English)", "silver-tempest-pack"),
    ("(ING) Blister Megaevolução 2 - Phantasmal Flames - Sneasel (English)", "phf-blister-3pack-sneasel"),
    ("(ING) Blister Escarlate e Violeta 10 - Destined Rivals - Zebstrika (English)", "dri-blister-3pack-zebstrika"),
])
def test_booster_blister_casa(title, expected, registry):
    assert ids(title, registry) == [expected]


@pytest.mark.parametrize("title,wrong", [
    # blister do MESMO set, Pokémon diferente, não pode casar o novo
    ("(ING) Blister Megaevolução 2 - Phantasmal Flames - Weavile (English)", "phf-blister-3pack-sneasel"),
    ("(ING) Blister Escarlate e Violeta 10 - Destined Rivals - Kangaskhan (English)", "dri-blister-3pack-zebstrika"),
])
def test_blister_variante_vizinha_nao_casa(title, wrong, registry):
    assert wrong not in ids(title, registry)
