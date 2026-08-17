#!/usr/bin/env python3
"""scripts/gen_onepiece_registry.py — gera/regenera o sku_registry_onepiece.yaml
a partir de dados REAIS do tcgcsv.com (categoria 68 = One Piece Card Game, EN).

Regra inviolável do repo aplicada aqui: **nunca deduzir/inventar termo de set,
productId ou referência** — todo SKU sai de um produto real do tcgcsv, com
product_id real e preço market atual DENTRO da sanity band do tipo (produto
sem preço/fora da banda NÃO entra; contado no resumo). Os únicos termos
"derivados" são variantes MECÂNICAS da abbreviation oficial do grupo
("OP16" -> "op16"/"op 16"), marcadas como tal.

Escopo do seed (recência primeiro — lição da frota: deal mora em lançamento;
back-catalog é mercado eficiente): grupos principais de PRB-01 (2024-11) até
hoje + os DOIS grupos guarda-chuva sem cutoff (17675 Promotion Cards e 23304
Collection Sets — é onde moram Treasure/Illustration/Tin/Gift/Devil Fruits).
Grupos de evento/promo/demo (RE/PRE/ANN/DD/RP/PR) ficam FORA. Tipos cobertos
(operador 2026-08-17 — "revisar o scanner focado em BUSCAR"): Booster Box
(+Case), Booster Pack, Sleeved Booster Pack, Double Pack Set (+Display,
+Display Case), Extra Booster Box/Pack, Treasure Booster Set (+Display Case),
Illustration Box (+Case), Devil Fruits Collection (+Case), Tin Pack Set
(+Display, +Display Case), Gift Collection (+Display). Starter Deck (+Display)
segue gerado mas FORA do escopo de compra (scope.exclude, operador 2026-08-15).
FORA (contado): Dash Pack / Special DON!! (inserts), Bonus Pack, Promotion
Pack, "Set of N" (lote), case de deck, deck sets (LT-01/SD01) e qualquer nome
de tipo não reconhecido.

Uso (rede: tcgcsv.com):
    python scripts/gen_onepiece_registry.py            # grava o YAML
    python scripts/gen_onepiece_registry.py --dry-run  # só imprime o resumo
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from build_us_reference import SANITY_BANDS_USD_ONEPIECE  # noqa: E402

CATEGORY_ID = 68
UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) sealed-scanner/onepiece",
      "Accept": "application/json"}

# Grupos do seed: (groupId verificado ao vivo, code curto p/ slug).
# Cutoff = PRB-01 (2024-11-08). Para AMPLIAR o catálogo depois: adicionar o
# groupId aqui (lista em https://tcgcsv.com/tcgplayer/68/groups) e rodar de novo.
SEED_GROUPS: list[tuple[int, str]] = [
    (24736, "op17"),   # The World's Strongest Warriors
    (24749, "st31"), (24750, "st32"), (24751, "st33"),
    (24752, "st34"), (24753, "st35"), (24754, "st36"),
    (24678, "st30"),   # Starter Deck EX: Luffy & Ace
    (24664, "op16"),   # The Time of Battle
    (24637, "op15"),   # Adventure on Kami's Island (abbrev oficial OP15-EB04)
    (24545, "eb03"),   # Extra Booster: One Piece Heroines Edition
    (24575, "st29"),   # Starter Deck 29: Egghead
    (24537, "op14"),   # The Azure Sea's Seven
    (24303, "op13"),   # Carrying On His Will
    (24305, "prb02"),  # Premium Booster -The Best- Vol. 2
    (24304, "st22"),   # Starter Deck 22: Ace & Newgate
    (24302, "op12"),   # Legacy of the Master
    (24241, "op11"),   # A Fist of Divine Speed
    (24282, "st23"), (24283, "st24"), (24284, "st25"),
    (24285, "st26"), (24286, "st27"), (24287, "st28"),
    (23834, "eb02"),   # Extra Booster: Anime 25th Collection
    (23766, "op10"),   # Royal Blood
    (23991, "st21"),   # Starter Deck EX: Gear 5
    (23589, "op09"),   # Emperors in the New World
    (23496, "prb01"),  # Premium Booster -The Best-
    # Grupos guarda-chuva SEM cutoff (operador 2026-08-17): é onde o tcgcsv
    # lista as famílias Treasure Booster / Illustration Box / Tin Pack /
    # Gift Collection (17675) e Devil Fruits Collection (23304). A identidade
    # desses SKUs vem do NOME do produto (vol/tema), nunca do nome do grupo.
    (17675, "promo"),  # One Piece Promotion Cards
    (23304, "opcs"),   # One Piece Collection Sets
]

# Vocabulário PT de TIPO da plataforma LigaMagic (validado no site Pokémon da
# mesma plataforma) — pendente confirmação no site OP (SETUP-VALIDACAO.md §B).
PT_BOX = ["caixa de booster"]
PT_PACK = ["booster avulso"]

# Nomes de produto que NUNCA viram SKU (lote/insert/desconhecido) — contados.
# "case" saiu da lista em 2026-08-17: cases agora são SKUs de 1ª classe
# (operador pediu BUSCAR Booster Case / Display Case das famílias novas);
# o que segue lote de verdade é "Set of N" / bundle.
_SKIP_PATTERNS = (
    ("dash pack", re.compile(r"\bdash pack\b", re.I)),
    ("don!! pack", re.compile(r"don!!", re.I)),
    ("bonus pack", re.compile(r"\bbonus pack\b", re.I)),
    ("promotion pack", re.compile(r"\bpromotion pack\b", re.I)),
    ("set of N (lote)", re.compile(r"\bset of \d+\b|\[set of", re.I)),
)

_CASE_RE = re.compile(r"\bcase\b", re.I)
_DISPLAY_RE = re.compile(r"\bdisplay\b", re.I)


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def classify_type(name: str) -> str | None:
    """Deriva o product_type do NOME REAL do tcgcsv. None = fora do escopo."""
    low = name.lower()
    for _, pat in _SKIP_PATTERNS:
        if pat.search(low):
            return None
    has_case = bool(_CASE_RE.search(low))
    has_display = bool(_DISPLAY_RE.search(low))
    # Famílias por NOME (grupos guarda-chuva 17675/23304) — antes dos genéricos.
    if "illustration box" in low:
        return "Illustration Box Case" if has_case else "Illustration Box"
    if "devil fruits collection" in low:
        return "Devil Fruits Collection Case" if has_case else "Devil Fruits Collection"
    if "tin pack set" in low:
        if has_display and has_case:
            return "Tin Pack Set Display Case"
        if has_display:
            return "Tin Pack Set Display"
        if has_case:
            return None            # "case sem display" não existe no catálogo — não chutar
        return "Tin Pack Set"
    if "treasure booster set" in low:
        if has_display and has_case:
            return "Treasure Booster Set Display Case"
        if has_display or has_case:
            return None
        return "Treasure Booster Set"
    if "gift collection" in low:
        if has_case:
            return None            # não existe no catálogo — não chutar
        return "Gift Collection Display" if has_display else "Gift Collection"
    if "double pack set" in low:
        if has_display and has_case:
            return "Double Pack Set Display Case"
        if has_case:
            return None
        return "Double Pack Set Display" if has_display else "Double Pack Set"
    if "sleeved booster" in low:
        return None if has_case else "Sleeved Booster Pack"
    if "booster box case" in low:
        return "Booster Box Case"
    if "starter deck" in low or "ultra deck" in low:
        if has_case:
            return None            # case de deck: decks já estão fora do escopo
        return "Starter Deck Display" if has_display else "Starter Deck"
    if has_case:
        # Nenhuma outra família tem case reconhecido (ex.: EB tratado abaixo).
        if low.startswith("extra booster:") and low.endswith(" box case"):
            return "Booster Box Case"
        return None
    if "booster box" in low:
        return "Booster Box"
    if "booster pack" in low:
        return "Booster Pack"
    if low.startswith("extra booster:"):
        # EB nomeia "… Box" / "… Pack" sem a palavra "booster" no sufixo.
        if low.endswith(" box"):
            return "Extra Booster Box"
        if low.endswith(" pack"):
            return "Extra Booster Pack"
    return None


def abbrev_tokens(code: str) -> list[str]:
    """Variantes MECÂNICAS da abbreviation oficial: 'op16' -> ['op16','op 16']."""
    m = re.match(r"([a-z]+)(\d+)$", code)
    if not m:
        return [code]
    return [code, f"{m.group(1)} {m.group(2)}"]


def _dp_vol_tokens(name: str) -> list[str]:
    """Identidade dos Double Pack Sets = o número do volume (o nome real NÃO
    carrega o nome do set): 'Double Pack Set Vol. 12' -> ['vol 12','volume 12']."""
    m = re.search(r"vol(?:ume)?\.?\s*(\d+)", name, re.I)
    if not m:
        return []
    n = m.group(1)
    return [f"vol {n}", f"volume {n}"]


_LANG_EXCLUDES = ["japanese", "japones", "japonesa", "coreano",
                  "korean", "chines", "chinese"]

# Famílias cuja identidade vem do NOME do produto (grupos guarda-chuva).
_NAME_FAMILIES = {
    "Illustration Box", "Illustration Box Case",
    "Devil Fruits Collection", "Devil Fruits Collection Case",
    "Tin Pack Set", "Tin Pack Set Display", "Tin Pack Set Display Case",
    "Treasure Booster Set", "Treasure Booster Set Display Case",
    "Gift Collection", "Gift Collection Display",
}


def _tin_theme(name: str) -> str:
    """'One Piece Tin Pack Set Vol. 2 -Portgas.D.Ace-' -> 'portgas d ace'."""
    m = re.search(r"-\s*([^-]+?)\s*-\s*$", name)
    return _norm_term(m.group(1)) if m else ""


def _family_sku_parts(name: str, ptype: str) -> tuple[list[str], list[str],
                                                      list[str], list[str], str] | None:
    """(set_terms, type_terms, extra_excludes, requires, slug) da família, ou
    None se a identidade não puder ser extraída do nome real (não chutar)."""
    is_case = ptype.endswith("Case")
    is_display = "Display" in ptype
    vols = _dp_vol_tokens(name)
    voln = re.search(r"vol(?:ume)?\.?\s*(\d+)", name, re.I)
    vslug = f"vol{voln.group(1)}" if voln else ""

    if ptype.startswith("Illustration Box"):
        if vols:
            set_terms, slug = vols, f"ilbox-{vslug}"
        elif re.search(r"\billustration box ex\b", name, re.I):
            set_terms, slug = ["illustration box ex"], "ilbox-ex"
        else:
            return None
        return (set_terms, ["illustration box"],
                [] if is_case else ["display"], ["case"] if is_case else [],
                slug + ("-case" if is_case else ""))
    if ptype.startswith("Devil Fruits Collection"):
        if not vols:
            return None
        return (vols, ["devil fruits collection"],
                [] if is_case else ["display"], ["case"] if is_case else [],
                f"dfc-{vslug}" + ("-case" if is_case else ""))
    if ptype.startswith("Tin Pack Set"):
        if not vols:
            return None
        if ptype == "Tin Pack Set":
            theme = _tin_theme(name)
            if not theme:
                return None       # unidade sem tema = identidade incompleta
            return (vols, ["tin pack"], ["display"], [theme],
                    f"tinpack-{vslug}-{theme.split()[-1]}")
        requires = ["display"] + (["case"] if is_case else [])
        return (vols, ["tin pack"], [], requires,
                f"tinpack-{vslug}-display" + ("-case" if is_case else ""))
    if ptype.startswith("Treasure Booster Set"):
        if is_case:
            return (["treasure booster set"], ["treasure booster"], [],
                    ["display", "case"], "treasure-booster-display-case")
        return (["treasure booster set"], ["treasure booster"],
                ["display"], [], "treasure-booster")
    if ptype.startswith("Gift Collection"):
        m = re.search(r"gift collection (\d{4})", name, re.I)
        if not m:
            return None
        year = m.group(1)
        if is_display:
            return ([f"gift collection {year}"], ["gift collection"], [],
                    ["display"], f"gift{year}-display")
        return ([f"gift collection {year}"], ["gift collection"],
                ["display", "promotion"], [], f"gift{year}")
    return None


def build_sku(prod: dict, group: dict, code: str, price: float) -> dict | None:
    name = prod["name"]
    ptype = classify_type(name)
    if ptype is None:
        return None
    # Grupos guarda-chuva: SÓ famílias com identidade no nome — um "booster
    # pack" promocional solto ali herdaria set_terms do nome do GRUPO (lixo).
    if group["groupId"] in (17675, 23304) and ptype not in _NAME_FAMILIES:
        return None
    group_name = group["name"]
    set_terms: list[str] = []
    type_terms: list[str] = []
    # Case é lote SÓ para SKU que não é case — SKUs de case têm "case" na
    # própria identidade (operador 2026-08-17) e não podem se auto-excluir.
    exclude_terms: list[str] = list(_LANG_EXCLUDES) + (
        ["lote"] if ptype.endswith("Case") else ["case", "lote"])
    requires_terms: list[str] = []

    if ptype in _NAME_FAMILIES:
        parts = _family_sku_parts(name, ptype)
        if parts is None:
            return None
        set_terms, type_terms, extra_exc, requires_terms, fam_slug = parts
        exclude_terms += extra_exc
        return {
            "id": f"{fam_slug}-en",
            "name": name,
            "product_type": ptype,
            "set": group_name,
            "set_code": (group.get("abbreviation") or code).upper(),
            "language": "EN",
            "tcgplayer_group_id": group["groupId"],
            "tcgplayer_product_id": prod["productId"],
            "match": {
                "set_terms": set_terms,
                "type_terms": type_terms,
                "exclude_terms": exclude_terms,
                **({"requires_terms": requires_terms} if requires_terms else {}),
            },
        }

    if ptype in ("Double Pack Set", "Double Pack Set Display",
                 "Double Pack Set Display Case"):
        set_terms = _dp_vol_tokens(name)
        if not set_terms:
            return None
        type_terms = ["double pack"]
        if ptype == "Double Pack Set":
            exclude_terms.append("display")
        elif ptype == "Double Pack Set Display":
            requires_terms.append("display")
        else:
            requires_terms += ["display", "case"]
    elif ptype in ("Starter Deck", "Starter Deck Display"):
        # Âncora = o número/EX do deck (tema colide entre decks: há 2 decks
        # "Monkey.D.Luffy"); tokens da abbreviation oficial (ST-31 -> st31).
        set_terms = abbrev_tokens(code)
        m = re.search(r"starter deck (\d+)", name, re.I)
        if m:
            set_terms.append(f"starter deck {m.group(1)}")
        elif "ex:" in name.lower():
            # Decks EX não têm número: usa o tema REAL do nome ("Luffy & Ace").
            theme = re.sub(r".*ex:\s*", "", name, flags=re.I)
            theme = re.sub(r"\s*display\s*$", "", theme, flags=re.I).strip()
            if theme:
                set_terms.append(_norm_term(theme))
        type_terms = ["starter deck", "ultra deck"]
        if ptype == "Starter Deck":
            exclude_terms += ["display", "set of", "bonus"]
        else:
            requires_terms.append("display")
    else:
        # Sets principais / EB / PRB: nome REAL do grupo + abbreviation mecânica.
        base = _norm_term(re.sub(r"\s*-the best-\s*", " ", group_name, flags=re.I))
        set_terms = [base] + abbrev_tokens(code)
        if code == "op15":
            set_terms += ["eb04", "eb 04"]     # abbreviation oficial é OP15-EB04
        if code == "prb01":
            # 'premium booster' é PREFIXO de 'premium booster vol 2' (PRB-02):
            # sem esta exclusão, todo produto do Vol. 2 casaria os DOIS sets
            # (ambiguidade provada no check de autoconsistência do seed).
            exclude_terms += ["vol 2", "vol ii"]
        if ptype == "Booster Box":
            type_terms = ["booster box"] + PT_BOX
            exclude_terms += ["double pack", "sleeved"]
        elif ptype == "Booster Box Case":
            # EB nomeia o case só como "Box Case" (sem "Booster") — gate de SET
            # escopa, igual ao Extra Booster Box.
            if group_name.lower().startswith("extra booster"):
                type_terms = ["box case"]
            else:
                type_terms = ["booster box case"]
            exclude_terms += ["double pack", "sleeved"]
        elif ptype == "Booster Pack":
            type_terms = ["booster pack"] + PT_PACK
            exclude_terms += ["sleeved", "box", "double pack", "dash"]
        elif ptype == "Sleeved Booster Pack":
            type_terms = ["sleeved booster"]
            exclude_terms += ["box"]
        elif ptype == "Extra Booster Box":
            # EB nomeia o box só como "Box" — termo largo, mas o gate de SET
            # (nome único do EB) escopa; "pack"/"sleeved" excluídos.
            type_terms = ["box"] + PT_BOX
            exclude_terms += ["pack", "sleeved"]
        elif ptype == "Extra Booster Pack":
            type_terms = ["pack"] + PT_PACK
            exclude_terms += ["box", "sleeved", "dash"]

    slug = {
        "Booster Box": "booster-box", "Booster Pack": "booster-pack",
        "Booster Box Case": "booster-box-case",
        "Sleeved Booster Pack": "sleeved-booster",
        "Double Pack Set": "double-pack", "Double Pack Set Display": "double-pack-display",
        "Double Pack Set Display Case": "double-pack-display-case",
        "Starter Deck": "starter-deck", "Starter Deck Display": "starter-deck-display",
        "Extra Booster Box": "eb-box", "Extra Booster Pack": "eb-pack",
    }[ptype]
    return {
        "id": f"{code}-{slug}-en",
        "name": name,
        "product_type": ptype,
        "set": group_name,
        "set_code": (group.get("abbreviation") or code).upper(),
        "language": "EN",
        "tcgplayer_group_id": group["groupId"],
        "tcgplayer_product_id": prod["productId"],
        "match": {
            "set_terms": set_terms,
            "type_terms": type_terms,
            "exclude_terms": exclude_terms,
            **({"requires_terms": requires_terms} if requires_terms else {}),
        },
    }


def _norm_term(text: str) -> str:
    """minúsculas + pontuação->espaço (mesma família do normalize do scanner)."""
    import unicodedata
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    cleaned = "".join(c if c.isalnum() else " " for c in stripped.lower())
    return " ".join(cleaned.split())


def yaml_quote(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def sku_to_yaml(sku: dict) -> str:
    lines = [f"- id: {sku['id']}"]
    for key in ("name", "product_type", "set", "set_code", "language"):
        lines.append(f"  {key}: {yaml_quote(sku[key])}")
    lines.append(f"  tcgplayer_group_id: {sku['tcgplayer_group_id']}")
    lines.append(f"  tcgplayer_product_id: {sku['tcgplayer_product_id']}")
    lines.append("  match:")
    for tkey in ("set_terms", "type_terms", "exclude_terms", "requires_terms"):
        terms = sku["match"].get(tkey)
        if not terms:
            continue
        lines.append(f"    {tkey}:")
        for t in terms:
            lines.append(f"    - {yaml_quote(t)}")
    return "\n".join(lines)


HEADER = """\
# sku_registry_onepiece.yaml — catálogo canônico de SKUs SELADOS de One Piece TCG
#
# GERADO por scripts/gen_onepiece_registry.py a partir de dados REAIS do
# tcgcsv.com (categoria 68 = One Piece Card Game, catálogo EN do TCGplayer).
# NÃO editar productIds/nomes à mão — rode o gerador para ampliar/refrescar.
# Todo SKU entrou com product_id real e preço market DENTRO da sanity band do
# tipo (SANITY_BANDS_USD_ONEPIECE em build_us_reference.py) no dia da geração.
#
# Termos de match:
# - set_terms = nome REAL do grupo tcgcsv + variantes MECÂNICAS da abbreviation
#   oficial ('OP16' -> 'op16'/'op 16'); Double Pack usa o nº do volume (o nome
#   real não carrega set); Starter Deck usa o nº do deck (tema colide).
# - ALIASES PT DE SET: NENHUM — a Bandai não localiza nome de set de One Piece;
#   aliases PT só entram depois de TÍTULOS REAIS da Liga One Piece (runbook
#   SETUP-VALIDACAO.md §B), nunca deduzidos (lição ASI-Evolve da frota).
# - 'caixa de booster'/'booster avulso' = vocabulário PT de TIPO da plataforma
#   LigaMagic (validado no site Pokémon da plataforma) — pendente confirmação
#   no site OP.
#
game: onepiece
tcgcsv_category_id: 68
skus:
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="Gera sku_registry_onepiece.yaml do tcgcsv cat 68")
    ap.add_argument("--output", default=str(ROOT / "sku_registry_onepiece.yaml"))
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    skus: list[dict] = []
    skipped: dict[str, int] = {}
    no_price = 0
    out_of_band = 0
    groups = fetch_json(f"https://tcgcsv.com/tcgplayer/{CATEGORY_ID}/groups")["results"]
    by_id = {g["groupId"]: g for g in groups}
    for gid, code in SEED_GROUPS:
        group = by_id[gid]
        prods = fetch_json(f"https://tcgcsv.com/tcgplayer/{CATEGORY_ID}/{gid}/products")["results"]
        prices = {p["productId"]: p for p in
                  fetch_json(f"https://tcgcsv.com/tcgplayer/{CATEGORY_ID}/{gid}/prices")["results"]
                  if p.get("subTypeName") in (None, "Normal")}
        for prod in prods:
            ext = {e["name"]: e.get("value") for e in (prod.get("extendedData") or [])}
            if ext.get("Rarity"):
                continue          # carta avulsa, não selado
            name = prod["name"]
            ptype = classify_type(name)
            if ptype is None:
                for label, pat in _SKIP_PATTERNS:
                    if pat.search(name.lower()):
                        skipped[label] = skipped.get(label, 0) + 1
                        break
                else:
                    skipped["tipo desconhecido"] = skipped.get("tipo desconhecido", 0) + 1
                    print(f"  [skip] tipo desconhecido: {name}")
                continue
            mp = (prices.get(prod["productId"]) or {}).get("marketPrice")
            if not mp:
                no_price += 1
                print(f"  [skip] sem marketPrice hoje: {name}")
                continue
            band = SANITY_BANDS_USD_ONEPIECE.get(ptype)
            if band and not (band[0] <= float(mp) <= band[1]):
                out_of_band += 1
                print(f"  [skip] US${mp} fora da banda {ptype} {band}: {name}")
                continue
            sku = build_sku(prod, group, code, float(mp))
            if sku:
                skus.append(sku)
        time.sleep(0.25)

    print(f"\nSKUs gerados: {len(skus)}")
    print(f"Pulados: {skipped} · sem preço: {no_price} · fora da banda: {out_of_band}")
    ids = [s["id"] for s in skus]
    assert len(ids) == len(set(ids)), "ids duplicados!"

    if args.dry_run:
        return 0
    body = "\n".join(sku_to_yaml(s) for s in skus)
    Path(args.output).write_text(HEADER + body + "\n", encoding="utf-8")
    print(f"Escrito: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
