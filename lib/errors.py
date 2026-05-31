"""errors.py — exceções compartilhadas entre adapters e o pipeline.

`SourceBlockedError` distingue "a fonte BR está bloqueada por proteção
externa (WAF/Cloudflare/IP reputation)" de "a fonte respondeu mas veio
vazia/quebrada". O scanner trata o primeiro como condição EXTERNA não-fatal
(o pipeline está OK, a fonte é que está inacessível) e o segundo como erro
real (seletor quebrado, inventário vazio inesperado) — evitando mascarar
silent failures das outras fontes. Cf. review sealed-reviewer 2026-05-29.
"""
from __future__ import annotations

__all__ = ["SourceBlockedError"]


class SourceBlockedError(Exception):
    """Levantada por um adapter quando a fonte está bloqueada por proteção
    externa (ex.: Cloudflare WAF "you have been blocked", HTTP 403/429/503
    de bot management). NÃO é bug do scanner — é o site negando acesso.

    Carrega `source` (nome da fonte) e `hint` (texto acionável para o log).
    """

    def __init__(self, source: str, detail: str, hint: str = "") -> None:
        self.source = source
        self.detail = detail
        self.hint = hint
        msg = f"{source}: {detail}"
        if hint:
            msg += f" — {hint}"
        super().__init__(msg)
