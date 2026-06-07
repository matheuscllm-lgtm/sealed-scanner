"""conftest.py — garante que a raiz do repo está no sys.path para o pytest.

Repo dedicado: os módulos (lib/, sealed_arbitrage_scanner) vivem na raiz. Sem
isso, `pytest tests/` não acha `lib`/`sealed_arbitrage_scanner` (pytest adiciona
o dir do teste ao path, não a raiz).
"""
import sys
from pathlib import Path

ROOT = str(Path(__file__).resolve().parent)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
