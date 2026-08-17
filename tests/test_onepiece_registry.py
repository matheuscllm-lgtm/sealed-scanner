"""Registry One Piece (`sku_registry_onepiece.yaml`) — integridade + matcher.

Travas:
  - integridade estrutural (ids únicos, product/group id reais em todos, EN,
    game/categoria declarados, todo tipo com sanity band OP);
  - **autoconsistência total do seed**: o NOME REAL (tcgcsv) de cada um dos
    SKUs casa EXATAMENTE o próprio SKU no matcher (nem 0, nem 2+) — é o
    equivalente OP do precision==recall==1.0 do matcher Pokémon;
  - casos dirigidos: Box ≠ Case, Pack ≠ Sleeved, Deck ≠ Display, Double Pack
    por volume, PRB-01 ≠ PRB-02 (colisão de prefixo corrigida no gerador);
  - **anti-contaminação cross-game nos DOIS sentidos** (registries separados
    por jogo é a defesa estrutural; aqui provamos que também não há vazamento
    semântico de termos).
"""
import pathlib

import pytest
import yaml

import sealed_arbitrage_scanner as S
import build_us_reference as B

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def op_raw():
    return yaml.safe_load((ROOT / "sku_registry_onepiece.yaml").read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def op_registry(op_raw):
    return S.build_registry(op_raw)


@pytest.fixture(scope="module")
def pkm_registry():
    data = yaml.safe_load((ROOT / "sku_registry.yaml").read_text(encoding="utf-8"))
    return S.build_registry(data)


# ── integridade ─────────────────────────────────────────────────────────────
def test_registry_declares_game_and_category(op_raw):
    assert op_raw["game"] == "onepiece"
    assert op_raw["tcgcsv_category_id"] == 68


def test_unique_ids_and_real_tcg_ids(op_raw):
    skus = op_raw["skus"]
    ids = [s["id"] for s in skus]
    assert len(ids) == len(set(ids))
    for s in skus:
        assert s.get("tcgplayer_group_id"), s["id"]
        assert s.get("tcgplayer_product_id"), s["id"]
        assert s.get("language") == "EN", s["id"]


def test_every_product_type_has_op_sanity_band(op_raw):
    types = {s["product_type"] for s in op_raw["skus"]}
    missing = types - set(B.SANITY_BANDS_USD_ONEPIECE)
    assert not missing, f"tipos sem banda OP (fail-open indevido): {missing}"


def test_no_pt_set_aliases_in_seed(op_raw):
    # Bandai não localiza nome de set: alias PT de SET só entra com título real
    # da Liga OP (runbook §B). O seed não pode conter chute (lição ASI-Evolve).
    pt_markers = ("ç", "ã", "õ", "á", "é", "í", "ó", "ú", "â", "ê")
    for s in op_raw["skus"]:
        for term in s["match"]["set_terms"]:
            assert not any(m in term for m in pt_markers), (s["id"], term)


# ── autoconsistência total do seed ──────────────────────────────────────────
def test_every_real_name_matches_exactly_its_own_sku(op_registry):
    fails = []
    for sku in op_registry:
        got = [c.id for c in S.match_listing(sku.name, op_registry)]
        if got != [sku.id]:
            fails.append((sku.id, sku.name, got))
    assert not fails, fails


# ── casos dirigidos (nomes REAIS do tcgcsv) ─────────────────────────────────
def _ids(title, registry):
    return [c.id for c in S.match_listing(title, registry)]


def test_box_vs_case_disambiguation(op_registry):
    # Operador 2026-08-17: case virou SKU de 1ª classe — o título de case tem
    # que casar EXATAMENTE o SKU de case (nunca o box, e vice-versa).
    assert _ids("The Time of Battle Booster Box Case", op_registry) == ["op16-booster-box-case-en"]
    assert _ids("The Time of Battle Booster Box", op_registry) == ["op16-booster-box-en"]
    # EB nomeia o case sem "Booster": "… Box Case".
    assert _ids("Extra Booster: Anime 25th Collection Box Case", op_registry) == ["eb02-booster-box-case-en"]


def test_new_families_match_their_own_sku(op_registry):
    # Famílias do escopo BUSCAR (operador 2026-08-17) — nomes REAIS do tcgcsv.
    assert _ids("One Piece Card Game Illustration Box Vol. 5", op_registry) == ["ilbox-vol5-en"]
    assert _ids("One Piece Card Game Illustration Box Vol. 5 Case", op_registry) == ["ilbox-vol5-case-en"]
    assert _ids("One Piece Card Game Illustration Box EX", op_registry) == ["ilbox-ex-en"]
    assert _ids("Devil Fruits Collection Vol. 2", op_registry) == ["dfc-vol2-en"]
    assert _ids("One Piece Tin Pack Set Vol. 2 -Sabo-", op_registry) == ["tinpack-vol2-sabo-en"]
    assert _ids("One Piece Tin Pack Set Vol. 2 Display", op_registry) == ["tinpack-vol2-display-en"]
    assert _ids("One Piece Tin Pack Set Vol. 2 Display Case", op_registry) == ["tinpack-vol2-display-case-en"]
    assert _ids("Treasure Booster Set", op_registry) == ["treasure-booster-en"]
    assert _ids("Gift Collection 2023", op_registry) == ["gift2023-en"]
    assert _ids("Gift Collection 2023 Display", op_registry) == ["gift2023-display-en"]
    # Promotion Pack NÃO é o unit (exclude 'promotion' defensivo).
    assert _ids("Gift Collection 2023 Promotion Pack", op_registry) == []


def test_pack_vs_sleeved_disambiguation(op_registry):
    assert _ids("The Time of Battle Booster Pack", op_registry) == ["op16-booster-pack-en"]
    assert _ids("The Time of Battle Sleeved Booster Pack", op_registry) == ["op16-sleeved-booster-en"]


def test_starter_deck_vs_display(op_registry):
    assert _ids("Starter Deck 31: RED Monkey.D.Luffy", op_registry) == ["st31-starter-deck-en"]
    assert _ids("Starter Deck 31: RED Monkey.D.Luffy Display", op_registry) == ["st31-starter-deck-display-en"]


def test_double_pack_identity_is_volume_number(op_registry):
    assert _ids("Double Pack Set Vol. 11", op_registry) == ["op16-double-pack-en"]
    assert _ids("Double Pack Set Vol. 11 Display", op_registry) == ["op16-double-pack-display-en"]
    assert _ids("Double Pack Set Vol. 12", op_registry) == ["op17-double-pack-en"]


def test_prb01_does_not_swallow_prb02(op_registry):
    # 'premium booster' é prefixo de 'premium booster vol 2' — colisão real
    # achada no check de autoconsistência e corrigida com exclude no PRB-01.
    assert _ids("Premium Booster Vol. 2 - Booster Box", op_registry) == ["prb02-booster-box-en"]
    assert _ids("Premium Booster - Booster Box", op_registry) == ["prb01-booster-box-en"]


def test_inserts_and_lots_never_match(op_registry):
    assert _ids("Special DON!! Card Pack DP-11", op_registry) == []
    assert _ids("Adventure on Kami's Island - Dash Pack", op_registry) == []
    assert _ids("Starter Decks 23-28 [Set of 6]", op_registry) == []


def test_non_english_rejected(op_registry):
    assert _ids("The Time of Battle Booster Box Japanese", op_registry) == []


# ── anti-contaminação cross-game (2 sentidos) ───────────────────────────────
POKEMON_TITLES = [
    "Surging Sparks Booster Box (English)",
    "Prismatic Evolutions Elite Trainer Box",
    "Pokémon 151 Booster Bundle",
    "Stellar Crown Booster Box (English)",
    "Mega Evolution Booster Bundle",
]
ONEPIECE_TITLES = [
    "The Time of Battle Booster Box",
    "Royal Blood Booster Pack",
    "Double Pack Set Vol. 11",
    "Starter Deck 31: RED Monkey.D.Luffy",
    "Extra Booster: One Piece Heroines Edition Box",
]


def test_pokemon_titles_never_match_op_registry(op_registry):
    for title in POKEMON_TITLES:
        assert _ids(title, op_registry) == [], title


def test_onepiece_titles_never_match_pokemon_registry(pkm_registry):
    for title in ONEPIECE_TITLES:
        assert _ids(title, pkm_registry) == [], title
