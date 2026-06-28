#!/usr/bin/env python3
"""
liga_adapter.py — adapter da Liga Pokémon para o scanner de selados.

Dois modos de acesso, escolhidos por config['liga']['mode'] ou env LIGA_MODE:

  mode=local       (DEFAULT)  Usa patchright + Google Chrome real, num
                              perfil persistente. Roda do seu PC (IP
                              residencial), passa o Cloudflare da Liga
                              sem proxy. Requer Chrome instalado e
                              `pip install patchright`. Sem custo.

  mode=scraperapi             Roteia tudo via api.scraperapi.com. Útil
                              quando o adapter roda em servidor (IP
                              datacenter, bloqueado pela Liga). Requer
                              SCRAPERAPI_KEY e premium=true (a Liga é
                              "protected domain"). Free tier consome
                              rápido (~25-50 credits por render).

Anti-scraping de preço da Liga: cada dígito é uma <div> com classe
ofuscada cujo CSS aponta para um JPG via background-position. Nome
das classes e URL do sprite mudam a cada render, mas a fonte é estável.
Decodificação por template matching com 10 templates fixos
(sealed/data/liga_digit_templates/{0..9}.png), correlação ~1.000.

Mapeamento PT→EN: tipo de produto ("Coleção Treinador Avançado" →
"Elite Trainer Box") e nome de set ("Caos Ascendente" → "Chaos
Rising"). Sem isso o matcher do scanner rejeita tudo por sem_match
(o registry vive em inglês).

Categorias da Liga mapeadas em CATEGORY_PRODUCT_TYPE / DEFAULT_CATEGORIES:
10/14/21/25/26/27/28/38 (boxes, bundles, packs, blisters, decks, ETBs,
collection boxes, kits).
"""
from __future__ import annotations

import functools
import html as html_lib
import os
import re
import time
import urllib.parse
import urllib.request
from pathlib import Path

SCRAPERAPI_BASE = "http://api.scraperapi.com/"
LIGA_BASE = "https://www.ligapokemon.com.br"

# Liga PT name (substring) -> canonical product_type used by the scanner registry.
CATEGORY_PRODUCT_TYPE = {
    "caixa de booster": "Booster Box",
    "coleção treinador avançado": "Elite Trainer Box",
    "colecao treinador avancado": "Elite Trainer Box",
    "combo de pacotes": "Booster Bundle",
    "booster avulso": "Booster Pack",
    "blister unitário": "Blister",
    "blister triplo": "Blister",
    "blister quádruplo": "Blister",
    "blister": "Blister",
    "box coleção": "Collection Box",
    "box colecao": "Collection Box",
    "baralho pré construído": "Battle Deck",
    "kit": "Kit",
    "deck selado": "Theme Deck",
    "lata": "Tin",
    "pacote pré-lançamento": "Build & Battle Box",
    "pacote pre-lancamento": "Build & Battle Box",
    "pré-lançamento": "Build & Battle Box",
    "pre-lancamento": "Build & Battle Box",
}

# Categories to scrape. Numbers come from the categ= URL param in
# ?view=cards/search&card=categ%3D<N>+searchprod%3D1.
DEFAULT_CATEGORIES = {
    10: "Caixas de Boosters",
    14: "Pacotes / Fat Packs",
    21: "Boosters Avulsos",
    24: "Latas",
    25: "Blisters",
    26: "Decks Selados",
    27: "Coleção Treinador Avançado",
    28: "Box Colecionável",
    38: "Kits",
    57: "Pacote Pré-Lançamento",
}

# Idiomas (img title) reconhecidos. Used to populate listing['lang'].
LANG_MAP = {
    "Inglês": "EN",
    "Ingles": "EN",
    "Português": "PT-BR",
    "Portugues": "PT-BR",
    "Japonês": "JA",
    "Japones": "JA",
    "Chinês": "ZH",
    "Coreano": "KO",
    "Alemão": "DE",
    "Francês": "FR",
    "Espanhol": "ES",
    "Italiano": "IT",
}

