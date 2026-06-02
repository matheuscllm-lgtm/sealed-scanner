#!/usr/bin/env python3
"""readd_tins_split.py — re-adiciona os Tins ao registry com SPLIT correto.

Contexto (2026-06-02): os 6 SKUs `*-tin` foram removidos porque "Mini Lata" e
"Lata premium" se confundiam — cada `*-tin` antigo apontava arbitrariamente
para UMA lata de personagem (e o `asc-tin` apontava para o 5-Pack!). Como o
catálogo do TCGPlayer mostra, esses 6 sets NÃO têm "Tin premium": a linha é
Mini Tin avulsa (~US$17-50), Mini Tin **Display** (a caixa lacrada de latas,
~US$180-520) e Display Case (atacado). A confusão real é avulsa vs Display
(gap de ~10x). Este script recria o split certo:

  {set}-mini-tin          -> lata AVULSA; preço = a avulsa MAIS BARATA do set
                             (conservador); exclui display/case/box/booster/etb.
  {set}-mini-tin-display  -> a CAIXA (Mini Tin Display); requires "display",
                             exclui "booster" (p/ não colidir com Display de Booster).

Anexa os 12 blocos como TEXTO ao fim de sku_registry.yaml (lista YAML ignora
ordem; mantém o arquivo existente e suas âncoras intactos) e injeta os preços
US (marketPrice via tcgcsv — idênticos ao que build_us_reference.py produz) em
data/us_reference.json. Idempotente: aborta se algum id já existir.

Uso: python scripts/readd_tins_split.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "sku_registry.yaml"
US_REF = ROOT / "data" / "us_reference.json"

# Bloco de idioma + acessório, comum a todos os SKUs do registry.
BASE_EXCLUDE = [
    "japones", "japonesa", "japanese", "portugues", "portuguesa", "portuguese",
    "pt br", "ptbr", "copag", "chines", "chinesa", "chinese", "coreano",
    "coreana", "korean", "espanhol", "espanhola", "spanish", "frances",
    "francesa", "french", "alemao", "alema", "german", "italiano", "italiana",
    "italian", "acrylic", "acrilico", "magnetic", "protector", "protetor",
    "storage", "case for", "capa para",
]
TIN_TYPE = ["mini tin", "mini lata", "mini latas", "minilata", "lata", "latas", "tin"]
# Tudo que NÃO é uma lata avulsa -> a avulsa nunca casa com caixa/display/box.
SINGLE_XTYPE = [
    "display", "case", "caixa", "5 pack", "5-pack", "5pack", "set of", "booster",
    "booster box", "box", "elite trainer", "elite trainer box", "etb", "bundle",
    "booster bundle", "blister", "collection", "collection box", "premium",
    "premium collection", "tech sticker", "build", "battle", "sleeved", "sleeve",
    "pokemon center",
]
# Display exige "display"; exclui "booster" p/ não colidir com "Display de Booster".
DISPLAY_XTYPE = [
    "booster", "booster box", "caixa de booster", "display de booster",
    "booster display", "box", "case", "display case", "elite trainer",
    "elite trainer box", "etb", "bundle", "booster bundle", "blister",
    "collection", "collection box", "premium", "premium collection",
    "tech sticker", "build", "battle", "sleeved", "sleeve", "pokemon center",
    "5 pack", "5-pack", "5pack", "set of",
]

# Por set: prefixo, group_id, set_terms (extra além do existente),
# avulsa (product_id + nome + market USD) e display (product_id + nome + market USD).
SETS = [
    {
        "pref": "meg", "set": "Mega Evolution", "group_id": 24380,
        "set_terms_extra": [],
        "single": (649395, "Mega Heroes Mini Tin [Mega Kangaskhan]", 17.22),
        "display": (649392, "Mega Heroes Mini Tin Display", 255.86),
    },
    {
        "pref": "asc", "set": "Ascended Heroes", "group_id": 24541,
        "set_terms_extra": [],
        "single": (668534, "Ascended Heroes Mini Tin [Togepi & Totodile]", 26.88),
        "display": (679556, "Ascended Heroes Mini Tin Display", 315.90),
    },
    {
        "pref": "blk", "set": "Black Bolt", "group_id": 24325,
        "set_terms_extra": ["unova"],  # as latas são marca "Unova Mini Tin"
        "single": (630441, "Unova Mini Tin [Volcarona & Emolga]", 19.27),
        "display": (630446, "Unova Mini Tin Display", 189.96),
    },
    {
        "pref": "pre", "set": "Prismatic Evolutions", "group_id": 23821,
        "set_terms_extra": [],
        "single": (593457, "Prismatic Evolutions Mini Tin [Flareon]", 29.28),
        "display": (593463, "Prismatic Evolutions Mini Tin Display", 230.74),
    },
    {
        "pref": "sfa", "set": "Shrouded Fable", "group_id": 23529,
        "set_terms_extra": [],
        "single": (553011, "Shrouded Fable Mini Tin (Munkidori)", 17.17),
        "display": (553008, "Shrouded Fable Mini Tin Display", 180.77),
    },
    {
        "pref": "mew", "set": "Scarlet & Violet 151", "group_id": 23237,
        "set_terms_extra": [],
        "single": (522703, "151 Mini Tin [Hitmonlee & Kadabra]", 45.51),
        "display": (502008, "151 Mini Tin Display", 518.14),
    },
]


def render_terms(key: str, terms: list, anchor: str | None, defined: set[str]) -> list[str]:
    """Emite uma lista YAML. Com `anchor`: define (&) na 1ª vez, referencia (*) depois
    — mesmo padrão de âncoras do registry, p/ não repetir listas longas 12x."""
    if anchor and anchor in defined:
        return [f"    {key}: *{anchor}"]
    head = f"    {key}: &{anchor}" if anchor else f"    {key}:"
    if anchor:
        defined.add(anchor)
    return [head] + [f"    - {t}" for t in terms]


def render_sku(*, sku_id, name, product_type, set_name, set_code, pack_count,
               group_id, product_id, set_terms, type_terms, exclude_terms,
               requires_terms=None, type_anchor=None, excl_anchor=None,
               req_anchor=None, defined: set[str]) -> str:
    lines = [
        f"- id: {sku_id}",
        f"  name: {name}",
        f"  product_type: {product_type}",
        f"  set: {set_name}",
        f"  set_code: {set_code}",
        "  language: EN",
        f"  pack_count: {pack_count}",
        f"  tcgplayer_group_id: {group_id}",
        f"  tcgplayer_product_id: {product_id}",
        "  match:",
    ]
    lines += render_terms("set_terms", set_terms, None, defined)  # set-specific, inline
    lines += render_terms("type_terms", type_terms, type_anchor, defined)
    if requires_terms:
        lines += render_terms("requires_terms", requires_terms, req_anchor, defined)
    lines += render_terms("exclude_terms", exclude_terms, excl_anchor, defined)
    return "\n".join(lines)


def main() -> int:
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    existing_ids = {s["id"] for s in reg["skus"]}
    # set_code + set_terms resolvidos a partir de um SKU existente do mesmo set.
    by_set: dict[str, dict] = {}
    for s in reg["skus"]:
        by_set.setdefault(s.get("set"), s)

    new_ids = []
    for spec in SETS:
        for suffix in ("mini-tin", "mini-tin-display"):
            sid = f"{spec['pref']}-{suffix}"
            if sid in existing_ids:
                print(f"ERRO: id já existe: {sid} — abortando (idempotência).")
                return 1
            new_ids.append(sid)

    blocks: list[str] = []
    prices: dict[str, float] = {}
    defined: set[str] = set()  # âncoras já emitidas (define na 1ª, referencia depois)
    for spec in SETS:
        ref = by_set.get(spec["set"])
        if ref is None:
            print(f"ERRO: set não encontrado no registry: {spec['set']}")
            return 1
        set_code = ref.get("set_code", "")
        base_terms = list(ref["match"]["set_terms"])
        set_terms = base_terms + [t for t in spec["set_terms_extra"] if t not in base_terms]

        s_pid, s_name, s_mkt = spec["single"]
        d_pid, d_name, d_mkt = spec["display"]

        blocks.append(render_sku(
            sku_id=f"{spec['pref']}-mini-tin",
            name=f"{spec['set']} Mini Tin (English)",
            product_type="Mini Tin", set_name=spec["set"], set_code=set_code,
            pack_count=2, group_id=spec["group_id"], product_id=s_pid,
            set_terms=set_terms, type_terms=TIN_TYPE,
            exclude_terms=SINGLE_XTYPE + BASE_EXCLUDE,
            type_anchor="tin_type", excl_anchor="tin_excl_single", defined=defined,
        ))
        prices[f"{spec['pref']}-mini-tin"] = s_mkt

        blocks.append(render_sku(
            sku_id=f"{spec['pref']}-mini-tin-display",
            name=f"{spec['set']} Mini Tin Display (English)",
            product_type="Mini Tin Display", set_name=spec["set"], set_code=set_code,
            pack_count=10, group_id=spec["group_id"], product_id=d_pid,
            set_terms=set_terms, type_terms=TIN_TYPE, requires_terms=["display"],
            exclude_terms=DISPLAY_XTYPE + BASE_EXCLUDE,
            type_anchor="tin_type", excl_anchor="tin_excl_display",
            req_anchor="tin_req", defined=defined,
        ))
        prices[f"{spec['pref']}-mini-tin-display"] = d_mkt

    # 1) Anexa blocos ao registry (texto, diff aditivo).
    text = REGISTRY.read_text(encoding="utf-8")
    if not text.endswith("\n"):
        text += "\n"
    text += "\n".join(blocks) + "\n"
    REGISTRY.write_text(text, encoding="utf-8")

    # 2) Injeta preços US (idênticos ao build_us_reference.py p/ esses product_id).
    ref_doc = json.loads(US_REF.read_text(encoding="utf-8"))
    ref_doc["prices"].update(prices)
    US_REF.write_text(json.dumps(ref_doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"OK: +{len(new_ids)} SKUs de Tin anexados, +{len(prices)} preços US.")
    for sid in new_ids:
        print(f"   {sid:26s} US=${prices[sid]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
