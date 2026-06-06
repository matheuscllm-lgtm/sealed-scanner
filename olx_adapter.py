#!/usr/bin/env python3
"""
olx_adapter.py — adapter para OLX Brasil (busca de selados Pokémon).

OLX expõe os anúncios no JSON __NEXT_DATA__ embutido no HTML da página de
busca, parseável direto. Para cada SKU do registry faz uma busca em
olx.com.br/brasil?q=... e devolve as listagens; o matcher do scanner
depois decide o que casa.

ACESSO (revisado 2026-06-05): a OLX serve Cloudflare WAF managed-rule /
IP-reputation block. NÃO é o challenge "Just a moment"/Turnstile (que a Liga
atravessa com Chrome headful) — não há captcha pra resolver. O comportamento
medido é ESCALAÇÃO POR REPUTAÇÃO DE IP: a 1ª request num IP "frio" às vezes
passa (50 anúncios), mas depois de poucas requests o WAF flaga o IP e mantém
o block de forma sustentada (cooldown + baixa frequência não limpam dentro
da janela testada). Há também `http.client.RemoteDisconnected` transitório.

Por isso o adapter tem DOIS modos de transporte (config.olx.mode):

  mode=urllib     (DEFAULT) GET direto via urllib + retry/backoff/jitter.
                  Trata block e RemoteDisconnected como retentáveis e só
                  desiste da query após esgotar as tentativas. Recupera a
                  janela de IP frio e para de abortar no 1º block, MAS — dado
                  o comportamento de escalação — NÃO entrega OLX cheia de
                  forma confiável quando o IP já está flagado. É a base
                  correta de robustez, não a solução de acesso.

  mode=firecrawl  Roteia a busca via Firecrawl (render + proxy stealth, fura
                  o WAF), retorna o HTML renderizado e passa pelo MESMO
                  parser. É o que faz a OLX voltar a entregar inventário de
                  forma repetível. Usa FIRECRAWL_API_KEY (env/.env). O parser
                  e a detecção de block NÃO mudam — só a camada de transporte.

Em ambos os modos, se a fonte negar acesso de fato (todas as queries
bloqueadas e nada coletado), o adapter levanta `SourceBlockedError` e o
scanner trata como condição EXTERNA não-fatal (Amazon e Liga seguem). Nunca
fabrica dado: se mesmo via proxy a OLX bloquear, reporta BLOQUEADA honesto.

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
import http.client
import json
import os
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from lib.errors import SourceBlockedError

BASE = "https://www.olx.com.br/brasil?q="
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/124.0 Safari/537.36"

FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v2/scrape"

# Retry/backoff do mode=urllib. O block escala por reputação de IP, então o
# backoff é mais largo que o de um anti-bot coin-flip — a 1ª request pode
# passar e as seguintes não. Retry recupera a janela de IP frio; não cura a
# flag sustentada (pra isso é o mode=firecrawl).
_BLOCK_RETRIES = 4
_BACKOFF = 4.0

# Tokens da página de BLOCK do Cloudflare ("you have been blocked" / WAF
# managed-rule / IP reputation). Distinto do challenge "Just a moment"/Turnstile,
# que auto-resolve — este é terminal por requisição, não há captcha pra clicar.
# Reproduzido em 2026-05-29 e 2026-06-05: urllib e patchright batem nisso.
_BLOCK_TOKENS = (
    "you have been blocked",
    "attention required",
    "sorry, you have been blocked",
    "cf-error-details",
)
_BLOCK_HINT = (
    "OLX está com block WAF do Cloudflare neste IP (não é Turnstile, não há "
    "captcha pra resolver; é escalação por reputação de IP). Opções: usar "
    "config.olx.mode=firecrawl (render+proxy stealth, FIRECRAWL_API_KEY já no "
    "ambiente), rodar de outra rede/IP, ou rotear via proxy residencial. "
    "Amazon e Liga seguem operacionais."
)


def _load_dotenv_if_present() -> None:
    """Carrega .env da raiz do repo se existir. Não sobrescreve env vars já setadas.
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
    """GET cru via urllib. Levanta SourceBlockedError se a resposta for página
    de block do CF (403/429/503 com corpo de block, ou 200-com-block)."""
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


# --------------------------------------------------------------------------
# Fetcher abstrato — urllib (direto + retry) ou firecrawl (render/proxy)
# Espelha a abstração _Fetcher do liga_adapter: só a camada de TRANSPORTE
# muda; o parser (parse_search_results) e a detecção de block (_is_block_page)
# são compartilhados e idênticos entre os modos.
# --------------------------------------------------------------------------
class _Fetcher:
    def get_html(self, url: str) -> str:
        raise NotImplementedError

    def close(self) -> None:
        pass


