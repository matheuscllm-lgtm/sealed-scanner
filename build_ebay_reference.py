#!/usr/bin/env python3
"""build_ebay_reference.py — referência do LADO DE VENDA: menor anúncio ATIVO
no eBay US por SKU do registry.

O que este arquivo gera (data/ebay_reference.json, GITIGNORED):
  Para cada SKU selado, o MENOR anúncio ativo plausível no eBay US (Buy It Now,
  item nos EUA, preço do item SEM frete) — o mercado onde o operador de fato
  vende (via Probstein, consignação no eBay US).

⚠️ HONESTIDADE (regras duras — não relaxar):
  - Isto é PEDIDA (anúncio ativo), NÃO venda realizada. A API de vendidos do
    eBay (Marketplace Insights) é restrita; o rótulo da coluna na entrega diz
    exatamente isso.
  - A referência eBay é INFORMATIVA: NUNCA entra na classificação
    GREEN/YELLOW/RED (que segue 100% TCGplayer) nem na margem oficial.
  - Nunca inventar preço/URL: SKU sem anúncio plausível sai com status
    explícito, jamais com número fabricado.
  - RUN DEGRADADO (sem EBAY_CLIENT_ID/SECRET): avisa alto, retorna 0 e NÃO
    TOCA no arquivo anterior (espelho do comportamento do
    ebay-arbitrage-scanner, PR #19 de lá: nunca sobrescrever a última
    referência real com um vazio "verde").

Match por BUSCA (query de texto) — título arbitrário é a maior fonte de erro
(lição da frota), então o gate de título é estrito, reutilizando os PRÓPRIOS
termos do registry (set_terms + type_terms + requires_terms + exclude_terms,
com o mesmo normalize/contains_term do matcher) MAIS os guards específicos de
eBay/selado: não-EN, graded, aberto/usado em EN, lote/case/multi-unidade, e
anúncio-lixo (< 50% da referência TCG = contado, nunca vencedor).

Uso:
    python build_ebay_reference.py                     # Pokémon (default)
    python build_ebay_reference.py --game onepiece     # perfil One Piece
    python build_ebay_reference.py --limit-skus 5      # smoke curto

Custo: 1 chamada Browse API por SKU (205 SKUs ≪ 5.000/dia do free tier).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import sealed_arbitrage_scanner as S
from lib.ebay_client import REQUEST_DELAY_S, EbayClient
from lib.env import load_dotenv_if_present

# ── Guards de título (precisão > cobertura) ────────────────────────────────
# Marcadores de graded/idioma (substring no título minúsculo, paridade com
# outlook/ebay_availability.py da frota). Graded importa p/ packs vintage
# ("WOTC pack PSA 10") e combos ("ETB + PSA 10 card").
GRADED_MARKERS = ("psa", "bgs", "cgc", "sgc", "graded", "ace 10")
NON_EN_MARKERS = ("japanese", "japan", "jpn", "korean", "chinese", "german",
                  "italian", "french", "spanish", "portuguese")
# Aberto/usado em EN (análogo eBay do _USED_TOKENS PT do scanner): anúncio de
# caixa vazia/aberta nunca é referência de venda de produto selado.
USED_TOKENS_EN = (
    "opened", "empty", "no packs", "no cards", "no boosters",
    "box only", "resealed", "damaged",
)
# Produto DIGITAL (code cards do Pokémon TCG Online/Live etc.): observado AO
# VIVO na validação de 2026-08-03 — "Surging Sparks Elite Trainer Box Code
# Card E-Delivery" a US$0,99 passa o gate de set+tipo e, em SKU barato ou sem
# referência TCG, escaparia do junk-ratio. Nenhum selado físico usa estes
# termos no nome → substring no título minúsculo é seguro.
DIGITAL_TOKENS = (
    "code card", "code cards", "online code", "digital", "e-delivery",
    "email delivery", "ptcgo", "ptcgl", "tcg live", "tcg online",
    "no physical", "in-game",
)
# Lote/case/multi-unidade: "Lot of 4", "2x", "x2", "Booster Box Case",
# "Set of 6", "Bundle of 3". NB: "bundle" sozinho é tipo de produto legítimo
# (Booster Bundle) — só "bundle of" conta. Aplicado no título minúsculo CRU.
LOT_CASE_RE = re.compile(
    r"\b\d+\s*x\b|\bx\s*\d+\b|\blot\b|\bcase\b|\bset of\b|\bbundle of\b|\blote\b"
)
# Variante para SKUs cuja PRÓPRIA identidade é um case (product_type termina
# em "Case" — operador 2026-08-17, escopo OP ampliado): "case" deixa de ser
# veto; o resto (lot, Nx, set of, bundle of) segue vetando multi-unidade.
LOT_NOCASE_RE = re.compile(
    r"\b\d+\s*x\b|\bx\s*\d+\b|\blot\b|\bset of\b|\bbundle of\b|\blote\b"
)


def _lot_re_for(sku) -> re.Pattern:
    ptype = (getattr(sku, "product_type", "") or "")
    return LOT_NOCASE_RE if ptype.endswith("Case") else LOT_CASE_RE
# Anúncio abaixo de SUSPECT_RATIO × referência TCG = lixo provável (caixa
# errada, foto, pré-venda suspeita): contado, NUNCA vencedor.
SUSPECT_RATIO = 0.5


def _is_ebay_listing_url(url: str) -> bool:
    """True só para URL de anúncio no próprio eBay (host *.ebay.com).

    A Browse API devolve também itens da rede eBay fora do marketplace core —
    observado ao vivo (scan 2026-08-11): goldin.co (casa de leilões da eBay)
    vazou como "menor anúncio" em 3 SKUs, com URL sem item e preço de lance de
    leilão, que não é pedida Buy It Now comparável. Sem URL auditável no
    eBay US, o anúncio não serve de referência de venda.
    """
    try:
        host = (urlparse(url).netloc or "").lower()
    except ValueError:
        return False
    return host == "ebay.com" or host.endswith(".ebay.com")

_ENGLISH_SUFFIX_RE = re.compile(r"\s*\((?:english|ingles|inglês)\)\s*$", re.IGNORECASE)


def sku_query(sku, game_word: str) -> str:
    """Query de busca do SKU: '<jogo> <nome canônico sem "(English)">'."""
    name = _ENGLISH_SUFFIX_RE.sub("", sku.name or sku.id)
    return " ".join(f"{game_word} {name}".split())


def title_passes_gate(title: str, sku) -> bool:
    """Gate de título estrito: o anúncio precisa provar que é ESTE SKU selado.

    Reusa os termos do registry (mesma semântica whole-word do matcher) e
    adiciona os guards de eBay: não-EN, graded, aberto/usado EN, lote/case.
    """
    if not title:
        return False
    low = title.lower()
    if any(m in low for m in NON_EN_MARKERS):
        return False
    if any(m in low for m in GRADED_MARKERS):
        return False
    if any(m in low for m in DIGITAL_TOKENS):
        return False
    if _lot_re_for(sku).search(low):
        return False
    norm = S.normalize(title)
    if any(S.contains_term(norm, t) for t in USED_TOKENS_EN):
        return False
    if not any(S.contains_term(norm, t) for t in sku.set_terms):
        return False
    if not any(S.contains_term(norm, t) for t in sku.type_terms):
        return False
    if sku.requires_terms and not all(S.contains_term(norm, t) for t in sku.requires_terms):
        return False
    if any(S.contains_term(norm, t) for t in sku.exclude_terms):
        return False
    return True


def select_lowest(sku, items: list[dict], ref_usd: float | None) -> dict:
    """Menor anúncio plausível dentre os itemSummaries. Função pura (testável).

    Retorna a entrada do JSON: {'usd','url','status':'ok','junk_skipped'} ou
    {'status': '...'} explícito — nunca silencioso, nunca preço inventado.
    """
    best: dict | None = None
    junk = 0
    for it in items:
        title = it.get("title") or ""
        if not title_passes_gate(title, sku):
            continue
        url = it.get("itemWebUrl") or ""
        if not _is_ebay_listing_url(url):
            continue
        price = it.get("price") or {}
        if (price.get("currency") or "USD") != "USD":
            continue
        try:
            usd = float(price.get("value"))
        except (TypeError, ValueError):
            continue
        if usd <= 0:
            continue
        if ref_usd and ref_usd > 0 and usd < SUSPECT_RATIO * ref_usd:
            junk += 1
            continue
        if best is None or usd < best["usd"]:
            best = {"usd": usd, "url": url, "status": "ok"}
    if best:
        best["junk_skipped"] = junk
        return best
    if junk:
        return {"status": f"só anúncios-lixo ({junk} < 50% da ref)"}
    return {"status": "sem anúncio plausível"}


def build_reference(skus: list, us_prices: dict, client, game_word: str,
                    category_ids: str | None = None, limit: int = 50,
                    limit_skus: int = 0) -> tuple[dict, dict]:
    """Roda a busca SKU a SKU. Retorna (entries, counts). Cliente injetável."""
    entries: dict[str, dict] = {}
    counts = {"ok": 0, "sem_anuncio": 0, "so_lixo": 0, "erro": 0}
    todo = skus[:limit_skus] if limit_skus else skus
    for i, sku in enumerate(todo, start=1):
        query = sku_query(sku, game_word)
        ref_usd = us_prices.get(sku.id)
        # Piso da BUSCA = o mesmo piso do junk-guard (50% da ref TCG): a busca
        # ordena por preço e devolve só `limit` itens — em SKU popular a janela
        # saturava de lixo sub-US$20 (sleeves, code cards) antes de alcançar o
        # produto real (observado ao vivo em 2026-08-03: ssp-booster-box "sem
        # anúncio plausível" com boxes reais a US$180+ fora da janela). Tudo
        # abaixo do piso já seria descartado pelo guard de qualquer forma.
        min_price = round(SUSPECT_RATIO * ref_usd, 2) if ref_usd else None
        try:
            items = client.search(query, category_ids=category_ids, limit=limit,
                                  min_price=min_price)
            entry = select_lowest(sku, items, ref_usd)
        except Exception as exc:  # rede/HTTP após retries — status explícito
            entry = {"status": f"erro: {type(exc).__name__}: {exc}"}
        entry["query"] = query
        entries[sku.id] = entry
        status = entry["status"]
        if status == "ok":
            counts["ok"] += 1
            print(f"  [{i}/{len(todo)}] {sku.id}: US$ {entry['usd']:.2f}"
                  + (f" (lixo pulado: {entry['junk_skipped']})" if entry.get("junk_skipped") else ""))
        else:
            key = ("erro" if status.startswith("erro") else
                   "so_lixo" if status.startswith("só anúncios-lixo") else "sem_anuncio")
            counts[key] += 1
            print(f"  [{i}/{len(todo)}] {sku.id}: {status}")
    return entries, counts


def write_reference(path: Path, entries: dict, counts: dict) -> None:
    """Escrita atômica (tmp + os.replace) — nunca deixa JSON pela metade."""
    payload = {
        "_comment": (
            "Gerado por build_ebay_reference.py (eBay Browse API). Menor ANÚNCIO "
            "ATIVO plausível por SKU no eBay US (Buy It Now, item nos EUA). É "
            "PEDIDA, NÃO venda realizada; preço do item SEM frete. Referência "
            "INFORMATIVA do lado de venda — NUNCA entra na classificação "
            "GREEN/YELLOW/RED nem na margem oficial (que seguem TCGplayer). "
            "NÃO editar à mão."
        ),
        "reference": "eBay US menor anúncio ativo (Browse API)",
        "marketplace": "EBAY_US",
        "currency": "USD",
        "captured_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": counts,
        "entries": entries,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


# Perfis por jogo: caminhos default de cada --game. Pokémon = arquivos atuais.
GAME_PROFILES = {
    "pokemon": {
        "registry": "sku_registry.yaml",
        "us_reference": "data/us_reference.json",
        "output": "data/ebay_reference.json",
        "game_word": "pokemon",
    },
    "onepiece": {
        "registry": "sku_registry_onepiece.yaml",
        "us_reference": "data/us_reference_onepiece.json",
        "output": "data/ebay_reference_onepiece.json",
        "game_word": "one piece tcg",
    },
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Referência do lado de VENDA: menor anúncio ativo no eBay US por SKU."
    )
    ap.add_argument("--game", default="pokemon", choices=sorted(GAME_PROFILES),
                    help="perfil de jogo (define registry/refs/output default)")
    ap.add_argument("--registry", default=None, help="caminho do sku_registry (default: do --game)")
    ap.add_argument("--output", default=None, help="JSON de saída (default: do --game)")
    ap.add_argument("--us-reference", default=None,
                    help="us_reference.json p/ o guard de anúncio-lixo (default: do --game)")
    ap.add_argument("--game-word", default=None,
                    help="prefixo da query de busca (default: do --game)")
    ap.add_argument("--category-ids", default="",
                    help="IDs de categoria eBay (default: SEM filtro — não chutamos ID de selados)")
    ap.add_argument("--limit-skus", type=int, default=0, help="só os N primeiros SKUs (smoke)")
    ap.add_argument("--force", action="store_true",
                    help="com --limit-skus, sobrescreve a referência principal "
                         "(default: smoke sai em *.smoke.json e preserva a completa)")
    ap.add_argument("--limit", type=int, default=50, help="anúncios por busca (default 50)")
    ap.add_argument("--delay", type=float, default=None,
                    help=f"segundos entre chamadas (default {REQUEST_DELAY_S})")
    args = ap.parse_args(argv)

    profile = GAME_PROFILES[args.game]
    registry_path = Path(args.registry) if args.registry else SCRIPT_DIR / profile["registry"]
    output_path = Path(args.output) if args.output else SCRIPT_DIR / profile["output"]
    us_ref_path = Path(args.us_reference) if args.us_reference else SCRIPT_DIR / profile["us_reference"]
    game_word = args.game_word if args.game_word is not None else profile["game_word"]

    load_dotenv_if_present()
    client = EbayClient()
    if not client.configured:
        print("=" * 64)
        print("  AVISO: EBAY_CLIENT_ID / EBAY_CLIENT_SECRET não configurados.")
        print("  Referência eBay NÃO gerada; o arquivo anterior (se existir)")
        print(f"  foi PRESERVADO intacto: {output_path}")
        print("  Setup grátis (~5 min): ver SETUP-VALIDACAO.md §A.")
        print("=" * 64)
        return 0

    if args.delay is not None:
        import lib.ebay_client as _ec
        _ec.REQUEST_DELAY_S = args.delay  # override de cadência p/ debug

    registry_data = S.load_yaml(registry_path, registry_path.name)
    skus = S.build_registry(registry_data)
    us_prices: dict = {}
    if us_ref_path.exists():
        us_prices = (S.load_json(us_ref_path, us_ref_path.name) or {}).get("prices", {})
    else:
        print(f"  [aviso] {us_ref_path} ausente — guard de anúncio-lixo DESLIGADO "
              "(rode build_us_reference.py antes p/ ligar o guard).")

    print(f"  [ebay] jogo={args.game} · SKUs={len(skus)} · query='{game_word} …' · "
          f"categoria={'(sem filtro)' if not args.category_ids else args.category_ids}")
    entries, counts = build_reference(
        skus, us_prices, client, game_word,
        category_ids=args.category_ids or None,
        limit=args.limit, limit_skus=args.limit_skus,
    )

    total = sum(counts.values())
    if total and counts["erro"] > total / 2:
        print("=" * 64)
        print(f"  ERRO: {counts['erro']}/{total} SKUs falharam (rede/API instável).")
        print(f"  Referência NÃO gravada; arquivo anterior preservado: {output_path}")
        print("=" * 64)
        return 1

    # --limit-skus é SMOKE: N entradas jamais clobram a referência COMPLETA
    # anterior (espírito da regra inviolável nº 8) — sai em *.smoke.json ao
    # lado; --force sobrescreve de propósito. Review do PR #75.
    target_path = output_path
    if args.limit_skus and output_path.exists() and not args.force:
        target_path = output_path.with_suffix(".smoke.json")
        print(f"  [smoke] --limit-skus {args.limit_skus}: referência completa "
              f"preservada em {output_path.name}; smoke vai em "
              f"{target_path.name} (use --force p/ sobrescrever).")
    write_reference(target_path, entries, counts)
    print("=" * 64)
    print("  REFERÊNCIA eBay (lado de VENDA) gravada")
    print(f"  Arquivo : {target_path}")
    print(f"  SKUs    : {counts['ok']} ok · {counts['sem_anuncio']} sem anúncio · "
          f"{counts['so_lixo']} só lixo · {counts['erro']} erro")
    print("  Lembrete: é PEDIDA (anúncio ativo), não venda realizada — coluna")
    print("  informativa; a classificação continua 100% TCGplayer.")
    print("=" * 64)
    return 0


if __name__ == "__main__":
    from lib.console import harden_stdout
    harden_stdout()
    sys.exit(main())
