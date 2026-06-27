"""Gap 4ª leva — família LATAS (tins/collector chest/mini tins). Títulos REAIS da
Liga (scan 2026-06-27). Refs tcgcsv reais (group 2374). Cada variante fixada por
série + Pokémon; X/Y e ano distinguidos; full tin exclui 'mini'."""
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
    ("(ING) Lata Slashing Legends - Zacian EX (English)", "slashing-legends-tin-zacian"),
    ("(ING) Lata Slashing Legends - Koraidon EX (English)", "slashing-legends-tin-koraidon"),
    ("(ING) Lata Moonlit - Mega Clefable (English)", "moonlit-tin-clefable"),
    ("(ING) Lata Moonlit - Mega Gengar (English)", "moonlit-tin-gengar"),
    ("(ING) Lata Mega Charizard Y ex (English)", "mega-charizard-tin-y"),
    ("(ING) Lata Mega Charizard X ex (English)", "mega-charizard-tin-x"),
    ("(ING) Lata Nidoking Ex da Equipe Rocket (English)", "team-rocket-tin-nidoking"),
    ("(ING) Lata Persian Ex da Equipe Rocket (English)", "team-rocket-tin-persian"),
    ("(ING) Lata Mewtwo Ex da Equipe Rocket (English)", "team-rocket-tin-mewtwo"),
    ("(ING) Lata Pokémon - Maleta de Colecionador - Outono 2025 (English)", "collector-chest-2025"),
    ("(ING) Lata Pokémon - Collector Chest - Outono 2024 (English)", "collector-chest-2024"),
    ("(ING) Mini Lata - Lumiose - Salamence (English)", "lumiose-mini-tin-salamence"),
    ("(ING) Mini Lata - Lumiose - Emboar (English)", "lumiose-mini-tin-emboar"),
    ("(ING) Mini Lata - Lumiose - Feraligatr (English)", "lumiose-mini-tin-feraligatr"),
    ("(ING) Mini Lata - Lumiose - Gallade (English)", "lumiose-mini-tin-gallade"),
    ("(ING) Mini Lata - Lumiose - Meganium (English)", "lumiose-mini-tin-meganium"),
])
def test_lata_casa_pela_variante(title, expected, registry):
    assert ids(title, registry) == [expected]


def test_charizard_x_nao_casa_y(registry):
    assert ids("(ING) Lata Mega Charizard X ex (English)", registry) == ["mega-charizard-tin-x"]
    assert "mega-charizard-tin-y" not in ids("(ING) Lata Mega Charizard X ex (English)", registry)


def test_chest_ano_distingue(registry):
    assert "collector-chest-2024" not in ids("(ING) Lata Pokémon - Maleta de Colecionador - Outono 2025 (English)", registry)


def test_full_tin_nao_e_mini(registry):
    # Slashing Legends é tin cheia; um "Mini Lata" não pode casar tin cheia
    assert not [s for s in ids("(ING) Mini Lata - Lumiose - Salamence (English)", registry) if "slashing" in s]
