"""lib/firecrawl.py — transporte Firecrawl `/scrape` compartilhado pelos adapters.

Antes desta extração (Issue #13), a chamada REST ao Firecrawl (montar payload,
POST via urllib, retry de transitório, extrair `rawHtml`) estava copiada em
`olx_adapter.py`, `amazon_adapter.py` e `mercadolivre_adapter.py`. Cada adapter
que ganhou rota Firecrawl re-colava o mesmo bloco. Aqui ele vive UMA vez.

O que é COMPARTILHADO (mora aqui):
  - `post_scrape()`  — POST ao endpoint /scrape com retry/backoff de transitório.
  - `extract_raw_html()` — valida o envelope e devolve o `rawHtml` (ou erra).
  - `FirecrawlFetcher` — fetcher genérico (transporte + detecção de block) que
    OLX e ML especializam por subclasse.

O que continua POR-FONTE (cada adapter define, NÃO unificar à força):
  - `wait_ms` — OLX usa ~6s; o ML precisa de ~14s (device-check próprio). É o
    pulo do gato; cada fonte seta o seu via subclasse/config.
  - detecção de block — o token de anti-bot difere: OLX casa o Cloudflare WAF,
    o ML casa o `account-verification`/`suspicious-traffic` dele. Cada subclasse
    sobrescreve `_is_block()`.
  - o parser (seletores DOM/CSS) — segue 100% no adapter (cada site é um site).

A Amazon usa só o `post_scrape()` + `extract_raw_html()` de baixo nível (rota
/v1, papel de FALLBACK quando o urllib leva 503), não a classe — porque lá o
Firecrawl não é o transporte primário.
"""
from __future__ import annotations

import http.client
import json
import time
import urllib.error
import urllib.request

from lib.errors import SourceBlockedError

FIRECRAWL_V1 = "https://api.firecrawl.dev/v1/scrape"
FIRECRAWL_V2 = "https://api.firecrawl.dev/v2/scrape"

# Códigos HTTP transitórios que valem retentar. 402 (sem créditos) e 4xx "de
# verdade" (400/404) NÃO entram — não adianta retentar.
_RETRYABLE = (408, 429, 500, 502, 503, 504)


def post_scrape(url: str, *, api_key: str, endpoint: str = FIRECRAWL_V2,
                proxy: str = "stealth", country: str = "BR",
                languages: tuple[str, ...] = ("pt-BR",), wait_ms: int | None = None,
                timeout: int = 180, retries: int = 2) -> dict:
    """POST ao Firecrawl `/scrape` pedindo `rawHtml`; devolve o envelope JSON cru.

    `wait_ms=None` omite `waitFor` (a rota /v1 da Amazon não usa). Retenta só os
    códigos de `_RETRYABLE` e erros de conexão transitórios, com backoff linear;
    o resto propaga na hora. Levanta a última exceção se esgotar as tentativas.
    """
    payload: dict = {
        "url": url,
        "formats": ["rawHtml"],
        "location": {"country": country, "languages": list(languages)},
        "proxy": proxy,
        "onlyMainContent": False,
    }
    if wait_ms is not None:
        payload["waitFor"] = wait_ms
    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
    )
    last_exc: Exception | None = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except urllib.error.HTTPError as exc:
            last_exc = exc
            if exc.code in _RETRYABLE and attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, http.client.RemoteDisconnected,
                ConnectionError, TimeoutError) as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(2 * (attempt + 1))
                continue
            raise
    assert last_exc is not None  # só chega aqui se todas as tentativas falharam
    raise last_exc


def extract_raw_html(envelope: dict, *, default_success: bool = True) -> str:
    """Valida o envelope do Firecrawl e devolve o `rawHtml`.

    `default_success` = o que assumir quando a chave `success` está ausente: o
    /v2 (OLX/ML) costuma omitir em sucesso → True; a Amazon (/v1) exige
    `success` truthy explícito → False. Levanta RuntimeError em falha/vazio.
    """
    if not envelope.get("success", default_success):
        raise RuntimeError(f"Firecrawl falhou: {envelope.get('error') or envelope}")
    data = envelope.get("data", envelope)
    html = data.get("rawHtml") or data.get("html") or ""
    if not html:
        raise RuntimeError("Firecrawl retornou HTML vazio (sem rawHtml).")
    return html


class FirecrawlFetcher:
    """Fetcher genérico via Firecrawl (render + proxy) — transporte primário.

    OLX e ML especializam por subclasse, definindo:
      - `SOURCE`          — nome da fonte pro `SourceBlockedError`.
      - `DEFAULT_WAIT_MS` — espera default (OLX 6s, ML 14s).
      - `DEFAULT_TIMEOUT` — timeout HTTP default.
      - `BLOCK_MSG` / `BLOCK_HINT` — mensagem/dica do block honesto.
      - `_is_block(html)` — detecta o anti-bot DAQUELA fonte (CF ≠ ML).

    `get_html()` devolve o `rawHtml` pro parser do adapter; se a resposta vier
    como página de block (mesmo via proxy), levanta `SourceBlockedError` — nunca
    fabrica dado.
    """
    SOURCE = "firecrawl"
    DEFAULT_WAIT_MS = 8000
    DEFAULT_TIMEOUT = 180
    ENDPOINT = FIRECRAWL_V2
    BLOCK_MSG = "anti-bot mesmo via Firecrawl"
    BLOCK_HINT = ""

    def __init__(self, api_key: str, *, proxy: str = "stealth",
                 wait_ms: int | None = None, timeout: int | None = None,
                 retries: int = 2):
        self.api_key = api_key
        self.proxy = proxy
        self.wait_ms = self.DEFAULT_WAIT_MS if wait_ms is None else wait_ms
        self.timeout = self.DEFAULT_TIMEOUT if timeout is None else timeout
        self.retries = retries

    def _call(self, url: str) -> dict:
        return post_scrape(
            url, api_key=self.api_key, endpoint=self.ENDPOINT, proxy=self.proxy,
            wait_ms=self.wait_ms, timeout=self.timeout, retries=self.retries,
        )

    def _is_block(self, html: str) -> bool:
        """Sobrescrever na subclasse com o detector de block da fonte."""
        return False

    def get_html(self, url: str) -> str:
        envelope = self._call(url)
        html = extract_raw_html(envelope)
        if self._is_block(html):
            raise SourceBlockedError(self.SOURCE, self.BLOCK_MSG, self.BLOCK_HINT)
        return html

    def close(self) -> None:
        pass
