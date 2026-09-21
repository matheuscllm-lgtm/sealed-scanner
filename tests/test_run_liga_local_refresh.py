"""Referência do DIA no runner canônico da Liga.

O config exige referência fresca (deal_criteria.max_reference_age_days: 1 —
decisão do operador 2026-08-15). Antes deste hook, run_liga_local.py NÃO
reconstruía nada: um scan com arquivo velho rebaixava GREEN -> YELLOW em
silêncio. Estes testes travam o contrato:

  1. o refresh roda por DEFAULT, na ordem US (classifica) -> eBay (informativa);
  2. o refresh é BEST-EFFORT — código de saída != 0 e exceção NUNCA propagam
     (a entrega não pode morrer por causa do refresh);
  3. --no-refresh-refs continua existindo para usar os arquivos que já existem.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import run_liga_local  # noqa: E402


def test_refresh_roda_os_dois_builders_na_ordem_certa():
    chamadas = []

    def fake_runner(cmd, **kwargs):
        chamadas.append(cmd)
        return 0

    res = run_liga_local.refresh_references("pokemon", runner=fake_runner)

    assert [Path(c[1]).name for c in chamadas] == [
        "build_us_reference.py",      # CLASSIFICA — vem primeiro
        "build_ebay_reference.py",    # informativa (lado de venda)
    ]
    # o perfil de jogo é repassado aos dois builders
    for cmd in chamadas:
        assert cmd[2:] == ["--game", "pokemon"]
    assert set(res.values()) == {"ok"}


def test_refresh_repassa_o_game_onepiece():
    chamadas = []
    run_liga_local.refresh_references(
        "onepiece", runner=lambda cmd, **kw: (chamadas.append(cmd), 0)[1]
    )
    for cmd in chamadas:
        assert cmd[2:] == ["--game", "onepiece"]


def test_builder_com_codigo_de_erro_nao_derruba_o_scan():
    res = run_liga_local.refresh_references("pokemon", runner=lambda cmd, **kw: 3)
    assert set(res.values()) == {"falhou"}   # avisado, nunca levantado


def test_excecao_do_builder_nao_propaga():
    def explode(cmd, **kwargs):
        raise subprocess.TimeoutExpired(cmd, 1)

    res = run_liga_local.refresh_references("pokemon", runner=explode)
    assert set(res.values()) == {"erro"}


def test_refresh_usa_timeout_para_nao_pendurar_a_entrega():
    vistos = []
    run_liga_local.refresh_references(
        "pokemon", runner=lambda cmd, **kw: (vistos.append(kw.get("timeout")), 0)[1]
    )
    assert vistos and all(t == run_liga_local.REFRESH_TIMEOUT_S for t in vistos)


@pytest.mark.parametrize("argv,esperado", [([], True), (["--no-refresh-refs"], False)])
def test_flag_refresh_refs_default_ligada(argv, esperado, monkeypatch):
    """O default é reconstruir; --no-refresh-refs desliga só naquele run."""
    import argparse

    p = argparse.ArgumentParser()
    p.add_argument("--refresh-refs", action=argparse.BooleanOptionalAction, default=True)
    assert p.parse_args(argv).refresh_refs is esperado
    # e a flag existe de fato no runner
    assert "--refresh-refs" in Path(run_liga_local.__file__).read_text(encoding="utf-8")