# Marker found at the start of product names: "(ING) ...", "(PT-BR) ...".
NAME_PREFIX_LANG = {
    "ING": "EN",
    "PT-BR": "PT-BR",
    "JAP": "JA",
    "CHN": "ZH",
    "COR": "KO",
    "ALE": "DE",
    "FRA": "FR",
    "ESP": "ES",
    "ITA": "IT",
}

# Tradução Liga (PT) -> set name canônico (EN) do registry. O matcher do
# scanner casa por palavra-chave em inglês — o título da Liga vem em PT,
# então o adapter injeta o nome em inglês no title da listing.
SET_TRANSLATE_PT_TO_EN = {
    # Megaevolução (ME) series
    "Caos Ascendente": "Chaos Rising",
    "Fogo Fantasmagórico": "Phantasmal Flames",
    "Equilíbrio Perfeito": "Perfect Order",
    "Heróis Excelsos": "Ascended Heroes",
    "Pitch Black": "Pitch Black",
    # Scarlet & Violet (SV) series
    "Forças Temporais": "Temporal Forces",
    "Máscara do Crepúsculo": "Twilight Masquerade",
    "Mascarada Crepuscular": "Twilight Masquerade",
    "Coroa Estelar": "Stellar Crown",
    "Fagulhas Impetuosas": "Surging Sparks",
    "Evoluções Prismáticas": "Prismatic Evolutions",
    "Amigos de Jornada": "Journey Together",
    "Rivais Predestinados": "Destined Rivals",
    "Destinos de Paldea": "Paldean Fates",
    # 151 special
    "Pokémon 151": "Pokémon 151",
    "151": "Pokémon 151",
}

# Tradução de tipo de produto Liga (PT) -> termo que o matcher reconhece.
TYPE_TRANSLATE_PT_TO_EN = {
    "Caixa de Booster": "Booster Box",
    "Coleção Treinador Avançado": "Elite Trainer Box",
    "Combo de Pacotes": "Booster Bundle",
    "Booster Avulso": "Booster Pack",
    "Blister Unitário": "Blister",
    "Blister Triplo": "Blister",
    "Blister Quádruplo": "Blister",
    "Box Coleção": "Collection Box",
    "Baralho Pré Construído": "Battle Deck",
    "Deck Selado": "Theme Deck",
}


def _translate_title(name: str) -> str:
    """Enriquece o título PT da Liga com termos EN para o matcher casar.

    '(ING) Coleção Treinador Avançado - Megaevolução 4 - Caos Ascendente'
      -> 'Chaos Rising Elite Trainer Box (English) — original: (ING) ...'
    """
    out = name
    for pt, en in TYPE_TRANSLATE_PT_TO_EN.items():
        if pt.lower() in name.lower():
            out = out.replace(pt, en) if pt in out else out + f" [{en}]"
            break
    for pt, en in SET_TRANSLATE_PT_TO_EN.items():
        if pt.lower() in name.lower():
            out = out.replace(pt, en) if pt in out else out + f" [{en}]"
            break
    lang = _name_lang(name)
    if lang == "EN" and "English" not in out:
        out += " (English)"
    return out


# --------------------------------------------------------------------------
# Configuração / helpers
# --------------------------------------------------------------------------
def _load_dotenv_if_present() -> None:
    """Carrega .env da raiz do repo se existir. Não sobrescreve env vars já setadas."""
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"\''))


def _get_api_key(liga_cfg: dict) -> str:
    _load_dotenv_if_present()
    key = os.environ.get("SCRAPERAPI_KEY") or liga_cfg.get("scraperapi_key")
    if not key:
        raise RuntimeError(
            "SCRAPERAPI_KEY não configurada (modo scraperapi). Defina em .env "
            "na raiz do repo, exporte como env var, ou coloque em "
            "liga.scraperapi_key no config.yaml. Cadastro grátis em "
            "https://www.scraperapi.com (free tier ~1000 req/mês). Pra rodar "
            "sem custo, use mode=local (default) com Chrome instalado."
        )
    return key


