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

import os
import random
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from lib.errors import SourceBlockedError
from lib.firecrawl import FirecrawlFetcher  # transporte /scrape compartilhado (Issue #13)

# Busca por TIPO de produto (queries amplas); o matcher do scanner filtra
# contra o registry. O path /games-brinquedos ancora a categoria certa e
# corta parte do ruído de fora de games.
BASE = "https://lista.mercadolivre.com.br/games-brinquedos/"

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


def _norm_text(s: str) -> str:
    """casefold + remove acento, p/ casar o vendedor contra o seller_allowlist
    sem depender de acento/caixa ('ML POKÉMON' ~ 'pokemon', 'COPAG' ~ 'copag')."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.casefold().strip()


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


class _FirecrawlFetcher(FirecrawlFetcher):
    """ML é firecrawl-first: o device-check próprio precisa de waitFor ~14s
    (≠ 6s da OLX) e o anti-bot é o `account-verification` dele, não o CF.

    Transporte (POST /v2/scrape + retry + extração do rawHtml) vem de
    `lib.firecrawl.FirecrawlFetcher`; aqui só os parâmetros por-fonte + o
    detector de block. Se a resposta vier como account-verification mesmo via
    proxy, a base levanta SourceBlockedError — não fabrica dado."""
    SOURCE = "mercadolivre"
    DEFAULT_WAIT_MS = _DEFAULT_WAIT_MS  # 14000 — device-check do ML
    DEFAULT_TIMEOUT = 220
    BLOCK_MSG = "anti-bot do ML mesmo via Firecrawl"
    BLOCK_HINT = _BLOCK_HINT

    def _is_block(self, html: str) -> bool:
        return _is_block_page(html)


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


# Busca DENTRO de uma loja confiável (search_mode=stores). Mais recall e precisão
# que a busca ampla: lista.ml.com.br/loja/{slug}/{query} devolve só os itens
# daquela loja, no MESMO parser SSR (validado ao vivo 2026-06-07: escopo 100% —
# loja/asmodee/pokemon = só Asmodee). Vale p/ LOJA OFICIAL (tem slug); vendedor
# comum não tem /loja/ — precisa de filtro por seller_id (evolução futura).
_LISTA_ROOT = "https://lista.mercadolivre.com.br/"


def _store_url(slug: str, query: str) -> str:
    return f"{_LISTA_ROOT}loja/{slug.strip('/')}/{urllib.parse.quote(query, safe='-')}"


def _derive_targets(ml_cfg: dict, registry: list[dict]) -> list[tuple[str, str]]:
    """Lista de (label, url) conforme search_mode:
      - 'stores' (recomendado): busca `store_query` DENTRO de cada loja confiável.
      - 'type'   (fallback): buscas amplas por product_type EN no ML inteiro.
    Modo stores sem lista de lojas cai no type (não trava a fonte). O `label` é o
    slug ÚNICO da busca (tipo OU loja) — vira a chave do id do anúncio."""
    mode = (ml_cfg.get("search_mode") or "type").lower()
    stores = [str(s).strip() for s in (ml_cfg.get("stores") or []) if str(s).strip()]
    if mode == "stores" and stores:
        q = ml_cfg.get("store_query", "pokemon")
        return [(slug, _store_url(slug, q)) for slug in stores]
    return [(q.removeprefix("pokemon-").removesuffix("-ingles") or q, _build_url(q))
            for q in _derive_queries(registry)]


def fetch_listings(config: dict, registry: list[dict]) -> list[dict]:
    ml_cfg = config.get("mercadolivre", {})
    delay = ml_cfg.get("delay_seconds", 1.5)
    limit_per_query = ml_cfg.get("results_per_query", 50)
    mode = (ml_cfg.get("search_mode") or "type").lower()
    # seller_allowlist (opcional, modo TYPE): VAZIO = sem filtro. Termos casam o
    # vendedor por substring sem acento/caixa. No modo STORES a URL já escopa por
    # loja, então o filtro é redundante e fica DESLIGADO lá.
    seller_allow = [_norm_text(t) for t in (ml_cfg.get("seller_allowlist") or []) if str(t).strip()]

    targets = _derive_targets(ml_cfg, registry)
    if not targets:
        raise ValueError(
            "nenhuma busca Mercado Livre gerada (modo type sem registry/product_types, "
            "ou modo stores sem lista de lojas)."
        )

    fetcher = _make_fetcher(ml_cfg)
    all_listings: list[dict] = []
    seen_ids: set[str] = set()
    failed = 0  # buscas que não entregaram HTML (block ou transitório)
    try:
        for i, (label, url) in enumerate(targets):
            try:
                html = fetcher.get_html(url)
            except SourceBlockedError:
                # Anti-bot nesta busca. NÃO aborta a fonte no 1º block: conta como
                # perdida e segue. Só vira BLOQUEADA se TODAS falharem e nada
                # coletado (ver no fim) — mesmo contrato honesto da OLX/Amazon.
                failed += 1
                print(f"  [aviso] ML bloqueado para '{label}' (anti-bot). Seguindo...")
                continue
            except Exception as exc:
                failed += 1
                print(f"  [aviso] busca ML falhou para '{label}': {exc}")
                continue
            results = parse_search_results(html)
            if seller_allow and mode != "stores":
                before = len(results)
                results = [r for r in results
                           if any(a in _norm_text(r.get("seller", "")) for a in seller_allow)]
                dropped = before - len(results)
                if dropped:
                    print(f"  [filtro] ML seller_allowlist: -{dropped} anúncio(s) de vendedor fora da lista ('{label}')")
            # `label` é o slug ÚNICO da busca (tipo OU loja) → chave do id, sem
            # colisão entre buscas (regressão do bug "ML-booster-1" duplicado).
            kept = 0
            for r in results[:limit_per_query]:
                mid = str(r.get("ml_id", ""))
                if mid and mid in seen_ids:
                    continue
                if mid:
                    seen_ids.add(mid)
                entry = dict(r)
                entry["id"] = f"ML-{label}-{kept + 1}"
                entry["source"] = "mercadolivre"
                entry["query"] = label
                all_listings.append(entry)
                kept += 1
            if i < len(targets) - 1:
                time.sleep(delay + random.uniform(0, 0.75))
    finally:
        fetcher.close()

    # BLOQUEADA honesto só no fim: todas as buscas falharam E nada coletado.
    # (Mesma trilha de Amazon PR #9 / OLX PR #10 — não mascarar block como
    # "ok, 0 anúncios", mas não estourar BLOQUEADA num 0-inventário parcial.)
    if failed and not all_listings and failed == len(targets):
        raise SourceBlockedError(
            "mercadolivre",
            f"todas as {failed} buscas falharam (anti-bot/transitório)",
            _BLOCK_HINT,
        )
    return all_listings
