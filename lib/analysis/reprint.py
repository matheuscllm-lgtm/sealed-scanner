"""lib/analysis/reprint.py — sinal 2.4: risco de reprint/restock.

Duas camadas, combinadas honestamente:
  1. EVENTOS curados (`data/events_<jogo>.yaml` — sempre com fonte real):
     estado da evidência por SKU:
       CONFIRMADO_OFICIAL  — reprint/restock com fonte oficial (CONFIRMADA)
       RESTOCK_OBSERVADO   — restock visto em varejista/PC
       SINAL_DISTRIBUIDOR  — sinal de GTS/Southern Hobby ou notícia (SINAL_DE_MERCADO)
       RUMOR               — fórum/rede social (nunca sobe de RUMOR)
       SEM_EVIDENCIA       — nenhum evento registrado
  2. RISCO ESTRUTURAL (adaptado de pokemon-longterm-outlook/outlook/scoring.py):
     sets de reprint forte (151, Prismatic, Celebrations…) + sets ESPECIAIS
     (fora da numeração da era: "SV:", "ME:", "SWSH:") são impressos em massa
     por anos; e set jovem ainda está na janela de impressão.

Regra dura: `SEM_EVIDENCIA` ≠ risco baixo — ausência de anúncio não prova
descontinuação, e um simples "esgotado" não é evento. Risco BAIXO exige
`out_of_print_confirmed` com fonte, OU idade estrutural fora da janela.
"""
from __future__ import annotations

import re

from .events import Event
from .signals import SignalResult

# Portado de outlook/scoring.py (nomes de set cobrem a fonte tcgcsv).
HEAVY_REPRINT_NAME_PARTS = (
    "151", "Paldean Fates", "Prismatic Evolutions", "Champion's Path",
    "Shining Fates", "Crown Zenith", "Celebrations", "Ascended Heroes",
)
SPECIAL_SET_PREFIX_RE = re.compile(r"^(SV|SWSH|ME):")


def is_heavy_reprint(set_name: str) -> bool:
    name = set_name or ""
    return (any(part in name for part in HEAVY_REPRINT_NAME_PARTS)
            or bool(SPECIAL_SET_PREFIX_RE.match(name)))


_EVENT_STATE = {
    "reprint_announced": "CONFIRMADO_OFICIAL",
    "reprint_shipping": "CONFIRMADO_OFICIAL",
    "restock": "RESTOCK_OBSERVADO",
    "allocation": "SINAL_DISTRIBUIDOR",
    "new_product_with_set": "SINAL_DISTRIBUIDOR",
}
_STATE_RANK = ["SEM_EVIDENCIA", "RUMOR", "SINAL_DISTRIBUIDOR",
               "RESTOCK_OBSERVADO", "CONFIRMADO_OFICIAL"]


def reprint_risk(set_name: str, age_months: float | None,
                 sku_events: list[Event], scfg: dict) -> SignalResult:
    """Risco de reprint/restock do SKU: nível alto|medio|baixo + estado da
    evidência + razões auditáveis (cada input citado)."""
    late = int(scfg.get("print_cycle_late_months", 18))
    old = int(scfg.get("print_cycle_old_months", 30))
    reasons: list[str] = []
    evidence: list[dict] = []
    state = "SEM_EVIDENCIA"
    oop_confirmed = False
    for ev in sku_events:
        evidence.append({"fact": f"[{ev.type}] {ev.note or ev.id} ({ev.classification})",
                         "source_type": ev.source_type, "source_url": ev.source_url,
                         "collected_at": ev.collected_at})
        if ev.type == "out_of_print_confirmed":
            oop_confirmed = True
            reasons.append(f"fim de impressão confirmado ({ev.id})")
            continue
        st = _EVENT_STATE.get(ev.type, "SINAL_DISTRIBUIDOR")
        if ev.classification == "RUMOR":
            st = "RUMOR"
        if _STATE_RANK.index(st) > _STATE_RANK.index(state):
            state = st
            reasons.append(f"evento {ev.type} ({ev.classification}, {ev.id})")

    heavy = is_heavy_reprint(set_name)
    if heavy:
        reasons.append("set de reprint forte/especial — impresso em massa por anos")
    in_window = age_months is not None and age_months < late
    if in_window:
        reasons.append(f"set jovem ({age_months:.0f}m) — dentro da janela de impressão")

    # Nível: evento positivo de reprint/restock domina; um out-of-print
    # CONFIRMADO com fonte vence o estrutural (idade/janela) — evidência
    # curada > heurística; senão estrutural.
    if state in ("CONFIRMADO_OFICIAL", "RESTOCK_OBSERVADO"):
        level = "alto"
    elif oop_confirmed:
        level = "baixo"
    elif state == "SINAL_DISTRIBUIDOR" or heavy or in_window:
        level = "alto" if heavy else "medio"
    elif age_months is not None and age_months >= old:
        level = "baixo"
        reasons.append(f"idade {age_months:.0f}m ≥ {old}m — fora da janela típica")
    else:
        # SEM_EVIDENCIA nunca é prova de risco baixo.
        level = "medio"
    if state == "SEM_EVIDENCIA" and not oop_confirmed:
        reasons.append("sem evidência registrada — ausência de anúncio ≠ risco baixo")
    if state == "RUMOR":
        reasons.append("há RUMOR não confirmado — acompanhar")

    display_state = state
    if oop_confirmed and state == "SEM_EVIDENCIA":
        display_state = "OOP_CONFIRMADO"   # há evidência — só que de FIM de impressão
    detail = {"level": level, "evidence_state": state,
              "heavy_reprint": heavy, "oop_confirmed": oop_confirmed,
              "reasons": reasons}
    return SignalResult(f"{level} ({display_state})", None, detail, evidence)