# --------------------------------------------------------------------------
# Fetcher abstrato — local (patchright + Chrome) ou scraperapi
# --------------------------------------------------------------------------
class _Fetcher:
    def get(self, url: str, *, render: bool = False,
            wait_for_selector: str | None = None, timeout: int = 180) -> bytes:
        raise NotImplementedError

    def close(self) -> None:
        pass


class _ScraperAPIFetcher(_Fetcher):
    """GET via ScraperAPI. Liga é "protected domain" → exige premium=true."""

    def __init__(self, api_key: str, max_retries: int = 2):
        self.api_key = api_key
        self.max_retries = max_retries

    def get(self, url, *, render=False, wait_for_selector=None, timeout=180):
        params = {"api_key": self.api_key, "url": url, "country_code": "br"}
        if render:
            params["render"] = "true"
            params["premium"] = "true"  # Liga é protected domain
        if wait_for_selector:
            params["wait_for_selector"] = wait_for_selector
        api_url = SCRAPERAPI_BASE + "?" + urllib.parse.urlencode(params)
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                with urllib.request.urlopen(api_url, timeout=timeout) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                last_err = e
                if e.code not in (429, 500, 502, 503, 504):
                    raise
                if attempt < self.max_retries:
                    time.sleep(2 ** attempt * 2)
        raise last_err  # type: ignore[misc]


class _LocalChromeFetcher(_Fetcher):
    """patchright + Chrome real, perfil persistente.

    Pensado pra rodar do PC do usuário (IP residencial). Passa o Cloudflare
    da Liga sem proxy. Requer Chrome instalado e `pip install patchright`.

    O contexto Chromium é mantido enquanto o fetcher viver — abrir/fechar
    1 vez por scan, várias páginas reaproveitam a mesma sessão.
    """

    def __init__(self, headless: bool = True, profile_dir: str | None = None):
        self.headless = headless
        self.profile_dir = profile_dir or str(Path.home() / ".pw_profile_liga_sealed")
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
                "patchright não instalado. Rode:\n"
                "  pip install patchright\n"
                "Modo local também precisa do Google Chrome instalado. "
                "Alternativa: use mode=scraperapi (config.liga.mode)."
            ) from exc
        Path(self.profile_dir).mkdir(exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            channel="chrome",
            headless=self.headless,
            no_viewport=True,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--disable-quic",  # evita ERR_QUIC_PROTOCOL_ERROR com CF
            ],
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()

    def get(self, url, *, render=False, wait_for_selector=None, timeout=180):
        self._ensure()
        page = self._page
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout * 1000)
        except Exception:
            # Uma navegação que falha (ERR_HTTP_RESPONSE_CODE_FAILURE, timeout)
            # dispara uma navegação de erro (chrome-error://) que ainda está
            # assentando quando o próximo goto dispara -> "interrupted by another
            # navigation", que cascateia e derruba a listagem de categorias
            # inteiras (visto 2026-06-27: 1 blister ruim na categ 25 derrubou
            # 26/27/28/38/57). Deixa a página de erro assentar antes de re-erguer
            # pra o próximo get() começar limpo. NÃO fechar a page (fecha o
            # contexto inteiro e mata os cookies CF).
            try:
                page.wait_for_load_state("domcontentloaded", timeout=8000)
            except Exception:
                pass
            raise
        # Espera o Cloudflare clear (titulo deixa de ser "Just a moment...")
        deadline = time.time() + 60
        while time.time() < deadline:
            t = page.title().lower()
            if "moment" not in t and "just a" not in t and "access denied" not in t:
                break
            time.sleep(1)
        if wait_for_selector:
            try:
                page.wait_for_selector(wait_for_selector, timeout=30000)
            except Exception:
                pass
        # Pequena rolagem pra disparar lazy-load (sellers, imagens)
        try:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
            time.sleep(1.5)
        except Exception:
            pass
        return page.content().encode("utf-8", errors="replace")

    def fetch_binary(self, url: str, timeout: int = 60) -> bytes:
        """Baixa um arquivo binário (sprite JPG) usando a sessão Chromium —
        herda cookies de Cloudflare automaticamente."""
        self._ensure()
        resp = self._ctx.request.get(url, timeout=timeout * 1000)
        return resp.body()

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


