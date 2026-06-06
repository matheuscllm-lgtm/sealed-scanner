#!/usr/bin/env python3
"""
mercadolivre_adapter.py — adapter para Mercado Livre Brasil (selados Pokémon).

4ª fonte BR (ao lado de amazon/liga/olx). Entrega listings crus (título +
preço + url); o matcher/economia do scanner faz o resto, igual às outras fontes.

ACESSO (probe ao vivo 2026-06-06): o ML é mais duro que a OLX.
  - API oficial `sites/MLB/search` → 403 sem OAuth (fechada ~2024).
  - HTML via urllib puro → redirect pra `gz/account-verification`
    (`suspicious-traffic-frontend`) — anti-bot PRÓPRIO do ML, NÃO Cloudflare.
  - Firecrawl proxy=stealth + waitFor=6000 (o número da OLX) → AINDA cai no
    account-verification. Só com waitFor≈12-15s o device-check (challenge JS)
    clareia e a busca server-side completa volta (medido: 1.46 MB, 50 cards).

Por isso o adapter é FIRECRAWL-FIRST (≠ OLX, que é urllib-first): o urllib puro
não rende aqui, sem nem a "janela de IP frio" da OLX. Mantém-se um modo `urllib`
opcional só por simetria/futuro, mas hoje ele cai direto no anti-bot.

O parser é DOM/CSS (BeautifulSoup), igual Amazon — a busca do ML NÃO expõe
`__NEXT_DATA__` (OLX) nem `preloadedState` (legado morto). Seletores validados
ao vivo 2026-06-06 (ver §5 do HANDOFF-mercadolivre-adapter-2026-06-06.md).

ESCOPO — INVARIANTE DURO: exclusivamente PRODUTO SELADO, só inglês. O ML é o
marketplace mais RUIDOSO de não-selado (lote de cartas, single raro caro, deck,
gradada, acessório) e dominado por PT-BR/COPAG. As defesas são compartilhadas e
não vivem aqui: o `match_listing` casa set_terms E type_terms (single não tem
type_term de box) e o registry já exclui `copag/portugues/...`. O adapter só
transporta + parseia; se um não-selado vazar, é bug de escopo (não relaxar
filtro). Ver HANDOFF §1/§3.

CONDIÇÃO (novo vs usado) — LIMITAÇÃO CONHECIDA: o ML vende usado, mas a condição
NÃO aparece no card da listagem (confirmado no probe 2026-06-06: 0 sinais de
condição em 48 cards; só existe na página do produto). No scrape de busca só dá
pra heurística fraca por título (`_looks_used`). A rota limpa é a API OAuth
(`condition:new` de graça) — evolução v2 documentada no HANDOFF §11. Não
fabricamos: o que não dá pra ler com confiança, não inventamos.
"""
from __future__ import annotations

import http.client
import json
import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lib.errors import SourceBlockedError

# Busca por TIPO de produto (queries amplas); o matcher do scanner filtra
# contra o registry. O path /games-brinquedos ancora a categoria certa e
# corta parte do ruído de fora de games.
BASE = "https://lista.mercadolivre.com.br/games-brinquedos/"

FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v2/scrape"

# waitFor default ALTO (≠ OLX 6s): o device-check do ML precisa de ~12-15s pra
# resolver o challenge JS. 6s cai no account-verification (medido).
_DEFAULT_WAIT_MS = 14000

# Tokens da página de anti-bot DO ML (device-check / suspicious-traffic). NÃO
# são os tokens Cloudflare da OLX — o ML tem o próprio. Quando o HTML contém
# qualquer um destes, a página real não carregou (block).
_BLOCK_TOKENS = (
    "account-verification",
    "suspicious-traffic",
    "suspicious traffic",
    "/gz/account",
    "validate that you are not a robot",
    "confirme que você é uma pessoa",
)
_BLOCK_HINT = (
    "Mercado Livre serviu o anti-bot próprio (account-verification / "
    "suspicious-traffic), não o WAF da OLX. urllib puro NÃO passa; o caminho é "
    "config.mercadolivre.mode=firecrawl (proxy stealth + waitFor ~14s, "
    "FIRECRAWL_API_KEY já no ambiente). O device-check é intermitente por "
    "reputação de IP — pode falhar mesmo via proxy; nesse caso é BLOQUEADA "
    "honesto. Rota robusta futura: API oficial via OAuth (HANDOFF §11). As "
    "outras fontes (amazon/liga/olx) seguem operacionais."
)

