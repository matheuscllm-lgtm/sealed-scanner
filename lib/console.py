"""Console encoding hardening for Windows cp1252 terminals.

O console do Windows usa cp1252 por padrão. Títulos de anúncios do Liga/PT-BR
(e ocasionais bytes inválidos vindos do scrape, vistos como U+FFFD ``�``) não
mapeiam pra cp1252 e estouram ``UnicodeEncodeError: 'charmap' codec`` no
primeiro ``print()`` que toca o título — derrubando o scan inteiro.

Este helper força UTF-8 com ``errors='replace'`` em stdout/stderr. Não afeta
CSV/XLSX, que já são escritos em UTF-8 diretamente. É idempotente e seguro de
chamar no início de qualquer entrypoint (inclusive fora do Windows, onde é
essencialmente no-op).
"""
from __future__ import annotations

import os
import sys


def harden_stdout() -> None:
    """Reconfigura stdout/stderr pra UTF-8 (errors='replace'). Idempotente."""
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:  # stream sem reconfigure (ex.: redirecionado/StringIO)
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