def _make_fetcher(liga_cfg: dict) -> _Fetcher:
    """Cria o fetcher conforme config.liga.mode (env LIGA_MODE também)."""
    _load_dotenv_if_present()
    mode = (os.environ.get("LIGA_MODE")
            or liga_cfg.get("mode") or "local").lower()
    if mode == "scraperapi":
        return _ScraperAPIFetcher(_get_api_key(liga_cfg))
    if mode == "local":
        return _LocalChromeFetcher(headless=liga_cfg.get("headless", True))
    raise ValueError(f"liga.mode desconhecido: {mode!r}. Use 'local' ou 'scraperapi'.")


# --------------------------------------------------------------------------
# Sprite de dígitos — decoder do anti-scraping de preço
# --------------------------------------------------------------------------
@functools.lru_cache(maxsize=2)
def _load_digit_templates(kind: str = "price"):
    """Lê os templates de dígitos e devolve dict digit -> list[ndarray].

    kind='price' → sprite imgnum (fonte usada nas .new-price)
    kind='qty'   → sprite imgunid (fonte usada nas .quantity-with-image)

    Sprites usam glyphs visualmente similares mas tipograficamente distintos
    (font/anti-aliasing); aplicar templates do sprite errado degrada
    template-matching de ~95% pra ~64% per-class — daí o split em 2 dirs.

    Cada dígito pode ter MÚLTIPLOS templates (variantes do mesmo glyph). O
    arquivo canônico é `{d}.png` (obrigatório); variantes adicionais como
    `{d}b.png`, `{d}c.png` são opcionais. O decoder testa todas e usa o
    melhor score. Útil pra dígitos onde Liga renderiza com pequena variação
    de anti-aliasing entre células do mesmo sprite (e.g., qty/1b.png cobre
    a variante de '1' que nIkOsZ usa, distinta de aJwVlZ).
    """
    import cv2  # local import — só carrega quando o adapter rodar de verdade
    subdir = "liga_digit_templates" if kind == "price" else "liga_digit_templates_qty"
    tpl_dir = Path(__file__).parent / "data" / subdir
    out: dict[str, list] = {}
    for d in "0123456789":
        primary = tpl_dir / f"{d}.png"
        img = cv2.imread(str(primary), cv2.IMREAD_GRAYSCALE)
        if img is None:
            raise RuntimeError(f"Template canônico ausente: {primary}")
        out[d] = [img]
        # Variantes opcionais: 1b.png, 1c.png, ...
        for suffix in "bcde":
            extra = tpl_dir / f"{d}{suffix}.png"
            if extra.exists():
                v = cv2.imread(str(extra), cv2.IMREAD_GRAYSCALE)
                if v is not None:
                    out[d].append(v)
    return out


def _fetch_sprite_decoded(sprite_url: str, fetcher: _Fetcher):
    """Baixa o sprite via fetcher e devolve ndarray gray.

    Cache em memória por URL (sprite muda a cada render mas pode repetir
    durante o mesmo scan). Sem `@lru_cache` porque o fetcher não é hasheável.
    """
    cache = _fetch_sprite_decoded.__dict__.setdefault("_cache", {})
    if sprite_url in cache:
        return cache[sprite_url]
    import cv2
    import numpy as np
    if isinstance(fetcher, _LocalChromeFetcher):
        data = fetcher.fetch_binary(sprite_url)
    else:
        data = fetcher.get(sprite_url, timeout=60)
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise RuntimeError(f"Sprite inválido em {sprite_url}")
    cache[sprite_url] = img
    return img