# Heurística FRACA de usado por título (a condição real não está no card —
# ver docstring). Best-effort: marca/loga, não é gate confiável.
_USED_TOKENS = (
    "usado", "usada", "aberto", "aberta", "sem plastico", "sem plástico",
    "sem lacre", "open box",
)


def _load_dotenv_if_present() -> None:
    """Carrega .env da raiz do repo se existir, sem sobrescrever env já setado.
    (mode=firecrawl lê FIRECRAWL_API_KEY do ambiente; .env é só fallback.)"""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def _is_block_page(body: str) -> bool:
    low = body.lower()
    return any(tok in low for tok in _BLOCK_TOKENS)


def _looks_used(title: str) -> bool:
    low = title.lower()
    return any(tok in low for tok in _USED_TOKENS)


def _price_to_float(text: str) -> float | None:
    """'R$ 1.299' -> 1299.0; '1.412,58' -> 1412.58 (BR: ponto=milhar, vírgula=decimal)."""
    cleaned = "".join(c for c in str(text) if c.isdigit() or c in ".,")
    if not cleaned:
        return None
    cleaned = cleaned.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


_MLB_RE = re.compile(r"MLB-?\d+")


def _extract_id(url: str) -> str:
    """ID do anúncio pra dedup. Os hrefs do ML carregam `MLB-<digits>` (medido:
    48/48 no probe). Fallback: o path canônico sem query/fragmento."""
    m = _MLB_RE.search(url or "")
    if m:
        return m.group(0).replace("-", "")
    # Fallback raro: usa o path sem #position/?tracking pra estabilizar a chave.
    path = urllib.parse.urlsplit(url or "").path
    return path or (url or "")


def _card_price(card) -> float | None:
    """Preço ATUAL do card. CUIDADO: o ML repete `.andes-money-amount__fraction`
    pro preço riscado (`--previous`) E pro atual — e o riscado costuma vir
    PRIMEIRO no DOM (medido: fractions=[449, 413, 449], atual=413). Por isso
    escopamos em `.poly-price__current` (fallback `.poly-component__price`),
    nunca o 1º fraction solto do card."""
    block = card.select_one(".poly-price__current") or card.select_one(".poly-component__price")
    if block is None:
        return None
    # Dentro do bloco atual, ignora qualquer `--previous` que tenha vazado.
    amount = None
    for amt in block.select(".andes-money-amount"):
        cls = amt.get("class") or []
        if "andes-money-amount--previous" in cls:
            continue
        amount = amt
        break
    if amount is None:
        amount = block
    frac = amount.select_one(".andes-money-amount__fraction")
    if frac is None:
        return None
    cents = amount.select_one(".andes-money-amount__cents")
    text = frac.get_text(strip=True)
    if cents is not None and cents.get_text(strip=True):
        text = f"{text},{cents.get_text(strip=True)}"
    return _price_to_float(text)


