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

import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request

from lib.errors import SourceBlockedError
from lib.firecrawl import FIRECRAWL_V1, extract_raw_html, post_scrape  # transporte /scrape compartilhado (Issue #13)

BASE = "https://www.amazon.com.br/s?k="
# Fallback PRIMÁRIO (2026-06-10): Chrome REAL via patchright (lib.browser),
# mesma infra da Liga — $0, roda do PC do operador. Atravessa o 503 anti-bot
# que o urllib direto leva (probe ao vivo 2026-06-10: 13 resultados, 0 block).
# Abre 1× por run (lazy: só se algum SKU precisar) e reusa a sessão.
#
# Fallback LEGADO opt-in: Firecrawl (render + proxy residencial) — pago
# (~51 créditos/run sob block pesado). Mantido só pra rodar da nuvem (sem
# janela). Usa a rota /v1 (papel de FALLBACK), não a classe primária do
# lib.firecrawl (que OLX/ML usam como transporte principal).
FIRECRAWL_ENDPOINT = FIRECRAWL_V1
_BROWSER_PROFILE = None  # default: ~/.pw_profile_amazon_sealed (ver _BrowserSession)
# Pool de User-Agents pra não bater na Amazon sempre com a mesma assinatura
# (reduz a chance de anti-bot disparar por padrão de request).
UAS = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.4 Safari/605.1.15",
)
UA = UAS[0]  # default determinístico (compat: alguns testes/usos referenciam UA)

# Códigos HTTP transitórios da Amazon (anti-bot 503/429 + 5xx de servidor).
# Distinto de 4xx "de verdade" (404/400), que NÃO devem ser retentados.
_RETRYABLE = {500, 502, 503, 504, 429}


