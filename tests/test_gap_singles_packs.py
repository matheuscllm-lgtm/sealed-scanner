"""Gap singles packs (boosters avulsos) — 2026-07-02: set-base SVI + Trick or
Trade 2023/2024 (antes fora pelo piso R$50, extinto para selados).
Títulos REAIS dos scans de 06-27/06-30/07-02; refs tcgcsv reais.

Armadilha travada aqui: "escarlate e violeta 1" NÃO pode casar os sub-sets
"Escarlate e Violeta 9/10/..." (o matcher casa por palavra inteira)."""
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
    ("(ING) Booster Pack - Escarlate e Violeta 1 - Escarlate e Violeta (English)", "svi-pack-en"),
    ("(ING) Booster Pack - Trick or Trade 2023 (English)", "tot-2023-pack"),
    ("(ING) Booster Pack - Trick or Trade 2024 (English)", "tot-2024-pack"),
])
def test_singles_pack_casa_exato(title, expected, registry):
    assert ids(title, registry) == [expected]


@pytest.mark.parametrize("title", [
    # sub-sets SV (títulos reais) NÃO podem cair no set-base SVI
    "(ING) Booster Avulso - Escarlate e Violeta 9 - Amigos de Jornada (English)",
    "(ING) Booster Avulso - Escarlate e Violeta 10 - Fagulhas Impetuosas (English)",
    "(ING) Booster Avulso - Escarlate e Violeta 10 - Rivais Predestinados (English)",
])
def test_subset_sv_nao_casa_set_base(title, registry):
    matched = ids(title, registry)
    assert "svi-pack-en" not in matched
    assert matched, f"sub-set deveria seguir casando o próprio SKU: {title}"


@pytest.mark.parametrize("title,wrong", [
    # anos não podem cruzar
    ("(ING) Booster Pack - Trick or Trade 2023 (English)", "tot-2024-pack"),
    ("(ING) Booster Pack - Trick or Trade 2024 (English)", "tot-2023-pack"),
])
def test_tot_ano_nao_cruza(title, wrong, registry):
    assert wrong not in ids(title, registry)


@pytest.mark.parametrize("title", [
    # bundle/lote de ToT não é o mini pack avulso
    "(ING) Trick or Trade BOOster Bundle 2024 (35 mini packs) (English)",
    "(ING) Trick or Trade BOOster Bundle 2023 (50 ct) (English)",
    # PT-BR/Copag fora (scanner é EN-only)
    "Booster Pack - Trick or Trade 2024 (Português)",
    "(COPAG) Booster Pack - Escarlate e Violeta 1 - Escarlate e Violeta (Português)",
])
def test_ruido_nao_casa_pack(title, registry):
    for sku_id in ("svi-pack-en", "tot-2023-pack", "tot-2024-pack"):
        assert sku_id not in ids(title, registry)