def _decode_class_to_digit(sprite, x: int, y: int, templates) -> str:
    """Croppa 7x15 do sprite em (x, y) e devolve o dígito com maior correlação.

    `templates` agora é dict[digit, list[ndarray]] — testa todas variantes
    do mesmo dígito e usa o melhor score (cobre glyphs com pequena variação).
    """
    import cv2
    cell = sprite[y:y + 15, x:x + 7]
    if cell.shape != (15, 7):
        return "?"
    best_d, best_s = "?", -1.0
    for d, tpl_list in templates.items():
        for tpl in tpl_list:
            s = float(cv2.matchTemplate(cell, tpl, cv2.TM_CCOEFF_NORMED).max())
            if s > best_s:
                best_s, best_d = s, d
    # Score >= 0.85 é confiável (visto na prática: ~1.000 quando bate).
    return best_d if best_s >= 0.85 else "?"


def _build_class_digit_map(page_html: str, fetcher: _Fetcher) -> dict[str, str]:
    """Lê todas as regras CSS inline e devolve {classe: dígito}.

    A Liga usa DOIS sprites distintos com classes obfuscadas separadas:
      - imgnum  (5-letter digit classes) → preço     [.mXxQb wrapper]
      - imgunid (6-letter digit classes) → quantidade [.qGoMk wrapper]
    Disambiguação por COMPRIMENTO da classe (estável; engine de obfuscação
    da Liga gera 5 chars pro sprite de preço, 6 pro de qty).
    """
    class_to_digit: dict[str, str] = {}
    for folder, class_len, kind in [("imgnum", 5, "price"), ("imgunid", 6, "qty")]:
        m = re.search(rf"background-image:url\(([^)]+/{folder}/[^)]+)\)", page_html)
        if not m:
            continue
        sprite_url = m.group(1).strip()
        if sprite_url.startswith("//"):
            sprite_url = "https:" + sprite_url
        sprite = _fetch_sprite_decoded(sprite_url, fetcher)
        templates = _load_digit_templates(kind)
        pat = re.compile(
            rf"\.([a-zA-Z]{{{class_len}}})\s*\{{\s*background-position\s*:\s*(-?\d+)px\s+(-?\d+)px"
        )
        for cmatch in pat.finditer(page_html):
            cls = cmatch.group(1)
            x, y = -int(cmatch.group(2)), -int(cmatch.group(3))
            class_to_digit[cls] = _decode_class_to_digit(sprite, x, y, templates)
    return class_to_digit


def _decode_qty_block(qty_div, class_to_digit: dict[str, str]) -> int | None:
    """Decodifica '.quantity-with-image' (após o 'de ') em qty disponível.

    HTML:
      <div class="quantity-with-image">
        <div class="imgnum-unid">de </div>
        <div class="qGoMk vAzFoZ rPeBr"> </div>  ← dígito (qGoMk = wrapper, vAzFoZ = posição)
        <div class="qGoMk rPeBr nIkOsZ"> </div>  ← dígito 2 (qty >9 → 2 divs)
      </div>

    Devolve int se todos dígitos decodificados; None caso contrário (NÃO 0,
    NÃO 1 — diferenciamos "vendedor sem qty parseada" de qty real).
    """
    if qty_div is None:
        return None
    s = ""
    for child in qty_div.find_all("div", recursive=False):
        cls_list = child.get("class") or []
        # Pula o label "de "
        if "imgnum-unid" in cls_list:
            continue
        for c in cls_list:
            if c in class_to_digit:
                s += class_to_digit[c]
                break
    if not s or "?" in s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _decode_price_block(price_div, class_to_digit: dict[str, str]) -> float | None:
    """Reconstrói o preço caminhando pelos <div> filhos da .new-price."""
    s = ""
    for child in price_div.find_all("div", recursive=False):
        cls_list = child.get("class") or []
        # Ignora a label "R$"
        if "imgnum-monet" in cls_list:
            continue
        # Separador decimal: <div style="background-image:...marketplace/v2.png">
        style = child.get("style", "") or ""
        if "v2.png" in style:
            s += ","
            continue
        # Senão, achar a classe ofuscada e mapear pra dígito
        for c in cls_list:
            if c in class_to_digit:
                s += class_to_digit[c]
                break
    s = s.replace(".", "").replace(",", ".").strip()
    if not s or "?" in s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


