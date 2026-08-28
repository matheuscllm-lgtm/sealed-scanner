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
    python build_us_reference.py --game onepiece             # perfil One Piece

Categorias tcgcsv/TCGplayer por jogo: Pokémon = 3, One Piece = 68 (catálogo
EN — mesma categoria usada pelo op_scanner da frota). ⚠️ NÃO confundir com os
IDs `categ=N` do site da Liga (namespace próprio do site: lá 27 = ETB; no
tcgcsv 27 = Dragon Ball Masters).
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

# Faixas de plausibilidade (USD) por tipo de produto — guard FP-safe.
# Um preço FORA da faixa do tipo quase sempre é pid errado/variante trocada num
# refresh (ex.: um SKU "Mini Tin" apontando sem querer p/ um bundle de US$230, ou
# um booster avulso pegando US$0,50 de code-card). Em vez de gravar a referência
# suspeita — que viraria GREEN/RED falso lá no scanner — o build EXCLUI esse SKU
# (fica sem referência -> o scanner classifica RED `sem_referencia_us`, nunca um
# deal fabricado). Faixas GENEROSAS de propósito: só pegam erro grosseiro, não
# rejeitam deal legítimo. Tipo não-listado = sem checagem (não barra nada novo).
SANITY_BANDS_USD: dict[str, tuple[float, float]] = {
    "Sleeved Booster": (2.0, 60.0),
    "Booster Pack": (2.0, 60.0),
    "Vintage Pack": (10.0, 500.0),  # packs fora de catálogo (POP Series/WOTC): mercado ~$15-400
    "Tech Sticker": (12.0, 130.0),
    "Blister": (3.0, 150.0),  # single pack ~$8 .. 3-pack/premium ~$45 (banda generosa; barra case ~$600 se pid trocado)
    "Booster Bundle": (20.0, 320.0),
    "Collection Box": (15.0, 450.0),
    "Elite Trainer Box": (25.0, 950.0),
    "Premium Collection": (25.0, 1300.0),
    "Booster Box": (60.0, 1300.0),
    "Mini Tin": (6.0, 95.0),
    "Tin": (6.0, 200.0),
    "Mini Tin Display": (70.0, 750.0),
}

# Faixas do perfil ONE PIECE (tcgcsv categoria 68; tipos do registry OP).
# Mesma filosofia FP-safe: generosas, só pegam pid trocado/variante errada.
# Conferidas contra os preços reais do tcgcsv na criação do perfil (2026-08)
# — ex.: OP16 Booster Box market US$204,70.
SANITY_BANDS_USD_ONEPIECE: dict[str, tuple[float, float]] = {
    # Tetos recalibrados 2026-08-28 com o back-catalog OP-01..OP-08 (marketPrice
    # REAL do dia: Romance Dawn Box US$4.960,70; DP Vol.2 US$226,66; DP Vol.2
    # Display US$1.512,59; Romance Dawn Sleeved US$151,95) — bandas antigas
    # calibradas só no catálogo moderno barravam produto legítimo valorizado.
    "Booster Box": (40.0, 6000.0),
    "Booster Pack": (2.0, 80.0),
    "Sleeved Booster Pack": (2.0, 300.0),
    "Double Pack Set": (4.0, 400.0),
    "Double Pack Set Display": (30.0, 2500.0),
    "Starter Deck": (5.0, 500.0),
    "Starter Deck Display": (30.0, 1500.0),
    "Extra Booster Box": (40.0, 1500.0),
    "Extra Booster Pack": (2.0, 80.0),
    # Operador 2026-08-17 — escopo OP ampliado (cases/collections/tins/gift).
    # Bandas calibradas nos marketPrice REAIS do tcgcsv no dia da ampliação:
    # box cases US$2.3k–9k; tin display ~US$460; gift display ~US$2.2k;
    # illustration box US$38–824 (Vol.7/8 vs EX).
    "Booster Box Case": (300.0, 15000.0),
    "Double Pack Set Display Case": (100.0, 5000.0),
    "Treasure Booster Set": (50.0, 800.0),
    "Treasure Booster Set Display Case": (200.0, 5000.0),
    "Illustration Box": (15.0, 1500.0),
    "Illustration Box Case": (150.0, 5000.0),
    "Devil Fruits Collection": (20.0, 800.0),
    "Devil Fruits Collection Case": (100.0, 5000.0),
    "Tin Pack Set": (10.0, 300.0),
    "Tin Pack Set Display": (100.0, 2000.0),
    "Tin Pack Set Display Case": (500.0, 8000.0),
    "Gift Collection": (100.0, 2000.0),
    "Gift Collection Display": (500.0, 8000.0),
    # 2026-08-28 — família Premium Card Collection (grupo guarda-chuva 17675):
    # marketPrice real no dia da inclusão = US$76,75 (Best Selection Vol.5) a
    # US$891,50 (25th Edition); banda com folga p/ flutuação, nunca chutada.
    "Premium Card Collection": (40.0, 2000.0),
}

