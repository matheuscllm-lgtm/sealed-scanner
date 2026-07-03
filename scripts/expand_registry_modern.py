#!/usr/bin/env python3
"""expand_registry_modern.py — gera entradas de registry para selados modernos.

Puxa os produtos selados dos sets modernos (Mega Evolution + SV era) do tcgcsv,
casa com os tipos que importamos, e emite entradas prontas pro sku_registry.yaml.

Match terms são em PT (o título da Liga vem em PT e o adapter mantém o original),
então NÃO precisa mexer no liga_adapter — as set_terms/type_terms PT casam o título
cru. Inclui também termos EN por robustez.

Saída: scripts/registry_additions.yaml (pra revisar antes de mergear) + resumo.
Uso: python scripts/expand_registry_modern.py
"""
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# group_id tcgcsv -> (set EN, set_code, [termos de set PT/EN p/ casar título Liga])
GROUPS = {
    24380: ("Mega Evolution", "MEG", ["megaevolução 1", "megaevolucao 1", "mega evolution"]),
    24448: ("Phantasmal Flames", "PFL", ["fogo fantasmagórico", "fogo fantasmagorico", "phantasmal flames", "megaevolução 2 ", "megaevolucao 2 "]),
    24541: ("Ascended Heroes", "ASC", ["heróis excelsos", "herois excelsos", "ascended heroes", "megaevolução 2.5", "megaevolucao 2.5"]),
    24587: ("Perfect Order", "POR", ["equilíbrio perfeito", "equilibrio perfeito", "perfect order", "megaevolução 3", "megaevolucao 3"]),
    24655: ("Chaos Rising", "CRI", ["caos ascendente", "chaos rising", "megaevolução 4", "megaevolucao 4"]),
    24325: ("Black Bolt", "BLK", ["raio preto", "black bolt"]),
    24326: ("White Flare", "WHT", ["fogo branco", "white flare"]),
    24269: ("Destined Rivals", "DRI", ["rivais predestinados", "destined rivals"]),
    24073: ("Journey Together", "JTG", ["amigos de jornada", "journey together"]),
    23821: ("Prismatic Evolutions", "PRE", ["evoluções prismáticas", "evolucoes prismaticas", "prismatic evolutions"]),
    23651: ("Surging Sparks", "SSP", ["fagulhas impetuosas", "surging sparks"]),
    23537: ("Stellar Crown", "SCR", ["coroa estelar", "stellar crown"]),
    23529: ("Shrouded Fable", "SFA", ["fábulas nebulosas", "fabulas nebulosas", "shrouded fable"]),
    23473: ("Twilight Masquerade", "TWM", ["máscaras do crepúsculo", "mascaras do crepusculo", "twilight masquerade"]),
    23381: ("Temporal Forces", "TEF", ["forças temporais", "forcas temporais", "temporal forces"]),
    23286: ("Paradox Rift", "PAR", ["fenda paradoxal", "paradox rift"]),
    23237: ("Scarlet & Violet 151", "MEW", ["escarlate e violeta - 151", "151", "scarlet & violet 151"]),
    23228: ("Obsidian Flames", "OBF", ["obsidiana em chamas", "obsidian flames"]),
    23120: ("Paldea Evolved", "PAL", ["evoluções em paldea", "evolucoes em paldea", "paldea evolved"]),
    # Set-base SVI faltava desde a criação do dict (gap achado 2026-07-02: pack
    # avulso "Escarlate e Violeta 1" caía sem_match). NUNCA usar "escarlate e
    # violeta" puro como termo — prefixa TODO sub-set SV.
    22873: ("Scarlet & Violet", "SVI", ["escarlate e violeta 1", "scarlet violet base"]),
}

# (regex no nome TCGPlayer, product_type canônico, [type_terms PT/EN], pack_count)
# Ordem importa: específico antes de genérico. Pula code cards / cases / displays.
TYPE_RULES = [
    (r"tech sticker collection", "Tech Sticker", ["blister triplo tech sticker", "tech sticker"], 3),
    (r"booster bundle$", "Booster Bundle", ["combo de pacotes", "booster bundle"], 6),
    (r"elite trainer box$", "Elite Trainer Box", ["coleção treinador avançado", "colecao treinador avancado", "elite trainer box"], 1),
    (r"booster box$", "Booster Box", ["caixa de booster", "booster box", "booster display"], 36),
    (r"\bbooster pack$", "Sleeved Booster", ["booster avulso", "booster pack", "blister unitário", "blister unitario"], 1),
    (r"binder collection$", "Collection Box", ["binder collection", "kit colecionável"], 1),
    (r"mini tin", "Tin", ["mini lata", "mini tin"], 1),
    (r"premium collection", "Premium Collection", ["box coleção premium", "premium collection"], 1),
]

EXCLUDE_BASE = [
    "japones", "japonesa", "japanese", "portugues", "portuguesa", "portuguese", "pt br", "ptbr", "copag",
    "chines", "chinesa", "chinese", "coreano", "coreana", "korean", "espanhol", "espanhola", "spanish",
    "frances", "francesa", "french", "alemao", "alema", "german", "italiano", "italiana", "italian",
    "code card", "acrylic", "acrilico", "case for", "capa para", "protector", "protetor",
]
SKIP_NAME = re.compile(r"code card|\bcase\b|display|booster box case|elite trainer box case|pokemon center|sam's club", re.I)


def fetch(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read())["results"]


def classify(name: str):
    n = name.lower()
    for rx, ptype, terms, pack in TYPE_RULES:
        if re.search(rx, n):
            return ptype, terms, pack
    return None


def main():
    out = []
    summary = {}
    for gid, (set_en, code, set_terms) in GROUPS.items():
        try:
            prods = fetch(f"https://tcgcsv.com/tcgplayer/3/{gid}/products")
            prices = {p["productId"]: p for p in fetch(f"https://tcgcsv.com/tcgplayer/3/{gid}/prices")}
        except Exception as exc:
            print(f"  [aviso] grupo {gid} ({set_en}) falhou: {exc}")
            continue
        for p in prods:
            name = p["name"]
            if SKIP_NAME.search(name):
                continue
            cl = classify(name)
            if not cl:
                continue
            ptype, type_terms, pack = cl
            pr = prices.get(p["productId"], {})
            mp = pr.get("marketPrice") or pr.get("midPrice")
            if not mp:
                continue  # sem preço US não dá pra avaliar
            slug = re.sub(r"[^a-z0-9]+", "-", f"{code}-{ptype}".lower()).strip("-")
            # dedup id por set+type (pega o 1º; variantes por Pokémon caem no mesmo SKU)
            sku_id = slug
            if any(s["id"] == sku_id for s in out):
                continue
            out.append({
                "id": sku_id,
                "name": f"{set_en} {ptype} (English)",
                "product_type": ptype,
                "set": set_en,
                "set_code": code,
                "language": "EN",
                "pack_count": pack,
                "tcgplayer_group_id": gid,
                "tcgplayer_product_id": p["productId"],
                "match": {
                    "set_terms": set_terms,
                    "type_terms": type_terms,
                    "exclude_terms": EXCLUDE_BASE,
                },
                "_us_market": round(float(mp), 2),
            })
            summary.setdefault(set_en, []).append(f"{ptype}=US${mp}")
    # escreve
    import yaml
    addpath = ROOT / "scripts" / "registry_additions.yaml"
    addpath.write_text(yaml.safe_dump({"skus": out}, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"GERADAS {len(out)} entradas -> {addpath}")
    for s, items in summary.items():
        print(f"  {s}: {', '.join(items)}")


if __name__ == "__main__":
    main()
