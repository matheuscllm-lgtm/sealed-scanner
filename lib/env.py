"""lib/env.py — carregamento de `.env` compartilhado pelos adapters.

Antes desta extração, `_load_dotenv_if_present()` estava copiado idêntico em
`liga_adapter.py`, `olx_adapter.py` e `mercadolivre_adapter.py` (mesma classe
de duplicação do transporte Firecrawl, resolvida no Issue #13). Aqui ele vive
UMA vez; cada adapter mantém o alias `_load_dotenv_if_present` (os testes o
monkeypatcham por módulo).

Semântica preservada: NÃO sobrescreve env vars já setadas (`setdefault`),
ignora comentários/linhas sem `=`, e tira aspas simples/duplas do valor.
"""
from __future__ import annotations

import os
from pathlib import Path

# Raiz do repo (os adapters vivem na raiz; este módulo em lib/).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_ENV = _REPO_ROOT / ".env"


def load_dotenv_if_present(env_path: Path | None = None) -> None:
    """Carrega o `.env` da raiz do repo se existir. Não sobrescreve env vars
    já setadas. `env_path` só serve pra testes (default: `<raiz>/.env`)."""
    path = env_path or _DEFAULT_ENV
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip().strip('"\''))
