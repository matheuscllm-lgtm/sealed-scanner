"""Gap 4ª leva — prerelease (Build & Battle Box / Desafio Estratégico, categ 57)
+ 2 stragglers (Vileplume 2-pack, Back to School Bellibolt). Títulos REAIS da
Liga; refs tcgcsv reais. Prerelease distinguido por tipo 'desafio estratégico'."""
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
    ("(ING) Desafio Estratégico - Escarlate e Violeta 9 - Amigos de Jornada (Kit de Pré Lançamento) (English)", "journey-together-build-battle"),
    ("(ING) Desafio Estratégico - Megaevolução 1 - Megaevolução (Kit Pré-Lançamento) (English)", "mega-evolution-build-battle"),
    ("(ING) Desafio Estratégico - Megaevolução 2 - Fogo Fantasmagórico (Kit Pré-Lançamento) (English)", "phantasmal-flames-build-battle"),
    ("(ING) Desafio Estratégico - Megaevolução 3 - Equilíbrio Perfeito (Kit Pré-Lançamento) (English)", "perfect-order-build-battle"),
    ("(ING) Desafio Estratégico - Megaevolução 4 - Caos Ascendente (Kit Pré-Lançamento) (English)", "chaos-rising-build-battle"),
    ("(ING) Desafio Estratégico - Escarlate e Violeta 10 - Rivais Predestinados (Kit Pré-Lançamento) (English)", "destined-rivals-build-battle"),
    ("(ING) Desafio Estratégico - Megaevolução 5 - Escuridão Absoluta (Kit Pré-Lançamento) (English)", "pitch-black-build-battle"),
    ("(ING) Desafio Estratégico - Espada e Escudo 8 - Golpe Fusão (Build & Battle Box) (English)", "fusion-strike-build-battle"),
    ("(ING) Desafio Estratégico - XY - Cerco ao Vapor (Kit de Pré Lançamento) (English)", "steam-siege-prerelease-kit"),
    ("(ING) Blister Duplo Enhanced - Vileplume (English)", "vileplume-2pack-blister"),
    ("(ING) Blister Duplo - Back to School 2024 - Bellibolt (English)", "back-to-school-blister-bellibolt"),
])
def test_prerelease_e_stragglers_casa(title, expected, registry):
    assert ids(title, registry) == [expected]


_NEW = {"journey-together-build-battle", "mega-evolution-build-battle", "phantasmal-flames-build-battle",
        "perfect-order-build-battle", "chaos-rising-build-battle", "destined-rivals-build-battle",
        "pitch-black-build-battle", "fusion-strike-build-battle", "steam-siege-prerelease-kit",
        "vileplume-2pack-blister", "back-to-school-blister-bellibolt"}


@pytest.mark.parametrize("title", [
    # ETB/booster do mesmo set NÃO casa o prerelease:
    "(ING) Coleção Treinador Avançado - Megaevolução 2 - Fogo Fantasmagórico (English)",
    "(ING) Caixa de Booster - Megaevolução 4 - Caos Ascendente (English)",
    # Iono Bellibolt Premium não casa o back-to-school:
    "(ING) Collection Box Premium - Escarlate e Violeta - Bellibolt Ex da Kissera (English)",
])
def test_prerelease_nao_casa_ruido(title, registry):
    assert not [s for s in ids(title, registry) if s in _NEW]