class _UrllibFetcher(_Fetcher):
    """GET direto via urllib com retry/backoff/jitter (Tier 1).

    Retenta a MESMA URL em block (SourceBlockedError) e em falha transitória
    de conexão (RemoteDisconnected/URLError). Backoff largo + jitter porque o
    WAF correlaciona cadência fixa. Recupera a janela de IP frio; quando o IP
    já está flagado, esgota as tentativas e propaga o erro (o caller conta
    como query perdida e, se TODAS perderem, levanta BLOQUEADA honesto)."""

    def __init__(self, retries: int = _BLOCK_RETRIES, backoff: float = _BACKOFF):
        self.retries = retries
        self.backoff = backoff

    def get_html(self, url: str) -> str:
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                return _fetch(url)
            except SourceBlockedError as exc:
                last_exc = exc
            except (urllib.error.URLError, http.client.RemoteDisconnected,
                    ConnectionError, TimeoutError) as exc:
                last_exc = exc
            if attempt < self.retries - 1:
                time.sleep(self.backoff * (attempt + 1) + random.uniform(0, 1.0))
        assert last_exc is not None  # só chega aqui se todas as tentativas falharam
        raise last_exc


class _FirecrawlFetcher(_Fetcher):
    """GET via Firecrawl (render + proxy stealth) — fura o WAF da OLX (Tier 2).

    Manda a URL de busca pro endpoint /v2/scrape com formats=['rawHtml'],
    location BR e proxy=stealth (validado 2026-06-05: retorna o __NEXT_DATA__
    renderizado com props.pageProps.ads). Devolve o rawHtml pro MESMO parser.
    Se mesmo via proxy a resposta vier como página de block, levanta
    SourceBlockedError — não fabrica dado."""

    def __init__(self, api_key: str, *, proxy: str = "stealth",
                 wait_ms: int = 6000, timeout: int = 180, retries: int = 2):
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
        # Mesmo via render/proxy o WAF pode bloquear — reporta honesto, não fabrica.
        if _is_block_page(html):
            raise SourceBlockedError(
                "olx", "Cloudflare WAF block mesmo via Firecrawl", _BLOCK_HINT
            )
        return html


def _make_fetcher(olx_cfg: dict) -> _Fetcher:
    """Cria o fetcher conforme config.olx.mode (env OLX_MODE também tem prioridade)."""
    _load_dotenv_if_present()
    mode = (os.environ.get("OLX_MODE") or olx_cfg.get("mode") or "urllib").lower()
    if mode == "urllib":
        return _UrllibFetcher()
    if mode == "firecrawl":
        key = os.environ.get("FIRECRAWL_API_KEY") or olx_cfg.get("firecrawl_api_key")
        if not key:
            raise RuntimeError(
                "FIRECRAWL_API_KEY não configurada (olx.mode=firecrawl). Defina "
                "como env var (já herdada pelos scanners neste ambiente), em .env "
                "na raiz do repo, ou em olx.firecrawl_api_key no config.yaml. "
                "Alternativa sem proxy: olx.mode=urllib (default)."
            )
        return _FirecrawlFetcher(
            key,
            proxy=olx_cfg.get("firecrawl_proxy", "stealth"),
            wait_ms=olx_cfg.get("firecrawl_wait_ms", 6000),
        )
    raise ValueError(f"olx.mode desconhecido: {mode!r}. Use 'urllib' ou 'firecrawl'.")


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

    fetcher = _make_fetcher(olx_cfg)
    all_listings: list[dict] = []
    seen_ids: set[str] = set()
    failed = 0  # queries que não entregaram HTML após retry (block ou transitório)
    try:
        for i, query in enumerate(queries):
            url = BASE + urllib.parse.quote_plus(query)
            try:
                html = fetcher.get_html(url)
            except SourceBlockedError:
                # Block por IP/WAF nesta query. NÃO aborta a fonte inteira no 1º
                # block (Tier 1): conta como perdida e segue. Só vira BLOQUEADA
                # se TODAS as queries falharem e nada for coletado (ver no fim).
                failed += 1
                print(f"  [aviso] OLX bloqueada para '{query}' (WAF). Seguindo...")
                continue
            except Exception as exc:
                failed += 1
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
                # jitter no delay: cadência fixa correlaciona com o WAF.
                time.sleep(delay + random.uniform(0, 0.75))
    finally:
        fetcher.close()

    # BLOQUEADA honesto só no fim: todas as queries falharam E nada coletado.
    # (Mesma trilha do fix da Amazon no PR #9 — não mascarar block como
    # "status=ok, 0 anúncios"; mas só declara bloqueio quando de fato nada
    # passou, pra não estourar BLOQUEADA num 0-inventário legítimo parcial.)
    if failed and not all_listings and failed == len(queries):
        raise SourceBlockedError(
            "olx",
            f"todas as {failed} queries falharam (WAF/transitório)",
            _BLOCK_HINT,
        )
    return all_listings
