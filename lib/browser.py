"""lib/browser.py — fetcher Chrome real + perfil persistente (patchright).

Generaliza o `_LocalChromeFetcher` do `liga_adapter`: roda do PC do operador
(IP residencial) com Google Chrome REAL (`channel="chrome"`) e um perfil
persistente que HERDA o cookie `cf_clearance` do Cloudflare entre execuções.
Sem proxy, sem custo.

Reutilizável por qualquer fonte que precise passar Cloudflare via browser real
(Liga, OLX, ...). O `profile_dir` é parametrizável pra isolar cookies por fonte
— assim o clearance de uma fonte não polui a outra.

Requer: `pip install patchright` + Google Chrome instalado.
"""
from __future__ import annotations

import time
from pathlib import Path

# Títulos de interstitial CF que indicam "ainda não liberou" (challenge em curso,
# auto-resolvível por browser real). NÃO inclui o block terminal ("you have been
# blocked"), que não some sozinho — esse é detectado pelo conteúdo, não pelo título.
_CF_PENDING_TITLE = ("just a moment", "just a", "moment", "um momento", "verificando")

# Tokens de página de BLOCK TERMINAL do Cloudflare (IP/ASN/managed-rule). Distinto
# do challenge: não há captcha pra resolver, é negação por requisição.
BLOCK_TOKENS = (
    "you have been blocked",
    "sorry, you have been blocked",
    "attention required",
    "cf-error-details",
    "error 1006",
    "error 1007",
    "error 1009",
    "error 1015",
    "error 1020",
)


def is_block_page(html: str) -> bool:
    low = html.lower()
    return any(tok in low for tok in BLOCK_TOKENS)


class LocalChromeFetcher:
    """Chrome real + perfil persistente. Abrir/fechar 1× por scan; várias páginas
    reaproveitam a mesma sessão (e o mesmo cf_clearance)."""

    def __init__(self, profile_dir: str, headless: bool = True,
                 extra_args: list[str] | None = None):
        self.profile_dir = profile_dir
        self.headless = headless
        self.extra_args = extra_args or []
        self._pw = None
        self._ctx = None
        self._page = None

    def _ensure(self):
        if self._ctx is not None:
            return
        try:
            from patchright.sync_api import sync_playwright
        except ImportError as exc:
            raise RuntimeError(
                "patchright não instalado. Rode:\n  pip install patchright\n"
                "Modo local também precisa do Google Chrome instalado."
            ) from exc
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            channel="chrome",
            headless=self.headless,
            no_viewport=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-quic",  # evita ERR_QUIC_PROTOCOL_ERROR com CF
                *self.extra_args,
            ],
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def get(self, url, *, wait_for_selector=None, timeout=180,
            cf_wait_s=60, scroll=True) -> str:
        """Carrega a url, espera o CF clear (título deixa de ser interstitial),
        opcionalmente espera um seletor e rola pra disparar lazy-load. Retorna o
        HTML renderizado. Uso de produção (não-interativo)."""
        self._ensure()
        page = self._page
        page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        deadline = time.time() + cf_wait_s
        while time.time() < deadline:
            t = page.title().lower()
            if not any(tok in t for tok in _CF_PENDING_TITLE):
                break
            time.sleep(1)
        if wait_for_selector:
            try:
                page.wait_for_selector(wait_for_selector, timeout=30000)
            except Exception:
                pass
        if scroll:
            try:
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                time.sleep(1.5)
            except Exception:
                pass
        return page.content()

    def poll_until(self, url, *, ready_substrings, max_wait_s=150, poll_s=2):
        """Vai pra url e fica re-lendo o conteúdo até: achar um marcador de PRONTO,
        bater num BLOCK TERMINAL, ou estourar max_wait_s. Pensado pro probe headful
        com resolução MANUAL do challenge (dá tempo do operador resolver na janela).

        Retorna (html, status) com status em {'ready', 'blocked', 'timeout'}."""
        self._ensure()
        self._page.goto(url, wait_until="domcontentloaded", timeout=60000)
        deadline = time.time() + max_wait_s
        ready_substrings = [s.lower() for s in ready_substrings]
        while time.time() < deadline:
            html = self._page.content()
            low = html.lower()
            if is_block_page(low):
                return html, "blocked"
            if any(s in low for s in ready_substrings):
                return html, "ready"
            time.sleep(poll_s)
        return self._page.content(), "timeout"

    def title(self) -> str:
        self._ensure()
        return self._page.title()

    def close(self):
        try:
            if self._ctx:
                self._ctx.close()
        except Exception:
            pass
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass
        self._ctx = self._page = self._pw = None
