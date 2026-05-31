#!/usr/bin/env python3
"""
build_us_reference.py — popula data/us_reference.json com preços REAIS
do TCGPlayer, via tcgcsv.com.

tcgcsv.com é um espelho público da API do TCGPlayer (grátis, sem auth,
sem CloudFlare). Atualiza diariamente ~20:00 UTC.

Lê sku_registry.yaml. Para cada SKU com `tcgplayer_product_id`
e `tcgplayer_group_id`, busca o preço Market do TCGPlayer (1 fetch por
group). Escreve data/us_reference.json no mesmo formato que o
scanner já consome.

Uso:
    python build_us_reference.py
    python build_us_reference.py --price-field marketPrice   # default
    python build_us_reference.py --price-field lowPrice
    python build_us_reference.py --price-field midPrice

Categoria Pokémon no TCGPlayer = 3 (constante).
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

try:
    import yaml
except ImportError:
    print("ERRO: PyYAML não instalado. pip install -r requirements.txt")
    sys.exit(2)

SCRIPT_DIR = Path(__file__).resolve().parent
POKEMON_CATEGORY_ID = 3
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--registry", default=str(SCRIPT_DIR / "sku_registry.yaml"))
    parser.add_argument("--output", default=str(SCRIPT_DIR / "data" / "us_reference.json"))
    parser.add_argument(
        "--price-field",
        default="marketPrice",
        choices=["marketPrice", "lowPrice", "midPrice", "highPrice"],
    )
    args = parser.parse_args()

    registry = yaml.safe_load(Path(args.registry).read_text(encoding="utf-8"))
    skus = registry.get("skus", [])

    targets: list[tuple[str, int, int]] = []
    for sku in skus:
        pid = sku.get("tcgplayer_product_id")
        gid = sku.get("tcgplayer_group_id")
        if pid is None or gid is None:
            print(f"  [aviso] SKU sem tcgplayer_*_id: {sku.get('id')}")
            continue
        targets.append((sku["id"], int(gid), int(pid)))

    if not targets:
        print("ERRO: nenhum SKU tem tcgplayer_product_id mapeado.")
        return 2

    prices_cache: dict[int, list] = {}
    out: dict[str, float] = {}

    for sku_id, gid, pid in targets:
        if gid not in prices_cache:
            url = f"https://tcgcsv.com/tcgplayer/{POKEMON_CATEGORY_ID}/{gid}/prices"
            print(f"  fetch group {gid} ...")
            prices_cache[gid] = fetch_json(url)["results"]
        match = next(
            (
                p
                for p in prices_cache[gid]
                if p.get("productId") == pid and p.get("subTypeName") in (None, "Normal")
            ),
            None,
        )
        if match is None:
            print(f"  [aviso] sem preço para {sku_id} (productId={pid})")
            continue
        price = match.get(args.price_field)
        if price is None:
            print(f"  [aviso] {args.price_field} nulo para {sku_id}")
            continue
        out[sku_id] = float(price)
        print(f"  {sku_id:24s} {args.price_field}=${price}")

    payload = {
        "_comment": (
            "Gerado por build_us_reference.py a partir de tcgcsv.com (espelho da "
            "API do TCGPlayer). NÃO editar à mão — rode o script para refrescar."
        ),
        "reference": f"TCGPlayer {args.price_field} via tcgcsv.com",
        "currency": "USD",
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "prices": out,
    }
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nEscrito: {out_path}")
    print(f"SKUs com preço: {len(out)} de {len(targets)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