# --------------------------------------------------------------------------
# Parse: listagem de categoria + página de produto
# --------------------------------------------------------------------------
def _category_url(categ: int) -> str:
    return f"{LIGA_BASE}/?view=cards/search&tipo=1&card=categ%3D{categ}+searchprod%3D1"


def _product_url(pcode: int | str) -> str:
    return f"{LIGA_BASE}/?view=prod/view&pcode={pcode}"


def parse_category_products(html_text: str) -> list[dict]:
    """Extrai (pcode, nome) dos produtos listados numa página de categoria."""
    out: list[dict] = []
    seen = set()
    # href="/?view=prod/view&amp;pcode=NNNN&amp;prod=NAME"
    for m in re.finditer(r'href="(/\?view=prod/view&(?:amp;)?pcode=(\d+)[^"]*)"', html_text):
        href, pcode = m.group(1), m.group(2)
        if pcode in seen:
            continue
        seen.add(pcode)
        # Decode entities, extract prod=
        href_decoded = html_lib.unescape(href)
        prod_match = re.search(r"[?&]prod=([^&]+)", href_decoded)
        name = urllib.parse.unquote(prod_match.group(1)) if prod_match else ""
        out.append({
            "pcode": int(pcode),
            "name": name,
            "url": LIGA_BASE + href_decoded,
        })
    return out


def _name_lang(name: str) -> str:
    """'(ING) Booster Box ...' -> 'EN'."""
    m = re.match(r"\s*\(([A-Z\-]+)\)", name)
    if not m:
        return ""
    return NAME_PREFIX_LANG.get(m.group(1), "")


def _name_product_type(name: str) -> str:
    """'Caixa de Booster - ...' -> 'Booster Box'."""
    n = name.lower()
    # Remover o prefixo de idioma
    n = re.sub(r"^\s*\([a-z\-]+\)\s*", "", n)
    for needle, ptype in CATEGORY_PRODUCT_TYPE.items():
        if needle in n:
            return ptype
    return ""


