#!/usr/bin/env python3
"""
run_liga_local.py — runner amigável pro adapter da Liga em modo local.

Pra rodar no SEU PC (em casa, IP residencial). Faz verificação de deps,
mostra mensagens claras de cada passo, e dispara o scan completo.

Uso:
    python run_liga_local.py

Configuração via flags (todas opcionais):
    --categorias 10,27          # só Booster Box + ETB (default: todas)
    --max-por-categoria 10      # 30 por padrão
    --janela                    # mostra a janela do Chrome (default: headless)
    --no-snapshot               # NÃO gerar as notas Markdown (snapshot é default:
                                # a entrega canônica é a tabela do snapshot.py)
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Repo dedicado: este arquivo vive na raiz do repo (sem subpasta sealed/).
SEALED = Path(__file__).resolve().parent
ROOT = SEALED


def _check_dep(import_name: str, pip_name: str | None = None) -> bool:
    try:
        __import__(import_name)
        return True
    except ImportError:
        print(f"  [faltando] módulo Python '{import_name}'")
        print(f"             instale com:  pip install {pip_name or import_name}")
        return False


def _check_chrome_windows() -> bool:
    """Procura Chrome em locais conhecidos no Windows. Não bloqueia em outros SOs."""
    if sys.platform != "win32":
        return True
    candidates = [
        Path(r"C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path(r"C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"),
        Path.home() / "AppData/Local/Google/Chrome/Application/chrome.exe",
    ]
    if any(p.exists() for p in candidates):
        return True
    print("  [aviso] não achei Google Chrome no Windows. Baixe em:")
    print("           https://www.google.com/chrome/")
    return False


def check_environment() -> bool:
    print("== Verificando ambiente ==")
    ok = True
    ok &= _check_dep("yaml", "pyyaml")
    ok &= _check_dep("bs4", "beautifulsoup4")
    ok &= _check_dep("lxml")
    ok &= _check_dep("openpyxl")
    ok &= _check_dep("cv2", "opencv-python-headless")
    ok &= _check_dep("numpy")
    ok &= _check_dep("patchright")
    ok &= _check_chrome_windows()
    if ok:
        print("  tudo presente.")
    else:
        print("\nInstale o que falta e rode novamente.")
    return ok


def main() -> int:
    # Console do Windows é cp1252 por padrão e quebra acentos do Liga/PT.
    # Não afeta CSV/XLSX (sempre UTF-8); só o que aparece no terminal.
    from lib.console import harden_stdout
    harden_stdout()

    p = argparse.ArgumentParser(description="Scanner da Liga Pokémon — modo local (Chrome real).")
    p.add_argument("--categorias", default="", help="Lista CSV de IDs de categoria (ex: 10,14,21,27).")
    p.add_argument("--max-por-categoria", type=int, default=None, help="Teto de produtos por categoria.")
    p.add_argument("--janela", action="store_true", help="Mostrar a janela do Chrome durante o scan.")
    p.add_argument("--snapshot", action=argparse.BooleanOptionalAction, default=True,
                   help="Gerar 2 notas Markdown em snapshots/ (técnica + didática). "
                        "LIGADO por default — é a entrega canônica (skill liga-sealed-scan); "
                        "use --no-snapshot só para debug do coletor.")
    p.add_argument("--skip-check", action="store_true", help="Pular verificação de dependências.")
    args = p.parse_args()

    if not args.skip_check and not check_environment():
        return 1

    # Monta config temporário com overrides do usuário
    import yaml  # type: ignore[import-untyped]
    base_cfg_path = SEALED / "config.yaml"
    cfg = yaml.safe_load(base_cfg_path.read_text(encoding="utf-8"))
    liga_cfg = cfg.setdefault("liga", {})
    liga_cfg["mode"] = "local"
    liga_cfg["headless"] = not args.janela
    if args.categorias:
        liga_cfg["categorias"] = [int(x.strip()) for x in args.categorias.split(",") if x.strip()]
    if args.max_por_categoria:
        liga_cfg["max_products_per_category"] = args.max_por_categoria

    tmp_cfg = SEALED / ".config_local_run.yaml"
    tmp_cfg.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")

    print("\n== Iniciando scan da Liga (modo local — Chrome real) ==")
    print(f"  Categorias       : {liga_cfg.get('categorias')}")
    print(f"  Máx por categoria: {liga_cfg.get('max_products_per_category')}")
    print(f"  Janela visível   : {args.janela}")
    print()

    rc = subprocess.call(
        [sys.executable, str(SEALED / "sealed_arbitrage_scanner.py"),
         "--source", "liga", "--config", str(tmp_cfg)],
        cwd=ROOT,
    )
    if rc != 0:
        return rc

    if args.snapshot:
        print("\n== Gerando snapshots Markdown ==")
        rc = subprocess.call(
            [sys.executable, str(SEALED / "scripts" / "snapshot.py")],
            cwd=ROOT,
        )
        if rc == 0:
            print("  → também gerando versão didática (humano-friendly)...")
            rc = subprocess.call(
                [sys.executable, str(SEALED / "scripts" / "snapshot_friendly.py")],
                cwd=ROOT,
            )
    return rc


if __name__ == "__main__":
    sys.exit(main())
