#!/usr/bin/env python3
"""probe_olx_local.py — teste empírico decisivo: o OLX passa com Chrome REAL?

Fase 0 do plano zero-capital da OLX. Abre uma busca do OLX num Google Chrome
real + perfil persistente (IP residencial do operador) — o MESMO caminho que
destravou a Liga. Diferente do urllib puro (que leva block terminal 403), aqui
o browser tem fingerprint real, roda JS e guarda o cookie cf_clearance.

Se vier challenge "Just a moment"/Turnstile na janela, RESOLVA manualmente
(clique/aguarde) — o probe fica pol-ando até 150s e o clearance fica salvo no
perfil ~/.pw_profile_olx pra próximas execuções.

Saída: diz se a busca renderizou (__NEXT_DATA__ + anúncios parseados) ou se é
block terminal mesmo com browser real — o que decide Fase 1A (porta o adapter)
vs Fase 1B (escalada de stealth).

Uso:
    python probe_olx_local.py                 # headful (default; pra resolver challenge)
    python probe_olx_local.py --headless      # depois de aquecido, testar sem janela
    python probe_olx_local.py --query "elite trainer box pokemon ingles"
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from lib.browser import LocalChromeFetcher, is_block_page
from lib.console import harden_stdout

BASE = "https://www.olx.com.br/brasil?q="
PROFILE = str(Path.home() / ".pw_profile_olx")


def main() -> int:
    harden_stdout()
    p = argparse.ArgumentParser(description="Probe local da OLX (Chrome real)")
    p.add_argument("--query", default="booster box pokemon ingles")
    p.add_argument("--headless", action="store_true",
                   help="sem janela (use só depois de aquecer o perfil headful)")
    p.add_argument("--wait", type=int, default=150,
                   help="segundos pra resolver challenge manualmente (default 150)")
    args = p.parse_args()

    url = BASE + urllib.parse.quote_plus(args.query)
    print("=" * 68)
    print("  PROBE OLX LOCAL — Chrome real + perfil persistente")
    print("=" * 68)
    print(f"  perfil : {PROFILE}")
    print(f"  query  : {args.query!r}")
    print(f"  url    : {url}")
    print(f"  modo   : {'headless' if args.headless else 'HEADFUL (resolva o challenge na janela, se vier)'}")
    print("-" * 68)

    fetcher = LocalChromeFetcher(profile_dir=PROFILE, headless=args.headless)
    try:
        html, status = fetcher.poll_until(
            url, ready_substrings=["__next_data__"], max_wait_s=args.wait,
        )
        title = fetcher.title()
    except Exception as exc:
        print(f"  ERRO ao abrir o browser: {type(exc).__name__}: {exc}")
        fetcher.close()
        return 2
    finally:
        # mantém aberto o suficiente pra ler o resultado, depois fecha
        pass

    print(f"  título da página : {title!r}")
    print(f"  status do poll   : {status}")
    print(f"  tamanho do HTML  : {len(html)} chars")
    print(f"  block terminal?  : {is_block_page(html)}")
    has_next = "__next_data__" in html.lower()
    print(f"  __NEXT_DATA__?   : {has_next}")

    n_ads = None
    if has_next:
        try:
            from olx_adapter import parse_search_results
            ads = parse_search_results(html)
            n_ads = len(ads)
            print(f"  anúncios parseados: {n_ads}")
            for a in ads[:5]:
                print(f"    - R$ {a['price_brl']:>9.2f}  {a['title'][:60]}")
        except Exception as exc:
            print(f"  [aviso] parse falhou: {type(exc).__name__}: {exc}")

    print("-" * 68)
    if status == "ready" and n_ads:
        print("  >>> VEREDITO: PASSOU. Chrome real atravessa o OLX. → Fase 1A (portar adapter).")
        verdict = 0
    elif status == "ready" and has_next and not n_ads:
        print("  >>> VEREDITO: renderizou (__NEXT_DATA__) mas 0 anúncios — checar query/parse.")
        verdict = 0
    elif status == "blocked" or is_block_page(html):
        print("  >>> VEREDITO: BLOCK TERMINAL mesmo com Chrome real. → Fase 1B (CDP/mobile/firecrawl).")
        verdict = 1
    else:
        print("  >>> VEREDITO: TIMEOUT sem render nem block claro — challenge não resolvido a tempo?")
        print("      Rode de novo headful e resolva o challenge na janela.")
        verdict = 3
    print("=" * 68)

    fetcher.close()
    return verdict


if __name__ == "__main__":
    sys.exit(main())
