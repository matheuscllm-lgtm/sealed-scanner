"""Regressão do gap 2026-08-15 — a tradução PT→EN não pode destruir o match.

Bug real: `TYPE_TRANSLATE_PT_TO_EN` mapeava "Blister Unitário" → "Blister",
apagando o qualificador; o título traduzido sem "Checklane" não continha
NENHUM termo de tipo do SKU blister-1pack e caía em `sem_match_no_registry`
(JTG a R$23,95 com 1000+ unidades invisível em todos os scans). Os testes de
título cru (test_gap_loose_packs) não pegavam porque o matcher de produção
recebe o título JÁ TRADUZIDO — este arquivo cobre o roundtrip
`_translate_title` → `match_listing` para os formatos de blister unitário.

No mesmo episódio o operador re-apontou os 6 SKUs *-blister-1pack para o
"Sleeved Booster Pack" do tcgcsv (produto físico do "Blister Unitário" Copag;
a variante "Single Pack Blister [Pokémon]" tem promo e inflava a referência).
O teste de pids trava esse re-apontamento.
"""
import pathlib
import sys

import pytest
import yaml

import sealed_arbitrage_scanner as S

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from liga_adapter import _translate_title  # noqa: E402

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "sku_registry.yaml"


@pytest.fixture(scope="module")
def registry():
    return S.build_registry(yaml.safe_load(REGISTRY.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def raw_registry():
    return yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))


def ids(title, reg):
    return sorted(s.id for s in S.match_listing(title, reg))


# Título REAL da Liga (como o scraper vê) -> SKU esperado após tradução.
@pytest.mark.parametrize("titulo_liga,esperado", [
    # genérico (sem Pokémon) — o caso do bug: perdia "Unitário" e não casava nada
    ("(ING) Blister Unitário - Escarlate e Violeta 9 - Amigos de Jornada",
     "jtg-blister-1pack"),
    ("(ING) Blister Unitário - Escarlate e Violeta 10 - Rivais Predestinados",
     "dri-blister-1pack"),
    ("(ING) Blister Unitário - Megaevolução 2 - Fogo Fantasmagórico",
     "phf-blister-1pack"),
    ("(ING) Blister Unitário - Megaevolução 3 - Equilíbrio Perfeito",
     "po-blister-1pack"),
    ("(ING) Blister Unitário - Megaevolução 4 - Caos Ascendente",
     "cr-blister-1pack"),
    ("(ING) Blister Unitário - Megaevolução 5 - Escuridão Absoluta",
     "pb-blister-1pack"),
    # checklane com Pokémon continua caindo no genérico do set
    ("(ING) Blister Unitário Checklane - Megaevolução 4 - Caos Ascendente - Toxel",
     "cr-blister-1pack"),
    # premium checklane continua no SKU premium próprio, nunca no genérico
    ("(ING) Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Luxray",
     "pb-checklane-premium-luxray"),
])
def test_titulo_liga_traduzido_casa_sku(registry, titulo_liga, esperado):
    assert ids(_translate_title(titulo_liga), registry) == [esperado]


def test_blister_1pack_aponta_sleeved_booster_pack(raw_registry):
    """Operador 2026-08-15: referência do blister unitário = Sleeved Booster
    Pack (não a variante [Pokémon], mais cara). Trava os 6 pids."""
    esperados = {
        "jtg-blister-1pack": 610934,
        "dri-blister-1pack": 624684,
        "phf-blister-1pack": 654145,
        "po-blister-1pack": 672412,
        "cr-blister-1pack": 684448,
        "pb-blister-1pack": 692957,
    }
    skus = raw_registry if isinstance(raw_registry, list) else raw_registry.get("skus", raw_registry)
    got = {s["id"]: s.get("tcgplayer_product_id")
           for s in skus if isinstance(s, dict) and s.get("id") in esperados}
    assert got == esperados
