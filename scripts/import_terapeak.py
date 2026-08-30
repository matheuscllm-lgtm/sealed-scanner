#!/usr/bin/env python3
"""import_terapeak.py — importa uma captura Terapeak (sold) pro store da análise.

Fluxo (validado pelo operador em 2026-08-29 — a UI do Product Research não tem
export nem coluna de seller):
  1. `scripts/terapeak_scrape.js` no console da aba Sold → CSV em
     `data/terapeak/<sku>_<data>.csv` (gitignored);
  2. este script: casa cada título a EXATAMENTE um SKU do registry (gate do
     build_ebay_reference — ambíguo é descartado e contado), busca o
     `seller.username` de cada item via Browse API getItem (mesmo token do
     lib/ebay_client; CACHE em data/cache/ebay_sellers.json poupa as 5k
     chamadas/dia), marca `is_probstein` (probstein123) e grava ADITIVO no
     JSONL de sold (`analysis.files.sold_imports`) sem duplicar
     (item_id, lookback, arquivo).

Ressalva honesta: anúncio encerrado há >~90 dias some da API → seller=null
(nunca inventado). Por isso a captura vale MENSALMENTE.

Uso:
    python scripts/import_terapeak.py data/terapeak/ssp-etb_2026-08-29.csv \
        --lookback-days 30 [--sku ssp-etb-en] [--game pokemon] [--no-sellers]
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_ebay_reference as B
import sealed_arbitrage_scanner as S
from lib.analysis import history_store as store
from lib.analysis.importers import enrich_sellers, parse_terapeak_csv
from lib.analysis.profiles import analysis_config, resolve_path
from lib.ebay_client import EbayClient
from lib.env import load_dotenv_if_present

SELLER_CACHE = ROOT / "data" / "cache" / "ebay_sellers.json"


def _load_cache() -> dict:
    if SELLER_CACHE.exists():
        try:
            return json.loads(SELLER_CACHE.read_text(encoding="utf-8"))
        except ValueError:
            return {}
    return {}


def _save_cache(cache: dict) -> None:
    SELLER_CACHE.parent.mkdir(parents=True, exist_ok=True)
    SELLER_CACHE.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Importa captura Terapeak (sold).")
    ap.add_argument("csv", help="CSV gerado por scripts/terapeak_scrape.js")
    ap.add_argument("--lookback-days", type=int, required=True,
                    help="período usado na UI do Terapeak (30/90/…)")
    ap.add_argument("--sku", default=None,
                    help="força TODOS os itens neste SKU (export de produto único)")
    ap.add_argument("--game", default="pokemon", choices=sorted(S.GAME_PROFILES))
    ap.add_argument("--no-sellers", action="store_true",
                    help="pula o lookup de seller via getItem (sem chaves eBay)")
    args = ap.parse_args(argv)

    profile = S.GAME_PROFILES[args.game]
    config = S.load_yaml(ROOT / profile["config"], "config.yaml")
    acfg = analysis_config(config)
    out_path = resolve_path(ROOT, (acfg.get("files") or {}).get(
        "sold_imports", "data/history/ebay_sold_pokemon.jsonl"))

    registry_data = S.load_yaml(ROOT / profile["registry"], "registry")
    skus = S.build_registry(registry_data)

    csv_path = Path(args.csv)
    if not csv_path.exists():
        print(f"ERRO: {csv_path} não existe.")
        return 2

    existing, bad = store.read_records(out_path)
    existing_keys = {(r.get("item_id"), r.get("lookback_days"), r.get("source_file"))
                     for r in existing}
    records, stats = parse_terapeak_csv(
        csv_path, skus, B.title_passes_gate, args.lookback_days,
        collected_at=date.today().isoformat(), sku_hint=args.sku,
        existing_keys=existing_keys)
    for d in stats.details[:10]:
        print(f"  [terapeak] {d}")

    if records and not args.no_sellers:
        load_dotenv_if_present()
        client = EbayClient()
        if client.configured:
            cache = _load_cache()
            counts = enrich_sellers(records, client.get_item, cache)
            _save_cache(cache)
            print(f"  [terapeak] sellers: {counts['fetched']} buscados · "
                  f"{counts['cached']} do cache · {counts['gone']} encerrados "
                  f">90d (sem seller) · {counts['errors']} erros")
        else:
            print("  [terapeak] EBAY_CLIENT_ID/SECRET ausentes — sellers ficam "
                  "vazios (share Probstein sai n/d).")

    n = store.append_records(out_path, records)
    print(f"  [terapeak] {stats.summary()}")
    print(f"  [terapeak] {n} registro(s) gravados em {out_path}")
    return 0


if __name__ == "__main__":
    from lib.console import harden_stdout
    harden_stdout()
    sys.exit(main())
