#!/usr/bin/env python3
"""build_set_meta.py — datas de lançamento REAIS dos sets do registry.

Busca `https://tcgcsv.com/tcgplayer/<cat>/groups` UMA vez, filtra os
`tcgplayer_group_id` presentes no registry do jogo e grava
`data/set_meta[_onepiece].json` (VERSIONADO — dado de referência, como o
us_reference): `{captured_at, category_id, groups: {gid: {name, abbreviation,
publishedOn, url}}}`.

publishedOn é a data REAL do tcgcsv — a idade do set NUNCA é inferida (regra
da frota: nunca inventar data). Refresque quando cadastrar set novo.

Uso: python build_set_meta.py [--game pokemon] [--category-id 3]
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import yaml

import sealed_arbitrage_scanner as S
from lib.analysis.profiles import analysis_config, resolve_path

CATEGORY_BY_GAME = {"pokemon": "3", "onepiece": "68"}


def fetch_groups(category_id: str) -> list[dict]:
    url = f"https://tcgcsv.com/tcgplayer/{category_id}/groups"
    req = urllib.request.Request(url, headers={"User-Agent": "sealed-scanner/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode("utf-8")).get("results", [])


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Gera data/set_meta.json (publishedOn real por set).")
    ap.add_argument("--game", default="pokemon", choices=sorted(S.GAME_PROFILES))
    ap.add_argument("--category-id", default=None)
    args = ap.parse_args(argv)

    profile = S.GAME_PROFILES[args.game]
    config = S.load_yaml(SCRIPT_DIR / profile["config"], "config.yaml")
    acfg = analysis_config(config)
    cat = args.category_id or str((acfg.get("tcgcsv") or {}).get(
        "category_id") or CATEGORY_BY_GAME[args.game])
    out_path = resolve_path(SCRIPT_DIR, (acfg.get("files") or {}).get(
        "set_meta", "data/set_meta.json"))

    registry = yaml.safe_load((SCRIPT_DIR / profile["registry"]).read_text(encoding="utf-8")) or {}
    wanted = {str(s.get("tcgplayer_group_id")) for s in registry.get("skus", []) or []
              if s.get("tcgplayer_group_id")}
    try:
        groups = fetch_groups(cat)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"ERRO: tcgcsv indisponível ({exc}) — set_meta anterior preservado.")
        return 1
    out = {}
    for g in groups:
        gid = str(g.get("groupId"))
        if gid in wanted:
            out[gid] = {"name": g.get("name"), "abbreviation": g.get("abbreviation"),
                        "publishedOn": (g.get("publishedOn") or "")[:10],
                        "url": g.get("url") or ""}
    missing = wanted - set(out)
    payload = {
        "_comment": ("Gerado por build_set_meta.py — publishedOn REAL do tcgcsv "
                     "por group_id do registry. Idade de set nunca é inferida."),
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "category_id": cat,
        "groups": out,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
    print(f"  [set_meta] {len(out)} grupo(s) gravados em {out_path}"
          + (f" · {len(missing)} do registry SEM grupo no tcgcsv: {sorted(missing)}"
             if missing else ""))
    return 0


if __name__ == "__main__":
    from lib.console import harden_stdout
    harden_stdout()
    sys.exit(main())
