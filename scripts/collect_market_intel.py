#!/usr/bin/env python3
"""collect_market_intel.py — coleta CANDIDATOS a evento (feeds públicos).

Varre os feeds RSS/Atom configurados em `analysis.market_intel.feeds`
(PokéBeach/PokeGuardian/notícias oficiais — 1 GET por feed, best-effort) e
grava manchetes com gatilho de reprint/restock/nova onda que citem sets do
registry em `analysis.files.intel_candidates` (JSONL, gitignored).

Candidato NÃO é evento: a promoção passa por curadoria (operador, ou a sessão
Claude complementando com pesquisa dirigida) via scripts/import_events.py —
sempre com source_url + data. Notícia = no máx. SINAL_DE_MERCADO; fórum = RUMOR.
GTS/Southern Hobby/varejistas exigem conta/anti-bot → fase 2 (import manual).

Uso: python scripts/collect_market_intel.py [--game pokemon]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

import sealed_arbitrage_scanner as S
from lib.analysis import history_store as store
from lib.analysis import market_intel
from lib.analysis.profiles import analysis_config, resolve_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Coleta candidatos a evento (feeds públicos).")
    ap.add_argument("--game", default="pokemon", choices=sorted(S.GAME_PROFILES))
    args = ap.parse_args(argv)

    profile = S.GAME_PROFILES[args.game]
    config = S.load_yaml(ROOT / profile["config"], "config.yaml")
    acfg = analysis_config(config)
    feeds = (acfg.get("market_intel") or {}).get("feeds") or []
    if not feeds:
        print("  [intel] nenhum feed configurado em analysis.market_intel.feeds — nada a coletar.")
        return 0
    out_path = resolve_path(ROOT, (acfg.get("files") or {}).get(
        "intel_candidates", f"data/history/market_intel_{args.game}.jsonl"))

    registry = yaml.safe_load((ROOT / profile["registry"]).read_text(encoding="utf-8")) or {}
    set_names = {}
    for sku in registry.get("skus", []) or []:
        code, name = sku.get("set_code"), sku.get("set")
        if code and name:
            set_names.setdefault(code, name)

    candidates = market_intel.collect(feeds, set_names, store.utc_now_iso())
    existing, _bad = store.read_records(out_path)
    seen = {(r.get("source_url"), r.get("title")) for r in existing}
    fresh = [c for c in candidates if (c.get("source_url"), c.get("title")) not in seen]
    n = store.append_records(out_path, fresh)
    print(f"  [intel] {len(candidates)} candidato(s) · {n} novo(s) gravados em {out_path}")
    if fresh:
        print("  [intel] promova com scripts/import_events.py (curadoria — "
              "confira a URL antes; notícia = SINAL_DE_MERCADO no máximo).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
