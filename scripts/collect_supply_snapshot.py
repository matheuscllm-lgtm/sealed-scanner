#!/usr/bin/env python3
"""collect_supply_snapshot.py — snapshot de OFERTA ativa (eBay US) por SKU.

Grava, no store `analysis.files.supply_history` (JSONL, gitignored), um ponto
da série de oferta de cada SKU: nº de anúncios ativos que casam a busca
(`total` da Browse API), vendedores distintos plausíveis, menor pedida e a
escadinha (top-K). A série alimenta o sinal 2.3 (evolução da oferta) — com
<2 pontos o sinal sai HISTORICO_INSUFICIENTE, honesto.

Recorrência é MANUAL (regra da frota: sem cron novo): rode quando quiser
adensar a série; o build_ebay_reference.py também anexa um ponto por run.

Uso:
    python scripts/collect_supply_snapshot.py [--game pokemon] [--limit-skus 10]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import build_ebay_reference as B
import sealed_arbitrage_scanner as S
from lib.analysis import history_store as store
from lib.analysis.profiles import analysis_config, resolve_path
from lib.ebay_client import EbayClient
from lib.env import load_dotenv_if_present

LADDER_TOP_K = 5


def snapshot_records(skus: list, us_prices: dict, client, game_word: str,
                     limit_skus: int = 0, log=print) -> list[dict]:
    """Um registro de oferta por SKU (função separada p/ teste com fake client)."""
    now = store.utc_now_iso()
    out: list[dict] = []
    todo = skus[:limit_skus] if limit_skus else skus
    for i, sku in enumerate(todo, start=1):
        query = B.sku_query(sku, game_word)
        ref_usd = us_prices.get(sku.id)
        min_price = round(B.SUSPECT_RATIO * ref_usd, 2) if ref_usd else None
        try:
            page = (client.search_page(query, min_price=min_price)
                    if hasattr(client, "search_page")
                    else {"itemSummaries": client.search(query, min_price=min_price),
                          "total": None})
        except Exception as exc:
            log(f"  [{i}/{len(todo)}] {sku.id}: erro {type(exc).__name__} — pulado")
            continue
        items = page.get("itemSummaries") or []
        plaus = []
        sellers = set()
        for it in items:
            title = it.get("title") or ""
            if not B.title_passes_gate(title, sku):
                continue
            try:
                usd = float((it.get("price") or {}).get("value"))
            except (TypeError, ValueError):
                continue
            if usd <= 0:
                continue
            plaus.append(usd)
            username = ((it.get("seller") or {}).get("username") or "").strip()
            if username:
                sellers.add(username)
        plaus.sort()
        out.append({
            "sku_id": sku.id,
            "captured_at": now,
            "collected_at": now,
            "source_type": "ebay_active",
            "source_url": "https://api.ebay.com/buy/browse/v1/item_summary/search?q="
                          + query.replace(" ", "+"),
            "active_count": page.get("total"),
            "plausible_in_page": len(plaus),
            "sellers": len(sellers),
            "min_price_usd": plaus[0] if plaus else None,
            "ladder_usd": plaus[:LADDER_TOP_K],
            "query": query,
        })
        log(f"  [{i}/{len(todo)}] {sku.id}: total={page.get('total')} · "
            f"{len(plaus)} plausíveis na página · menor "
            f"{'US$ %.2f' % plaus[0] if plaus else 'n/d'}")
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Snapshot de oferta ativa (eBay US) por SKU.")
    ap.add_argument("--game", default="pokemon", choices=sorted(B.GAME_PROFILES))
    ap.add_argument("--limit-skus", type=int, default=0)
    args = ap.parse_args(argv)

    profile = B.GAME_PROFILES[args.game]
    config = S.load_yaml(ROOT / S.GAME_PROFILES[args.game]["config"], "config.yaml")
    acfg = analysis_config(config)
    out_path = resolve_path(ROOT, (acfg.get("files") or {}).get(
        "supply_history", "data/history/supply_pokemon.jsonl"))

    load_dotenv_if_present()
    client = EbayClient()
    if not client.configured:
        print("  AVISO: EBAY_CLIENT_ID/SECRET ausentes — snapshot de oferta não "
              "coletado (a série fica como está; nada é sobrescrito).")
        return 0
    registry_data = S.load_yaml(ROOT / profile["registry"], "registry")
    skus = S.build_registry(registry_data)
    us_ref = ROOT / profile["us_reference"]
    us_prices = (S.load_json(us_ref, us_ref.name) or {}).get("prices", {}) \
        if us_ref.exists() else {}

    records = snapshot_records(skus, us_prices, client, profile["game_word"],
                               limit_skus=args.limit_skus)
    n = store.append_records(out_path, records)
    print(f"  [supply] {n} snapshot(s) de oferta anexados a {out_path}")
    return 0


if __name__ == "__main__":
    from lib.console import harden_stdout
    harden_stdout()
    sys.exit(main())
