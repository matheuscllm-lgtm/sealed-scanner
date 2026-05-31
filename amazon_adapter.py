#!/usr/bin/env python3
"""
amazon_adapter.py — adapter para Amazon Brasil (busca de selados Pokémon).

Amazon BR é acessível deste ambiente (sem CloudFlare nas páginas de busca,
sem auth). Padrão: para cada SKU do registry, faz uma busca textual no
amazon.com.br/s?k=... e devolve as listagens encontradas — o matcher do
scanner depois decide o que casa com cada SKU.

CUIDADO: Amazon BR pode mudar markup ou aplicar anti-bot se a frequência
subir muito. Se a contagem de resultados despencar pra zero, conferir se
[data-component-type='s-search-result'] e span.a-price>span.a-offscreen
ainda valem.

NOTA: anúncios da Amazon BR para selado tendem a vir caros — sellers de
marketplace inflacionam preço de produto importado. Isso é dado REAL, não
problema do scanner. A Liga (quando o adapter dela rodar) costuma ser mais
agressiva em preço.
"""
from __future__ import annotations

import re
import time
import urllib.parse
import urllib.request

BASE = "https://www.amazon.com.br/s?k="
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"


def _fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _price_to_float(text: str) -> float | None:
    """'R$ 1.412,58' -> 1412.58 (BR: ponto = milhar, vírgula = decimal)."""
    cleaned = "".join(c for c in text if c.isdigit() or c in ".,")
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
    out: list[dict] = []
    for result in soup.select('div[data-component-type="s-search-result"]'):
        title_el = result.select_one("h2")
        title = title_el.get_text(strip=True) if title_el else ""
        if not title:
            continue
        price_el = result.select_one("span.a-price > span.a-offscreen")
        price = _price_to_float(price_el.get_text(strip=True)) if price_el else None
        if price is None:
            continue
        link_el = result.select_one("a.a-link-normal[href*='/dp/']") or result.select_one("h2 a")
        href = link_el.get("href", "") if link_el else ""
        if href.startswith("/"):
            href = "https://www.amazon.com.br" + href
        m = re.search(r"/dp/([A-Z0-9]{10})", href)
        asin = m.group(1) if m else ""
        out.append({
            "title": title,
            "price_brl": price,
            "seller": "Amazon.com.br marketplace",
            "url": href,
            "asin": asin,
        })
    return out


def _derive_query(sku: dict) -> str:
    """Constrói uma query Amazon a partir do SKU. SKU pode definir 'amazon_query' p/ override."""
    set_name = sku.get("set", "").replace("&", " ")
    parts = [set_name, sku.get("product_type", "")]
    if sku.get("language", "").upper() == "EN":
        parts.append("ingles")
    return " ".join(p.strip() for p in parts if p.strip())


def fetch_listings(config: dict, registry: list[dict]) -> list[dict]:
    """Busca cada SKU do registry no Amazon BR. Devolve todas as listagens encontradas."""
    if not registry:
        raise ValueError("amazon_adapter requer o registry para gerar as queries de busca.")
    amz = config.get("amazon", {})
    delay = amz.get("delay_seconds", 1.5)
    limit_per_sku = amz.get("results_per_sku", 6)

    all_listings: list[dict] = []
    seen_asins: set[str] = set()
    for i, sku in enumerate(registry):
        query = sku.get("amazon_query") or _derive_query(sku)
        url = BASE + urllib.parse.quote_plus(query)
        try:
            html = _fetch(url)
        except Exception as exc:
            print(f"  [aviso] busca Amazon falhou para {sku.get('id')}: {exc}")
            continue
        results = parse_search_results(html)
        kept = 0
        for r in results[:limit_per_sku]:
            asin = r.get("asin") or ""
            if asin and asin in seen_asins:
                continue
            if asin:
                seen_asins.add(asin)
            entry = dict(r)
            entry["id"] = f"AMZ-{sku['id']}-{kept + 1}"
            entry["source"] = "amazon"
            all_listings.append(entry)
            kept += 1
        if i < len(registry) - 1:
            time.sleep(delay)
    return all_listings
