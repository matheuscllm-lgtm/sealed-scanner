#!/usr/bin/env python3
"""
olx_adapter.py — adapter para OLX Brasil (busca de selados Pokémon).

OLX expõe os anúncios no JSON __NEXT_DATA__ embutido no HTML da página de
busca, parseável direto. Para cada SKU do registry faz uma busca em
olx.com.br/brasil?q=... e devolve as listagens; o matcher do scanner
depois decide o que casa.

ATENÇÃO (2026-05-29): a OLX passou a proteger o site com Cloudflare WAF.
De IP residencial comum a busca volta HTTP 403 "you have been blocked"
(reproduzido com urllib E com patchright headless/headful). NÃO é o
challenge "Just a moment"/Turnstile (que a Liga atravessa) — é block
terminal por requisição, sem captcha pra resolver. Quando detectado, o
adapter levanta `SourceBlockedError` e o scanner trata como condição
externa não-fatal (Amazon e Liga seguem). Acesso real exige outra rede/IP
ou proxy residencial (decisão de capital do operador).

CONTEXTO E AVISOS:
- OLX é marketplace de classificados (vendedores individuais predominantes).
  Preços são mais voláteis que retailers — negociação, urgência, scams. Use
  o flag professionalAd / location como sinais adicionais.
- Anúncios são locais: vendedor pode exigir encontro presencial. Para
  arbitragem nacional, filtrar por sellers com envio (não implementado).
- Maioria dos boxes na OLX vem em PT-BR (edição brasileira da COPAG). O
  matcher filtra via exclude_terms ("portugues"/"portuguesa" + nomes de
  sets em PT). Em geral só passa quem explicita "Inglês" no título.
"""
from __future__ import annotations

import gzip
import json
import time
import urllib.error
import urllib.parse
import urllib.request

from lib.errors import SourceBlockedError

BASE = "https://www.olx.com.br/brasil?q="
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

# Tokens da página de BLOCK do Cloudflare ("you have been blocked" / WAF
# managed-rule / IP reputation). Distinto do challenge "Just a moment"/Turnstile,
# que auto-resolve — este é terminal por requisição, não há captcha pra clicar.
# Reproduzido em 2026-05-29: urllib e patchright (headless/headful) batem nisso.
_BLOCK_TOKENS = (
    "you have been blocked",
    "attention required",
    "sorry, you have been blocked",
    "cf-error-details",
)
_BLOCK_HINT = (
    "OLX está com block WAF do Cloudflare neste IP (não é Turnstile, não há "
    "captcha pra resolver). Opções: rodar de outra rede/IP, ou rotear via "
    "proxy residencial (ScraperAPI/Firecrawl) — decisão de capital do operador. "
    "Amazon e Liga seguem operacionais."
)


def _decode_body(raw: bytes, encoding: str | None) -> str:
    """Decodifica o corpo, descomprimindo gzip se necessário (a página de
    block do CF costuma vir gzipada mesmo em resposta de erro)."""
    if encoding and "gzip" in encoding.lower():
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
    return raw.decode("utf-8", errors="replace")


def _is_block_page(body: str) -> bool:
    low = body.lower()
    return any(tok in low for tok in _BLOCK_TOKENS)


def _fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = _decode_body(r.read(), r.headers.get("Content-Encoding"))
    except urllib.error.HTTPError as exc:
        # 403/429/503 com corpo de block do Cloudflare = bloqueio externo, não
        # erro transitório. Lê o corpo do erro (gzipado) e classifica.
        try:
            err_body = _decode_body(exc.read(), exc.headers.get("Content-Encoding"))
        except Exception:
            err_body = ""
        if exc.code in (403, 429, 503) and _is_block_page(err_body):
            raise SourceBlockedError(
                "olx", f"Cloudflare WAF block (HTTP {exc.code})", _BLOCK_HINT
            ) from exc
        raise  # outro HTTP error — deixa o caller logar como aviso transitório
    # 200 OK mas corpo é página de block (CF pode servir block com 200).
    if _is_block_page(body):
        raise SourceBlockedError("olx", "Cloudflare WAF block (HTTP 200)", _BLOCK_HINT)
    return body