def _fetch(url: str, timeout: int = 30) -> str:
    req = urllib.request.Request(url, headers={
        "User-Agent": random.choice(UAS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def _fetch_retry(url: str, attempts: int = 3, base_sleep: float = 2.0) -> str:
    """`_fetch` com retry + backoff p/ 503/429 anti-bot intermitente da Amazon.

    A Amazon BR serve 503 de forma intermitente (~1 em 3 requests medido em
    2026-06-05); um único 503 NÃO deve descartar o SKU. Retenta só códigos
    transitórios (`_RETRYABLE`); 404/400 etc. propagam na hora. Backoff
    linear com jitter: ~2s, ~4s, ~6s.
    """
    last: Exception | None = None
    for i in range(attempts):
        try:
            return _fetch(url)
        except urllib.error.HTTPError as exc:
            last = exc
            if exc.code not in _RETRYABLE:
                raise
            if i < attempts - 1:
                time.sleep(base_sleep * (i + 1) + random.uniform(0, 0.75))
        except urllib.error.URLError as exc:
            # timeout / conexão resetada — também transitório, vale retentar.
            last = exc
            if i < attempts - 1:
                time.sleep(base_sleep * (i + 1) + random.uniform(0, 0.75))
    assert last is not None  # só chega aqui se todas as tentativas falharam
    raise last


def _firecrawl_key() -> str | None:
    return os.environ.get("FIRECRAWL_API_KEY")


def _fetch_firecrawl(url: str, proxy: str = "stealth", country: str = "BR",
                     timeout: int = 90) -> str:
    """Busca via Firecrawl (render + proxy residencial) — fallback quando o
    urllib direto leva 503 anti-bot persistente.

    Retorna o `rawHtml` (markup completo da SERP da Amazon), que
    `parse_search_results` consome SEM mudança — provado em 2026-06-05: o
    Firecrawl atravessa o block e o parser extrai os mesmos anúncios. Requer
    FIRECRAWL_API_KEY no ambiente. Sem dependência nova: REST direto via urllib.
    """
    key = _firecrawl_key()
    if not key:
        raise RuntimeError("FIRECRAWL_API_KEY ausente — fallback Firecrawl indisponível.")
    # Transporte compartilhado (lib.firecrawl): /v1, single-shot (retries=0 — o
    # retry da Amazon vive na camada urllib, antes do fallback), sem waitFor.
    # default_success=False = exige `success` truthy explícito (semântica /v1).
    envelope = post_scrape(
        url, api_key=key, endpoint=FIRECRAWL_ENDPOINT, proxy=proxy,
        country=country, wait_ms=None, timeout=timeout, retries=0,
    )
    return extract_raw_html(envelope, default_success=False)


# Sinais de página anti-bot da Amazon BR servida AO BROWSER (raro: a SERP em
# browser real costuma carregar limpa; isto pega captcha/robot-check residual).
_AMZ_BLOCK_TOKENS = ("robot check", "captcha", "algo deu errado", "/errors/validatecaptcha")


class _BrowserSession:
    """Sessão Chrome real LAZY pro fallback ($0). Abre no 1º uso, reusa entre
    SKUs, fecha no fim do run (fetch_listings faz o close no finally)."""

    def __init__(self, headless: bool = False, profile_dir: str | None = None):
        from pathlib import Path
        self._headless = headless
        self._profile = profile_dir or str(Path.home() / ".pw_profile_amazon_sealed")
        self._chrome = None

    def get_html(self, url: str) -> str:
        if self._chrome is None:
            from lib.browser import LocalChromeFetcher
            self._chrome = LocalChromeFetcher(self._profile, headless=self._headless)
        html = self._chrome.get(
            url, wait_for_selector='div[data-component-type="s-search-result"]',
            cf_wait_s=15)
        low = html.lower()
        if any(tok in low for tok in _AMZ_BLOCK_TOKENS):
            raise SourceBlockedError(
                "amazon", "anti-bot da Amazon mesmo via browser real",
                "Captcha/robot-check na SERP em Chrome real — raro; tente de novo "
                "mais tarde ou resolva o captcha na janela.")
        return html

    def close(self) -> None:
        if self._chrome is not None:
            self._chrome.close()
            self._chrome = None


def _fetch_retry_browser(browser: "_BrowserSession", url: str,
                         attempts: int = 2, base_sleep: float = 2.0) -> str:
    """Browser fallback com 1 retentativa (página em branco/transitório de
    rede). Block real (SourceBlockedError) propaga na hora — retentar captcha
    não resolve sozinho."""
    last: Exception | None = None
    for i in range(attempts):
        try:
            return browser.get_html(url)
        except SourceBlockedError:
            raise
        except Exception as exc:
            last = exc
            if i < attempts - 1:
                time.sleep(base_sleep + random.uniform(0, 0.75))
    assert last is not None
    raise last


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
    # Fallback BROWSER ($0, default): Chrome real, abre lazy no 1º SKU que o
    # urllib+retry não resolver. Fallback FIRECRAWL é LEGADO opt-in (pago) —
    # default DESLIGADO desde 2026-06-10; útil só rodando da nuvem.
    fallback_browser = amz.get("fallback_browser", True)
    fallback_firecrawl = amz.get("fallback_firecrawl", False)
    firecrawl_proxy = amz.get("firecrawl_proxy", "stealth")
    fc_available = bool(fallback_firecrawl and _firecrawl_key())
    browser = _BrowserSession(
        headless=bool(amz.get("browser_headless", False)),
        profile_dir=amz.get("browser_profile_dir"),
    ) if fallback_browser else None

    all_listings: list[dict] = []
    seen_asins: set[str] = set()
    fails = 0       # SKUs onde TODAS as rotas falharam (sinal de bloqueio real)
    br_used = 0     # quantos SKUs caíram no browser ($0)
    br_recovered = 0
    fc_used = 0     # quantos SKUs caíram no Firecrawl (créditos)
    fc_recovered = 0
    try:
        for i, sku in enumerate(registry):
            query = sku.get("amazon_query") or _derive_query(sku)
            url = BASE + urllib.parse.quote_plus(query)
            html: str | None = None
            via = "urllib"
            try:
                html = _fetch_retry(url)
            except Exception as exc:
                # urllib esgotou (provável 503 anti-bot persistente).
                # Escada: browser ($0) → firecrawl (opt-in pago) → FALHOU.
                if browser is not None:
                    via = "browser"
                    br_used += 1
                    try:
                        html = _fetch_retry_browser(browser, url)
                        br_recovered += 1
                    except Exception as br_exc:
                        exc = br_exc
                        html = None
                if html is None and fc_available:
                    via = "firecrawl"
                    fc_used += 1
                    try:
                        html = _fetch_firecrawl(url, proxy=firecrawl_proxy)
                        fc_recovered += 1
                    except Exception as fc_exc:
                        exc = fc_exc
                        html = None
                if html is None:
                    via = "FALHOU"
                    print(f"  [aviso] busca Amazon falhou p/ {sku.get('id')}: {exc}", flush=True)
            kept = 0
            if html is None:
                fails += 1
            else:
                results = parse_search_results(html)
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
            # progresso AO VIVO por SKU (flush). via = urllib | browser |
            # firecrawl | FALHOU.
            print(f"  [amazon] {i + 1:3}/{len(registry)} {str(sku.get('id'))[:22]:22} "
                  f"via={via:9} +{kept} anuncios={len(all_listings):3} "
                  f"br={br_used}(recup={br_recovered}) "
                  f"fc={fc_used}(recup={fc_recovered}) fails={fails}", flush=True)
            if i < len(registry) - 1:
                # jitter no delay pra não martelar a Amazon em cadência fixa.
                time.sleep(delay + random.uniform(0, 0.75))
    finally:
        if browser is not None:
            browser.close()

    if br_used:
        print(f"  [amazon] browser fallback: {br_recovered}/{br_used} SKUs "
              f"recuperados via Chrome real ($0).")
    if fc_used:
        print(f"  [amazon] Firecrawl fallback: {fc_recovered}/{fc_used} SKUs "
              f"recuperados via render/proxy (créditos consumidos).")

    # Bloqueio honesto: se a maioria das buscas falhou em AMBAS as rotas
    # (urllib+retry E Firecrawl) e nada foi coletado, é block real — não
    # "0 anúncios". Levanta SourceBlockedError pro orquestrador marcar BLOQUEADA
    # (igual Liga/OLX), em vez de mascarar como status=ok n_listings=0.
    total = len(registry)
    if fails and not all_listings and fails / max(1, total) >= 0.6:
        rotas = ["urllib"]
        if fallback_browser:
            rotas.append("browser")
        if fc_available:
            rotas.append("Firecrawl")
        raise SourceBlockedError(
            "amazon",
            f"anti-bot em {fails}/{total} buscas via {'+'.join(rotas)}",
            "Amazon BR negou a maioria das requests em todas as rotas. "
            "Conferir Chrome/patchright (rota browser), subir delay_seconds "
            "ou rodar mais tarde.",
        )
    return all_listings
