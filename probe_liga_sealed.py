#!/usr/bin/env python3
"""
probe_liga_sealed.py — descoberta da estrutura das páginas de PRODUTO SELADO
na Liga Pokémon.

POR QUE ESTE PROBE EXISTE
  A Liga está atrás de CloudFlare. De um IP de datacenter o CF responde 403
  (confirmado). Só limpa com Chrome real + perfil persistente. Logo, ESTE
  PROBE RODA NA SUA MÁQUINA, não no ambiente remoto — exatamente como os
  probe_liga_*.py da raiz do repo, que mapearam as páginas de SINGLES.

  Os probes da raiz cobrem só singles (?view=cards/...). A estrutura das
  páginas de selado é desconhecida — este probe a revela.

O QUE FAZ
  Navega até a URL que você passar, espera o CloudFlare limpar, salva o HTML
  e imprime um mapa da página: título, tokens de classe mais comuns, seletores
  candidatos e padrões de preço. Com isso ajustamos o parser do liga_adapter.py.

USO (na sua máquina)
    pip install patchright beautifulsoup4 lxml
    patchright install chrome
    python probe_liga_sealed.py "<URL de uma página de produto selado>"
    python probe_liga_sealed.py "<URL>" --headful   # se o CF não limpar headless

COMO ACHAR UMA URL DE SELADO
  Abra a Liga no navegador, procure um booster box / ETB lacrado, e copie a
  URL — tanto da página de busca/listagem quanto da página do produto.
"""
import re
import sys
import time
from collections import Counter
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from patchright.sync_api import sync_playwright
    from bs4 import BeautifulSoup
except ImportError:
    print("ERRO: instale as dependências do probe:")
    print("  pip install patchright beautifulsoup4 lxml")
    print("  patchright install chrome")
    sys.exit(1)

PROFILE_DIR = (Path.home() / ".pw_profile_liga_sealed").resolve()
PROFILE_DIR.mkdir(exist_ok=True)


def wait_until_cf_clears(page, max_wait=90):
    start = time.time()
    while time.time() - start < max_wait:
        title = page.title().lower()
        if "momento" not in title and "just a moment" not in title:
            return True
        time.sleep(1.5)
    return False


def probe(page, url):
    print(f"\n{'=' * 70}\n  {url}\n{'=' * 70}")
    page.goto(url, wait_until="domcontentloaded", timeout=120000)
    print(f"  após goto      : title={page.title()!r}")
    cleared = wait_until_cf_clears(page)
    print(f"  CloudFlare     : {'limpo' if cleared else 'NÃO limpou'} | title={page.title()!r}")
    if not cleared:
        print("  -> tente novamente com --headful")
    try:
        page.wait_for_load_state("networkidle", timeout=30000)
    except Exception:
        print("  [aviso] networkidle timeout")
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    time.sleep(3)

    html = page.content()
    soup = BeautifulSoup(html, "lxml")
    print(f"\n  HTML           : {len(html):,} bytes")
    print(f"  título página  : {soup.title.string if soup.title else '(nenhum)'}")
    print(f"  URL final      : {page.url}")

    # Hipótese: páginas de selado reaproveitam o widget de listagem de
    # vendedores dos singles (div.store / div.lang / div.new-price).
    candidates = [
        "div.store", "div.stores", "[class*='store']",
        "div.lang img", "img[title]",
        "div.quality", "div.quality_nm", "[class*='quality']",
        "div.new-price", "div.old-price", "div.price",
        "[class*='price']", "[class*='preco']",
        "a[href*='view=']", "h1",
        "[class*='produto']", "[class*='lacrado']", "[class*='sealed']", "[class*='seller']",
    ]
    print("\n  Seletores candidatos:")
    for sel in candidates:
        n = len(soup.select(sel))
        print(f"   {'->' if n else '  '} {sel:30s} {n}")

    prices = re.findall(r"R\$\s*[\d.,]+", html)
    print(f"\n  Padrões R$     : {len(prices)} | amostra: {prices[:15]}")

    classes = Counter()
    for el in soup.find_all(class_=True):
        for c in el.get("class") or []:
            classes[c] += 1
    print("\n  Top 40 tokens de classe:")
    for c, n in classes.most_common(40):
        print(f"   {n:5d}  {c}")

    out = Path("probe_liga_sealed_dump.html")
    out.write_text(html, encoding="utf-8")
    print(f"\n  HTML salvo em  : {out.resolve()}")
    print("  -> Cole a saída acima (ou o HTML) no chat para ajustarmos o parser.")


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    headful = "--headful" in sys.argv
    if not args:
        print(__doc__)
        print("ERRO: passe a URL de uma página de produto selado da Liga.")
        sys.exit(2)
    print(f"Modo: patchright {'headful' if headful else 'headless'} | perfil={PROFILE_DIR}")
    with sync_playwright() as pw:
        context = pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            channel="chrome",
            headless=not headful,
            no_viewport=True,
        )
        page = context.pages[0] if context.pages else context.new_page()
        try:
            probe(page, args[0])
        finally:
            context.close()


if __name__ == "__main__":
    main()