def parse_product_page(html_text: str, product_url: str, fetcher: _Fetcher) -> list[dict]:
    """Extrai todas as ofertas (vendedor/preço/idioma/condição) de uma página de produto."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html_text, "lxml")

    # Título: pega do og:title/<title>, depois traduz PT->EN pra o matcher
    # do scanner conseguir casar com os SKUs do registry (que estão em inglês).
    title_tag = soup.select_one('meta[property="og:title"]')
    product_title_raw = ""
    if title_tag and title_tag.get("content"):
        product_title_raw = title_tag["content"].split("|")[0].strip()
    elif soup.title:
        product_title_raw = soup.title.get_text().split("|")[0].strip()
    product_title = _translate_title(product_title_raw)

    # Decoder das classes ofuscadas (sprite específico desta página)
    class_to_digit = _build_class_digit_map(html_text, fetcher)

    listings: list[dict] = []
    for store in soup.select("div.store"):
        price_div = store.select_one(".new-price")
        if not price_div:
            continue
        price = _decode_price_block(price_div, class_to_digit)
        if price is None:
            continue
        lang_img = store.select_one(".lang img")
        lang_label = (lang_img.get("title", "") if lang_img else "").strip()
        cond_el = store.select_one(".condition")
        condition = cond_el.get_text(strip=True) if cond_el else ""
        seller_link = store.select_one('a[href*="mp/showcase"]')
        seller_href = seller_link.get("href", "") if seller_link else ""
        seller_id_match = re.search(r"id=(\d+)", seller_href)
        seller = f"loja#{seller_id_match.group(1)}" if seller_id_match else ""

        # Quantidade disponível (anti-scrape, mesmo decoder mas sprite separado)
        qty_div = store.select_one(".quantity-with-image")
        qty_avail = _decode_qty_block(qty_div, class_to_digit)

        listings.append({
            "title": product_title,
            "price_brl": price,
            "seller": seller,
            "url": product_url,
            "lang": LANG_MAP.get(lang_label, lang_label),
            "condition": condition,
            "qty_avail": qty_avail,
        })
    return listings


# --------------------------------------------------------------------------
# Orquestração
# --------------------------------------------------------------------------
def fetch_listings(config: dict) -> list[dict]:
    """Coleta anúncios de selado da Liga Pokémon.

    Itera pelas categorias em config['liga']['categorias'] (default: todas em
    DEFAULT_CATEGORIES). Pra cada produto inglês, busca a página e extrai as
    ofertas de vendedores.
    """
    liga_cfg = config.get("liga", {}) or {}
    delay = liga_cfg.get("delay_seconds", 1.0)
    max_products_per_cat = liga_cfg.get("max_products_per_category", 30)
    keep_langs = set(liga_cfg.get("keep_languages") or ["EN"])
    categories = liga_cfg.get("categorias") or list(DEFAULT_CATEGORIES.keys())

    fetcher = _make_fetcher(liga_cfg)
    out: list[dict] = []
    seen_pcodes: set[int] = set()
    try:
        for categ in categories:
            cat_name = DEFAULT_CATEGORIES.get(categ, f"categ={categ}")
            print(f"  [liga] categoria {categ} ({cat_name}) — listando produtos...")
            try:
                raw = fetcher.get(
                    _category_url(categ),
                    render=True, wait_for_selector='a[href*="prod/view"]',
                )
                cat_html = raw.decode("utf-8", errors="replace")
            except Exception as exc:
                print(f"    [aviso] falha ao listar categoria {categ}: {exc}")
                continue
            products = parse_category_products(cat_html)
            filtered = [p for p in products if _name_lang(p["name"]) in keep_langs]
            print(f"    produtos: {len(products)} ({len(filtered)} {sorted(keep_langs)})")
            for prod in filtered[:max_products_per_cat]:
                if prod["pcode"] in seen_pcodes:
                    continue
                seen_pcodes.add(prod["pcode"])
                try:
                    raw = fetcher.get(
                        prod["url"],
                        render=True, wait_for_selector=".new-price",
                    )
                    page_html = raw.decode("utf-8", errors="replace")
                except Exception as exc:
                    print(f"      [aviso] pcode={prod['pcode']} falhou: {exc}")
                    continue
                listings = parse_product_page(page_html, prod["url"], fetcher)
                ptype = _name_product_type(prod["name"])
                for i, lst in enumerate(listings, 1):
                    lst["id"] = f"LIGA-{prod['pcode']}-{i}"
                    lst["source"] = "liga"
                    lst["product_type_hint"] = ptype
                    lst["pcode"] = prod["pcode"]
                    out.append(lst)
                if delay:
                    time.sleep(delay)
    finally:
        fetcher.close()
    return out


# --------------------------------------------------------------------------
# CLI standalone — útil pra debug
# --------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys
    from lib.console import harden_stdout
    harden_stdout()  # console Windows cp1252 quebra em títulos Liga/PT-BR
    cfg_path = Path(__file__).parent / "config.yaml"
    cfg = {}
    if cfg_path.exists():
        import yaml
        cfg = yaml.safe_load(cfg_path.read_text()) or {}
    # Limita a 1 categoria + poucos produtos pra teste rápido
    cfg.setdefault("liga", {})
    cfg["liga"]["categorias"] = [27]  # ETB
    cfg["liga"]["max_products_per_category"] = 3
    listings = fetch_listings(cfg)
    print(f"\n{len(listings)} listagens:")
    for ls in listings[:15]:
        print(f"  {ls['id']}  R$ {ls['price_brl']:7.2f}  {ls['lang']:<5}  {ls['title'][:70]}")
