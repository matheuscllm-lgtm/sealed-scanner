"""Gap do back-catalog One Piece (review do scan de 2026-08-28).

O scan Liga OP de 2026-08-28 terminou com 56 anúncios EN sem match em 13
produtos únicos — todos dentro do escopo BUSCAR do operador: packs de sets
antigos (OP-02..OP-08), Double Pack Sets Vol.1–5 e a família Premium Card
Collection (Liga: "Kit Colecionável - Premium Card Collection - ...").
A ampliação (SEED_GROUPS op01..op08+eb01 + família PCC no gerador) precisa
manter cada um desses TÍTULOS REAIS da Liga casando exatamente 1 SKU.
"""
import pathlib

import pytest
import yaml

import sealed_arbitrage_scanner as S

ROOT = pathlib.Path(__file__).resolve().parents[1]

# (título REAL coletado na Liga em 2026-08-28, sku_id esperado)
REAL_TITLES = [
    ("(ING) Booster Pack - OP-02 - Paramount War (English)", "op02-booster-pack-en"),
    ("(ING) Booster Pack - OP-03 - Pillars of Strength (English)", "op03-booster-pack-en"),
    ("(ING) Booster Pack - OP-06 - Wings of the Captain (English)", "op06-booster-pack-en"),
    ("(ING) Booster Pack - OP-07 - 500 Years in the Future (English)", "op07-booster-pack-en"),
    ("(ING) Booster Pack - OP-08 - Two Legends (English)", "op08-booster-pack-en"),
    ("(ING) Caixa Colecionável - Double Pack Set Vol.1 - DP-01 - Kingdoms of Intrigue (English)",
     "op04-double-pack-en"),
    ("(ING) Caixa Colecionável - Double Pack Set Vol.3 - DP-03 - Wings of the Captain (English)",
     "op06-double-pack-en"),
    ("(ING) Caixa Colecionável - Double Pack Set Vol.4 - DP-04 - 500 Years in the Future (English)",
     "op07-double-pack-en"),
    ("(ING) Caixa Colecionável - Double Pack Set Vol.5 - DP-05 - Two Legends (English)",
     "op08-double-pack-en"),
    ("(ING) Kit Colecionável - Premium Card Collection - Best Selection vol.3 (English)",
     "pcc-best-selection-vol-3-en"),
    ("(ING) Kit Colecionável - Premium Card Collection - Best Selection vol.5 (English)",
     "pcc-best-selection-vol-5-en"),
    ("(ING) Kit Colecionável - Premium Card Collection - Best Selection vol.6 (English)",
     "pcc-best-selection-vol-6-en"),
    ("(ING) Kit Colecionável - Premium Card Collection - Live Action Edition (English)",
     "pcc-live-action-edition-en"),
]


@pytest.fixture(scope="module")
def op_registry():
    data = yaml.safe_load(
        (ROOT / "sku_registry_onepiece.yaml").read_text(encoding="utf-8"))
    return S.build_registry(data)


@pytest.mark.parametrize("title,expected", REAL_TITLES,
                         ids=[sku for _, sku in REAL_TITLES])
def test_titulo_real_da_liga_casa_um_unico_sku(op_registry, title, expected):
    got = [c.id for c in S.match_listing(title, op_registry)]
    assert got == [expected], f"{title!r} -> {got}"


def test_wave_sem_declarar_nao_casa_nenhum_dos_dois_waves(op_registry):
    # Romance Dawn tem Booster Box Wave 1 (Blue) e Wave 2 (White) — produtos
    # distintos com preços muito diferentes. Anúncio que NÃO declara o wave
    # não pode casar nenhum dos dois (nunca chutamos qual wave o vendedor tem).
    got = [c.id for c in S.match_listing(
        "(ING) Caixa de Booster - OP-01 - Romance Dawn (English)", op_registry)]
    assert not any(g.startswith("op01-booster-box") for g in got), got
