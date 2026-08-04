"""Seleção de PERFIL DE JOGO (--game) nos runners e no snapshot.

Trava:
  - resolução defensiva do jogo (`resolve_game`): --game > config['game'] >
    'pokemon'; Namespace SEM o atributo (testes antigos/chamadas programáticas)
    continua funcionando;
  - roteamento de resultados por jogo: Pokémon segue em `results/` (histórico)
    e One Piece em `results/onepiece/` — o snapshot de um jogo NUNCA enxerga
    run do outro;
  - E2E mock do perfil OP no orquestrador: classifica de ponta a ponta com o
    registry/config/referência OP e grava `run_meta.json` com game=onepiece;
  - perfis do snapshot (raiz/registry/tag/arquivo por jogo).
"""
import argparse
import csv
import json
import os
import pathlib
import sys

import yaml

import sealed_arbitrage_scanner as S
import run_all_sources as ORQ

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import snapshot  # noqa: E402


# ── resolve_game ────────────────────────────────────────────────────────────
def test_resolve_game_precedence_and_defensiveness():
    ns = argparse.Namespace(game="onepiece")
    assert S.resolve_game(ns, {"game": "pokemon"}) == "onepiece"   # flag vence
    ns_old = argparse.Namespace()                                   # sem atributo
    assert S.resolve_game(ns_old, {"game": "onepiece"}) == "onepiece"
    assert S.resolve_game(ns_old, {}) == "pokemon"
    assert S.resolve_game(ns_old, None) == "pokemon"
    assert S.resolve_game(argparse.Namespace(game="jogo_invalido"), {}) == "pokemon"


def test_results_root_per_game(tmp_path):
    assert S.results_root_for("pokemon", tmp_path) == tmp_path / "results"
    assert S.results_root_for("onepiece", tmp_path) == tmp_path / "results" / "onepiece"


def test_game_profiles_point_to_real_files():
    for game, prof in S.GAME_PROFILES.items():
        assert (ROOT / prof["config"]).exists(), (game, prof["config"])
        assert (ROOT / prof["registry"]).exists(), (game, prof["registry"])


# ── E2E mock do perfil One Piece no orquestrador ────────────────────────────
def test_orchestrator_onepiece_mock_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setattr(S, "resolve_fx_rate", lambda cfg: "manual (test)")
    monkeypatch.setattr(ORQ, "SCRIPT_DIR", tmp_path)
    (tmp_path / "data").mkdir()
    today = S.datetime.now(S.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # Referência OP PINADA (não depende do preço vivo commitado).
    (tmp_path / "data" / "us_reference_onepiece.json").write_text(
        json.dumps({"captured_at": today,
                    "prices": {"op16-booster-box-en": 200.0}}), encoding="utf-8")
    listings = [
        {"id": "OP-GOOD", "title": "The Time of Battle Booster Box (English) OP-16",
         "price_brl": 500.0, "seller": "v", "url": "u"},
        {"id": "OP-CASE", "title": "The Time of Battle Booster Box Case",
         "price_brl": 4000.0, "seller": "v", "url": "u"},
    ]
    mock = tmp_path / "op_listings.json"
    mock.write_text(json.dumps({"listings": listings}), encoding="utf-8")
    args = argparse.Namespace(
        game="onepiece", sources="mock", mock=str(mock),
        config=str(ROOT / "config_onepiece.yaml"),
        registry=str(ROOT / "sku_registry_onepiece.yaml"),
    )
    assert ORQ.run(args) == 0
    # Saída na raiz DO JOGO — e nada em results/unified_* (raiz Pokémon).
    op_dirs = sorted((tmp_path / "results" / "onepiece").glob("unified_*/"))
    assert op_dirs, "run OP não gravou em results/onepiece/"
    assert not list((tmp_path / "results").glob("unified_*"))
    rows = list(csv.DictReader((op_dirs[-1] / "unified_deals.csv").open(encoding="utf-8")))
    verdict = {r["ID Anúncio"]: r["Confiança do deal"] for r in rows}
    assert verdict["OP-GOOD"] == "GREEN"      # 200*5.05/500 → ~102% na banda
    assert verdict["OP-CASE"] == "RED"        # case = lote, nunca casa SKU
    meta = json.loads((op_dirs[-1] / "run_meta.json").read_text(encoding="utf-8"))
    assert meta["game"] == "onepiece"
    assert "One Piece" in meta["route_label"]


def test_orchestrator_default_sources_come_from_profile_config(tmp_path, monkeypatch):
    # --sources ausente → default_sources do config do perfil (OP = [liga]).
    monkeypatch.setattr(S, "resolve_fx_rate", lambda cfg: "manual (test)")
    monkeypatch.setattr(ORQ, "SCRIPT_DIR", tmp_path)
    (tmp_path / "data").mkdir()
    today = S.datetime.now(S.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    (tmp_path / "data" / "us_reference_onepiece.json").write_text(
        json.dumps({"captured_at": today, "prices": {}}), encoding="utf-8")

    seen: dict = {}
    real_load = S.load_listings

    def spy_load(source, mock_path, config, registry_raw=None):
        seen.setdefault("sources", []).append(source)
        if source == "liga":
            return [], "liga (spy)"
        return real_load(source, mock_path, config, registry_raw=registry_raw)

    monkeypatch.setattr(S, "load_listings", spy_load)
    args = argparse.Namespace(
        game="onepiece", sources=None, mock=str(tmp_path / "nao_usado.json"),
        config=str(ROOT / "config_onepiece.yaml"),
        registry=str(ROOT / "sku_registry_onepiece.yaml"),
    )
    rc = ORQ.run(args)
    assert seen["sources"] == ["liga"]        # perfil OP roda SÓ liga por default
    assert rc == 1                            # fonte vazia = falha honesta


# ── perfis do snapshot ──────────────────────────────────────────────────────
def test_snapshot_game_profiles_and_roots():
    assert snapshot.results_root_for("pokemon") == snapshot.RESULTS
    assert snapshot.results_root_for("onepiece") == snapshot.RESULTS / "onepiece"
    prof = snapshot.GAME_PROFILES["onepiece"]
    assert prof["tag"] == "onepiece"
    assert prof["file_infix"] == "onepiece-"
    assert (pathlib.Path(snapshot.ROOT) / prof["registry"]).exists()


def test_snapshot_registry_loader_reads_op_registry():
    ids = snapshot.load_tcg_product_ids(ROOT / "sku_registry_onepiece.yaml")
    assert ids.get("op16-booster-box-en") == 689336   # productId REAL (tcgcsv)


# ── resolve_cli_game: --game None deixa o game: do --config valer (review PR #75) ──

def test_resolve_cli_game_config_game_key_wins_without_flag():
    # `--config config_onepiece.yaml` SEM --game tem que resolver onepiece —
    # antes o default "pokemon" do argparse tornava o game: do config letra
    # morta e misturava registry Pokémon com config OP (contaminação cross-game).
    args = argparse.Namespace(game=None, config=str(ROOT / "config_onepiece.yaml"))
    assert S.resolve_cli_game(args) == "onepiece"


def test_resolve_cli_game_defaults_pokemon():
    args = argparse.Namespace(game=None, config=None)
    assert S.resolve_cli_game(args) == "pokemon"


def test_resolve_cli_game_explicit_flag_conflicting_config_fails():
    # --game pokemon + config OP = mistura de perfis; falha alto, nunca roda misto.
    args = argparse.Namespace(game="pokemon", config=str(ROOT / "config_onepiece.yaml"))
    try:
        S.resolve_cli_game(args)
        assert False, "conflito --game x game: do config tinha que falhar"
    except SystemExit:
        pass