# Seleção de banda por nome (--bands) — o objeto Pokémon é o MESMO de sempre
# (conteúdo travado em tests/test_reference_guards.py; não mexer).
BANDS_BY_GAME: dict[str, dict[str, tuple[float, float]]] = {
    "pokemon": SANITY_BANDS_USD,
    "onepiece": SANITY_BANDS_USD_ONEPIECE,
}

# Perfis por jogo: defaults de registry/saída/categoria/bandas do --game.
GAME_PROFILES: dict[str, dict] = {
    "pokemon": {
        "registry": "sku_registry.yaml",
        "output": "data/us_reference.json",
        "category_id": POKEMON_CATEGORY_ID,
        "bands": "pokemon",
    },
    "onepiece": {
        "registry": "sku_registry_onepiece.yaml",
        "output": "data/us_reference_onepiece.json",
        "category_id": 68,   # One Piece Card Game (catálogo EN do TCGplayer)
        "bands": "onepiece",
    },
}
UA = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--game", default="pokemon", choices=sorted(GAME_PROFILES),
                        help="perfil de jogo (define registry/saída/categoria/bandas default)")
    parser.add_argument("--registry", default=None,
                        help="caminho do sku_registry (default: do --game)")
    parser.add_argument("--output", default=None,
                        help="JSON de saída (default: do --game)")
    parser.add_argument("--category-id", type=int, default=None,
                        help="categoria tcgcsv/TCGplayer (default: do --game; Pokémon=3, One Piece=68)")
    parser.add_argument("--bands", default=None, choices=sorted(BANDS_BY_GAME),
                        help="conjunto de sanity bands (default: do --game)")
    parser.add_argument(
        "--price-field",
        default="marketPrice",
        choices=["marketPrice", "lowPrice", "midPrice", "highPrice"],
    )
    args = parser.parse_args(argv)

    profile = GAME_PROFILES[args.game]
    registry_path = Path(args.registry) if args.registry else SCRIPT_DIR / profile["registry"]
    output_path = Path(args.output) if args.output else SCRIPT_DIR / profile["output"]
    category_id = args.category_id if args.category_id is not None else profile["category_id"]
    bands = BANDS_BY_GAME[args.bands or profile["bands"]]

    registry = yaml.safe_load(registry_path.read_text(encoding="utf-8"))
    skus = registry.get("skus", [])

    targets: list[tuple[str, int, int, str]] = []
    for sku in skus:
        pid = sku.get("tcgplayer_product_id")
        gid = sku.get("tcgplayer_group_id")
        if pid is None or gid is None:
            print(f"  [aviso] SKU sem tcgplayer_*_id: {sku.get('id')}")
            continue
        targets.append((sku["id"], int(gid), int(pid), sku.get("product_type", "")))

    if not targets:
        print("ERRO: nenhum SKU tem tcgplayer_product_id mapeado.")
        return 2

    # Visibilidade da cobertura do guard: um product_type sem faixa não é checado
    # (fail-open). Avisa pra que uma grafia divergente/tipo novo não passe sem
    # sanity-band em silêncio.
    types_seen = {t[3] for t in targets if t[3]}
    no_band = sorted(t for t in types_seen if t not in bands)
    if no_band:
        print(f"  [aviso] product_type sem sanity-band (não checado): {', '.join(no_band)}")

    prices_cache: dict[int, list] = {}
    out: dict[str, float] = {}
    n_out_of_band = 0

    for sku_id, gid, pid, product_type in targets:
        if gid not in prices_cache:
            url = f"https://tcgcsv.com/tcgplayer/{category_id}/{gid}/prices"
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
        price = float(price)
        # Guard FP-safe: preço fora da faixa plausível do tipo = pid errado/
        # variante trocada -> NÃO grava (SKU fica sem referência -> RED honesto).
        band = bands.get(product_type)
        if band is not None and not (band[0] <= price <= band[1]):
            n_out_of_band += 1
            print(
                f"  [GUARD] {sku_id:24s} US${price} FORA da faixa {product_type} "
                f"{band[0]}-{band[1]} (pid={pid}) — EXCLUÍDO (provável variante trocada)"
            )
            continue
        out[sku_id] = price
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
    out_path = output_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"\nEscrito: {out_path}")
    print(f"SKUs com preço: {len(out)} de {len(targets)}")
    if n_out_of_band:
        print(f"[GUARD] {n_out_of_band} SKU(s) excluído(s) por preço fora da faixa do tipo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