def parse_search_results(html: str) -> list[dict]:
    """DOM/CSS parser (seletores validados ao vivo 2026-06-06). Devolve dicts
    crus; o matcher/economia do scanner faz o resto."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    cards = soup.select("li.ui-search-layout__item")
    out: list[dict] = []
    for card in cards:
        a = card.select_one("a.poly-component__title")
        if a is None:
            continue
        title = a.get_text(strip=True)
        url = a.get("href", "") or ""
        if not title:
            continue
        price = _card_price(card)
        if price is None:
            continue  # sem preço legível → descarta (não fabrica)
        seller_el = card.select_one(".poly-component__seller")
        seller = seller_el.get_text(strip=True) if seller_el else "Mercado Livre"
        out.append({
            "title": title,
            "price_brl": price,
            "seller": "ML " + (seller or "Mercado Livre"),
            "url": url,
            "ml_id": _extract_id(url),
            "maybe_used": _looks_used(title),
        })
    return out


# --------------------------------------------------------------------------
# Fetcher abstrato — espelha _Fetcher do olx_adapter. Só o TRANSPORTE muda;
# parser (parse_search_results) e detecção de block (_is_block_page) são
# compartilhados entre os modos.
# --------------------------------------------------------------------------
class _Fetcher:
    def get_html(self, url: str) -> str:
        raise NotImplementedError

    def close(self) -> None:
        pass


class _UrllibFetcher(_Fetcher):
    """GET direto via urllib. Mantido só por simetria/futuro: hoje o ML redireciona
    pro anti-bot (account-verification) sem nem a janela de IP frio da OLX. Se a
    resposta for página de block, levanta SourceBlockedError (não fabrica dado)."""

    UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

    def get_html(self, url: str, timeout: int = 30) -> str:
        req = urllib.request.Request(url, headers={
            "User-Agent": self.UA,
            "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            final_url = r.geturl()
            body = r.read().decode("utf-8", errors="replace")
        # O ML redireciona pro account-verification (a URL final já denuncia).
        if _is_block_page(final_url) or _is_block_page(body):
            raise SourceBlockedError("mercadolivre", "anti-bot do ML (urllib)", _BLOCK_HINT)
        return body


class _FirecrawlFetcher(_Fetcher):
    """GET via Firecrawl (render + proxy stealth + waitFor alto) — fura o device-check
    do ML (Tier 1, o caminho pronto). Manda a URL pro /v2/scrape com
    formats=['rawHtml'], location BR e waitFor≈14s (validado 2026-06-06: volta a
    busca server-side com os cards). Passa o rawHtml pro MESMO parser. Se mesmo
    via proxy a resposta vier como account-verification, levanta SourceBlockedError."""

    def __init__(self, api_key: str, *, proxy: str = "stealth",
                 wait_ms: int = _DEFAULT_WAIT_MS, timeout: int = 220, retries: int = 2):
        self.api_key = api_key
        self.proxy = proxy
        self.wait_ms = wait_ms
        self.timeout = timeout
        self.retries = retries

    def _call(self, url: str) -> dict:
        payload = {
            "url": url,
            "formats": ["rawHtml"],
            "location": {"country": "BR", "languages": ["pt-BR"]},
            "proxy": self.proxy,
            "waitFor": self.wait_ms,
            "onlyMainContent": False,
        }
        req = urllib.request.Request(
            FIRECRAWL_ENDPOINT,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": "Bearer " + self.api_key,
                "Content-Type": "application/json",
            },
        )
        last_exc: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    return json.loads(r.read().decode("utf-8", errors="replace"))
            except urllib.error.HTTPError as exc:
                last_exc = exc
                # 402 = sem créditos (não retenta). 408/429/5xx = transitório.
                if exc.code in (408, 429, 500, 502, 503, 504) and attempt < self.retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
            except (urllib.error.URLError, http.client.RemoteDisconnected,
                    ConnectionError, TimeoutError) as exc:
                last_exc = exc
                if attempt < self.retries:
                    time.sleep(2 * (attempt + 1))
                    continue
                raise
        assert last_exc is not None
        raise last_exc

    def get_html(self, url: str) -> str:
        j = self._call(url)
        if not j.get("success", True):
            raise RuntimeError(f"Firecrawl falhou: {j.get('error') or j}")
        data = j.get("data", j)
        html = data.get("rawHtml") or data.get("html") or ""
        if not html:
            raise RuntimeError("Firecrawl retornou HTML vazio (sem rawHtml).")
        # Mesmo via render/proxy o device-check pode vencer — honesto, não fabrica.
        if _is_block_page(html):
            raise SourceBlockedError(
                "mercadolivre", "anti-bot do ML mesmo via Firecrawl", _BLOCK_HINT
            )
        return html


def _make_fetcher(ml_cfg: dict) -> _Fetcher:
    """Cria o fetcher conforme config.mercadolivre.mode. FIRECRAWL-FIRST: o
    default é `firecrawl` (≠ OLX, que é urllib). Env MERCADOLIVRE_MODE tem prioridade."""
    _load_dotenv_if_present()
    mode = (os.environ.get("MERCADOLIVRE_MODE") or ml_cfg.get("mode") or "firecrawl").lower()
    if mode == "urllib":
        return _UrllibFetcher()
    if mode == "firecrawl":
        key = os.environ.get("FIRECRAWL_API_KEY") or ml_cfg.get("firecrawl_api_key")
        if not key:
            raise RuntimeError(
                "FIRECRAWL_API_KEY não configurada (mercadolivre.mode=firecrawl). "
                "Defina como env var (já herdada pelos scanners neste ambiente), "
                "em .env na raiz do repo, ou em mercadolivre.firecrawl_api_key no "
                "config.yaml. (urllib puro NÃO passa no anti-bot do ML.)"
            )
        return _FirecrawlFetcher(
            key,
            proxy=ml_cfg.get("firecrawl_proxy", "stealth"),
            wait_ms=ml_cfg.get("firecrawl_wait_ms", _DEFAULT_WAIT_MS),
        )
    raise ValueError(
        f"mercadolivre.mode desconhecido: {mode!r}. Use 'firecrawl' (default) ou 'urllib'."
    )


# Queries amplas por TIPO de produto (igual OLX). Firecrawl stealth + waitFor 14s
# custa créditos por scrape — começar barato (§9-A do HANDOFF): ~8 buscas amplas,
# 1 página cada. O ML tem inventário grande; busca ampla já traz bastante e o
# matcher filtra. Query por SKU (105×) ou paginação são otimizações futuras.
TYPE_TO_QUERY = {
    "Booster Box":        ["pokemon-booster-box-ingles"],
    "Elite Trainer Box":  ["pokemon-elite-trainer-box-ingles"],
    "Booster Bundle":     ["pokemon-booster-bundle-ingles"],
    "Collection Box":     ["pokemon-collection-box-ingles"],
    "Premium Collection": ["pokemon-premium-collection-ingles"],
    "Tin":                ["pokemon-tin-ingles"],
    "Sleeved Booster":    ["pokemon-sleeved-booster-ingles"],
    "Blister Pack":       ["pokemon-blister-ingles"],
}


def _derive_queries(registry: list[dict]) -> list[str]:
    """Queries únicas por product_type EN presente no registry."""
    queries: set[str] = set()
    for sku in registry:
        if sku.get("language", "").upper() != "EN":
            continue
        for q in TYPE_TO_QUERY.get(sku.get("product_type", ""), []):
            queries.add(q)
    return sorted(queries)


def _build_url(query: str) -> str:
    """ML usa o termo como segmento de path (busca SSR), não ?q=."""
    return BASE + urllib.parse.quote(query, safe="-")


def fetch_listings(config: dict, registry: list[dict]) -> list[dict]:
    if not registry:
        raise ValueError("mercadolivre_adapter requer o registry para gerar queries.")
    ml_cfg = config.get("mercadolivre", {})
    delay = ml_cfg.get("delay_seconds", 1.5)
    limit_per_query = ml_cfg.get("results_per_query", 50)

    queries = _derive_queries(registry)
    if not queries:
        raise ValueError(
            "nenhuma query Mercado Livre gerada (registry vazio ou sem product_types conhecidos)."
        )

    fetcher = _make_fetcher(ml_cfg)
    all_listings: list[dict] = []
    seen_ids: set[str] = set()
    failed = 0  # queries que não entregaram HTML (block ou transitório)
    try:
        for i, query in enumerate(queries):
            url = _build_url(query)
            try:
                html = fetcher.get_html(url)
            except SourceBlockedError:
                # Anti-bot nesta query. NÃO aborta a fonte no 1º block: conta como
                # perdida e segue. Só vira BLOQUEADA se TODAS falharem e nada
                # coletado (ver no fim) — mesmo contrato honesto da OLX/Amazon.
                failed += 1
                print(f"  [aviso] ML bloqueado para '{query}' (anti-bot). Seguindo...")
                continue
            except Exception as exc:
                failed += 1
                print(f"  [aviso] busca ML falhou para '{query}': {exc}")
                continue
            results = parse_search_results(html)
            slug = query.split("-")[1] if "-" in query else query
            kept = 0
            for r in results[:limit_per_query]:
                mid = str(r.get("ml_id", ""))
                if mid and mid in seen_ids:
                    continue
                if mid:
                    seen_ids.add(mid)
                entry = dict(r)
                entry["id"] = f"ML-{slug}-{kept + 1}"
                entry["source"] = "mercadolivre"
                entry["query"] = query
                all_listings.append(entry)
                kept += 1
            if i < len(queries) - 1:
                time.sleep(delay + random.uniform(0, 0.75))
    finally:
        fetcher.close()

    # BLOQUEADA honesto só no fim: todas as queries falharam E nada coletado.
    # (Mesma trilha de Amazon PR #9 / OLX PR #10 — não mascarar block como
    # "ok, 0 anúncios", mas não estourar BLOQUEADA num 0-inventário parcial.)
    if failed and not all_listings and failed == len(queries):
        raise SourceBlockedError(
            "mercadolivre",
            f"todas as {failed} queries falharam (anti-bot/transitório)",
            _BLOCK_HINT,
        )
    return all_listings
