#!/usr/bin/env python3
"""import_trends.py — importa CSV do Google Trends (export MANUAL da UI).

Decisão de fase 1: Google Trends entra SÓ por CSV exportado manualmente
(a API não-oficial é frágil e fora dos termos — sem pytrends). O dado é
INFORMATIVO (evidência de interesse de busca); não entra em fórmula nenhuma.

Uso:
    python scripts/import_trends.py trends.csv --sku ssp-etb-en \
        --term "surging sparks etb" [--game pokemon]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sealed_arbitrage_scanner as S
from lib.analysis import history_store as store
from lib.analysis.importers import parse_trends_csv
from lib.analysis.profiles import analysis_config, resolve_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Importa CSV do Google Trends (manual).")
    ap.add_argument("csv")
    ap.add_argument("--sku", required=True)
    ap.add_argument("--term", required=True, help="termo pesquisado no Trends")
    ap.add_argument("--game", default="pokemon", choices=sorted(S.GAME_PROFILES))
    args = ap.parse_args(argv)

    config = S.load_yaml(ROOT / S.GAME_PROFILES[args.game]["config"], "config.yaml")
    acfg = analysis_config(config)
    out_path = resolve_path(ROOT, (acfg.get("files") or {}).get(
        "trends_imports", "data/history/trends_pokemon.jsonl"))
    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERRO: {csv_path} não existe.")
        return 2
    records, stats = parse_trends_csv(csv_path, args.sku, args.term,
                                      collected_at=date.today().isoformat())
    n = store.append_records(out_path, records)
    print(f"  [trends] {stats.summary()} → {n} registro(s) em {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
