"""lib/ebay_client.py — cliente mínimo da eBay Browse API (stdlib puro).

Usado pelo `build_ebay_reference.py` para buscar o MENOR ANÚNCIO ATIVO de cada
SKU selado no eBay US — a referência do LADO DE VENDA (o operador vende via
Probstein, consignação em leilões/anúncios no eBay US).

Por que API e não scraping: o eBay bloqueia scraping direto (HTTP 403, provado
na frota em 2026-06-09). A Browse API é oficial e gratuita (5.000 chamadas/dia)
e devolve JSON estruturado. Setup (uma vez, ~5 min, grátis):
  1. Criar conta em https://developer.ebay.com (pode usar a conta eBay normal).
  2. Em "Application Keys", criar um keyset de PRODUCTION.
  3. Definir EBAY_CLIENT_ID (App ID) e EBAY_CLIENT_SECRET (Cert ID) como env
     vars (ou no `.env` da raiz deste repo — lido por lib/env.py).

Adaptado do cliente da frota (`ebay-arbitrage-scanner/src/ebay_api.py` — repos
independentes: código é COPIADO, nunca importado entre repos) com 2 diferenças
para o caso SELADO:
  - `category_ids` virou parâmetro com default None (SEM filtro de categoria).
    A categoria 183454 do scanner de singles é "CCG Individual Cards" — errada
    para selado, e NÃO chutamos um ID de categoria de selados (pinagem via
    Taxonomy API é backlog). Precisão vem dos guards de título do builder.
  - throttle + retry (padrão do outlook/ebay_availability.py): 0.35s entre
    chamadas com backoff, retry só em 429/5xx/erro de rede.

Nunca loga/imprime as credenciais. Sanitização BOM/zero-width inclusa
(erro recorrente nº 1 da frota).
"""
from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"
TIMEOUT_S = 30
RETRIES = 3
REQUEST_DELAY_S = 0.35
# Códigos HTTP que valem retry (rate-limit / instabilidade). 4xx de request
# malformado NÃO tem retry — falha na hora, com o erro real.
_RETRYABLE_HTTP = (429, 500, 502, 503, 504)

# Aliases módulo-level p/ os testes monkeypatcharem sem tocar o módulo global.
_urlopen = urllib.request.urlopen
_sleep = time.sleep


class EbayAuthError(RuntimeError):
    pass


def _clean_secret(value: str | None) -> str:
    """Remove BOM/zero-width/espaços de uma credencial lida do ambiente.

    Chave colada com BOM (U+FEFF) ou zero-width (U+200B) viraria um header
    Authorization Basic inválido (eBay 401 "configurado mas não autentica");
    pior, uma chave SÓ de invisíveis passaria como "configurada" (truthy).
    `.strip()` NÃO remove BOM/zero-width — removemos explícito. Erro
    recorrente nº 1 da frota (ver CLAUDE.md).
    """
    if not value:
        return ""
    return value.replace("\ufeff", "").replace("\u200b", "").strip()


class EbayClient:
    """OAuth client-credentials + busca de anúncios ativos (item_summary/search)."""

    def __init__(self, client_id: str | None = None, client_secret: str | None = None,
                 marketplace: str = "EBAY_US"):
        self.client_id = _clean_secret(client_id or os.environ.get("EBAY_CLIENT_ID", ""))
        self.client_secret = _clean_secret(client_secret or os.environ.get("EBAY_CLIENT_SECRET", ""))
        self.marketplace = marketplace
        self._token: str | None = None
        self._token_expires_at = 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.client_secret)

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expires_at - 60:
            return self._token
        if not self.configured:
            raise EbayAuthError(
                "EBAY_CLIENT_ID / EBAY_CLIENT_SECRET não definidos. "
                "Setup grátis (~5 min): ver topo de lib/ebay_client.py."
            )
        creds = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        body = urllib.parse.urlencode({"grant_type": "client_credentials", "scope": SCOPE}).encode()
        req = urllib.request.Request(
            TOKEN_URL,
            data=body,
            headers={
                "Authorization": f"Basic {creds}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        )
        with _urlopen(req, timeout=TIMEOUT_S) as r:
            payload = json.loads(r.read().decode())
        self._token = payload["access_token"]
        self._token_expires_at = time.time() + int(payload.get("expires_in", 7200))
        return self._token

    def search(self, query: str, *, category_ids: str | None = None, limit: int = 50,
               fixed_price_only: bool = True, location_country: str | None = "US",
               min_price: float | None = None, max_price: float | None = None) -> list[dict]:
        """Anúncios ativos (itemSummaries CRUS, dicts da API), ordenados por preço.

        - `category_ids=None` (default) = SEM filtro de categoria — para selado
          não usamos a categoria de singles nem chutamos outra; os guards de
          título do caller garantem a precisão.
        - `fixed_price_only=True` = só Buy It Now (pedida firme; leilão no meio
          do prazo não é referência de pedida).
        - `location_country="US"` = item localizado nos EUA (o mercado onde o
          operador vende via Probstein). Passe None/"" para desligar.
        - Preço SEM frete (o sort do eBay considera preço+frete; varrer os
          `limit` primeiros cobre o reordenamento).
        - Retry só em 429/5xx/erro de rede, com espera escalonada.
        """
        filters: list[str] = []
        if min_price is not None or max_price is not None:
            lo = f"{min_price:g}" if min_price is not None else ""
            hi = f"{max_price:g}" if max_price is not None else ""
            filters.append(f"price:[{lo}..{hi}]")
            filters.append("priceCurrency:USD")
        if location_country:
            filters.append(f"itemLocationCountry:{location_country}")
        if fixed_price_only:
            filters.append("buyingOptions:{FIXED_PRICE}")
        params: dict[str, str] = {"q": query, "limit": str(limit), "sort": "price"}
        if category_ids:
            params["category_ids"] = str(category_ids)
        if filters:
            params["filter"] = ",".join(filters)
        url = SEARCH_URL + "?" + urllib.parse.urlencode(params)

        last_error: Exception | None = None
        for attempt in range(RETRIES):
            _sleep(REQUEST_DELAY_S * (attempt + 1))
            req = urllib.request.Request(
                url,
                headers={
                    "Authorization": f"Bearer {self._get_token()}",
                    "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
                },
            )
            try:
                with _urlopen(req, timeout=TIMEOUT_S) as r:
                    payload = json.loads(r.read().decode())
                return payload.get("itemSummaries") or []
            except urllib.error.HTTPError as exc:
                if exc.code in _RETRYABLE_HTTP:
                    last_error = exc
                    continue
                raise
            except urllib.error.URLError as exc:
                last_error = exc
                continue
        assert last_error is not None
        raise last_error