def _price_to_float(text: str) -> float | None:
    """'R$ 3.800' -> 3800.0; 'R$ 1.412,58' -> 1412.58 (BR: ponto = milhar)."""
    cleaned = "".join(c for c in str(text) if c.isdigit() or c in ".,")
    if not cleaned:
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_search_results(html: str) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    script = soup.find("script", {"id": "__NEXT_DATA__"})
    if not script:
        return []
    try:
        data = json.loads(script.get_text())
    except json.JSONDecodeError:
        return []
    ads = data.get("props", {}).get("pageProps", {}).get("ads", [])
    out: list[dict] = []
    for ad in ads:
        if not isinstance(ad, dict):
            continue
        title = ad.get("subject") or ad.get("title") or ""
        if not title:
            continue
        price = _price_to_float(ad.get("priceValue") or ad.get("price") or "")
        if price is None:
            continue
        out.append({
            "title": title,
            "price_brl": price,
            "seller": "OLX " + ("(profissional)" if ad.get("professionalAd") else "(individual)"),
            "url": ad.get("url", ""),
            "list_id": ad.get("listId", ""),
            "location": ad.get("location", ""),
        })
    return out


# OLX tem inventário esparso por SKU — buscas por nome de set específico
# voltam quase vazias. Por isso usamos queries por TIPO de produto (mais
# amplas) e deixamos o matcher do scanner filtrar. Cada tipo pode ter MAIS
# de uma query (ex: pack tem termo PT "avulso" muito comum).
TYPE_TO_QUERY = {
    "Booster Box":        ["booster box pokemon ingles"],
    "Elite Trainer Box":  ["elite trainer box pokemon ingles"],
    "Booster Bundle":     ["booster bundle pokemon ingles"],
    "Collection Box":     ["collection box pokemon ingles"],
    "Premium Collection": ["premium collection pokemon ingles"],
    "Tin":                ["tin pokemon ingles"],
    "Sleeved Booster":    ["booster pack pokemon ingles", "booster avulso pokemon"],
    "Blister Pack":       ["blister pokemon ingles"],
}


def _derive_queries(registry: list[dict]) -> list[str]:
    """Queries únicas por product_type presente no registry."""
    queries: set[str] = set()
    for sku in registry:
        if sku.get("language", "").upper() != "EN":
            continue
        qs = TYPE_TO_QUERY.get(sku.get("product_type", ""), [])
        for q in qs:
            queries.add(q)
    return sorted(queries)


def fetch_listings(config: dict, registry: list[dict]) -> list[dict]:
    if not registry:
        raise ValueError("olx_adapter requer o registry para gerar queries.")
    olx_cfg = config.get("olx", {})
    delay = olx_cfg.get("delay_seconds", 1.5)
    limit_per_query = olx_cfg.get("results_per_query", 50)

    queries = _derive_queries(registry)
    if not queries:
        raise ValueError("nenhuma query OLX gerada (registry vazio ou sem product_types conhecidos).")

    all_listings: list[dict] = []
    seen_ids: set[str] = set()
    for i, query in enumerate(queries):
        url = BASE + urllib.parse.quote_plus(query)
        try:
            html = _fetch(url)
        except SourceBlockedError:
            # Block é por IP/WAF — vale pra todas as queries. Não martele 5×;
            # propaga pro scanner tratar como condição externa não-fatal.
            raise
        except Exception as exc:
            print(f"  [aviso] busca OLX falhou para '{query}': {exc}")
            continue
        results = parse_search_results(html)
        slug = query.split()[0]
        kept = 0
        for r in results[:limit_per_query]:
            lid = str(r.get("list_id", ""))
            if lid and lid in seen_ids:
                continue
            if lid:
                seen_ids.add(lid)
            entry = dict(r)
            entry["id"] = f"OLX-{slug}-{kept + 1}"
            entry["source"] = "olx"
            entry["query"] = query
            all_listings.append(entry)
            kept += 1
        if i < len(queries) - 1:
            time.sleep(delay)
    return all_listings
