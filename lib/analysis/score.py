"""lib/analysis/score.py — score 0-100 com componentes SEPARADOS e nomeados.

Componentes (pesos em `analysis.score_weights`, somam 1.0):
  margem · demanda_liquidez · tendencia · forca_colecao · risco_reprint ·
  risco_mercado · confianca

Cada componente é 0-100; componente SEM dado vira None e é EXCLUÍDO com o peso
renormalizado (sinalizado em `missing`) — ausência de dado nunca vira nota.
Score é triagem informativa; NUNCA muda GREEN/YELLOW/RED do scan nem decide
capital.
"""
from __future__ import annotations


def _clamp(v: float, lo: float = 0.0, hi: float = 100.0) -> int:
    return int(max(lo, min(hi, round(v))))


def component_scores(margem_sobre_custo: float | None,
                     signals: dict, confidence: int) -> dict[str, int | None]:
    """Notas 0-100 por componente (None = sem dado)."""
    out: dict[str, int | None] = {}

    # margem: 0% de margem líquida → 40; +50% → 100; −40% → 0 (linear).
    if margem_sobre_custo is None:
        out["margem"] = None
    else:
        out["margem"] = _clamp(40 + margem_sobre_custo * 120)

    liq = signals.get("liquidity")
    if liq is None or liq.value is None:
        out["demanda_liquidez"] = None
    elif "vendas/semana" in liq.label:
        out["demanda_liquidez"] = _clamp(30 + (liq.value or 0) * 20)
    else:  # proxy por anúncios ativos (sem sold) — nota conservadora
        out["demanda_liquidez"] = _clamp(20 + (liq.value or 0) * 4)

    trend = signals.get("price_trend")
    if trend is None or trend.value is None:
        out["tendencia"] = None
    else:  # −20% → 10 · 0% → 50 · +20% → 90
        out["tendencia"] = _clamp(50 + trend.value * 200)

    chases = signals.get("set_strength")
    if chases is None or chases.value is None:
        out["forca_colecao"] = None
    else:
        out["forca_colecao"] = _clamp(50 + chases.value * 200)

    reprint = signals.get("reprint_risk")
    level = (reprint.detail or {}).get("level") if reprint is not None else None
    out["risco_reprint"] = {"baixo": 90, "medio": 50, "alto": 10}.get(level)

    # risco_mercado: volatilidade das janelas de preço (menos volátil = melhor).
    vol = (trend.detail or {}).get("volatility") if trend is not None else None
    out["risco_mercado"] = None if vol is None else _clamp(90 - vol * 300)

    out["confianca"] = _clamp(confidence)
    return out


def total_score(components: dict[str, int | None],
                weights: dict[str, float]) -> tuple[int | None, list[str]]:
    """Score ponderado com renormalização dos componentes presentes.

    Retorna (score, componentes_faltantes). Todos ausentes → (None, [...]).
    """
    missing = [k for k, v in components.items() if v is None]
    present = {k: v for k, v in components.items() if v is not None}
    wsum = sum(float(weights.get(k, 0.0)) for k in present)
    if not present or wsum <= 0:
        return None, missing
    score = sum(v * float(weights.get(k, 0.0)) for k, v in present.items()) / wsum
    return int(round(score)), missing
