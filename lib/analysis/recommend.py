"""lib/analysis/recommend.py — decisão hold-vs-sell (classificação TÉCNICA).

Estados (rótulos NEUTROS — decisão do operador; nunca ordem de compra/venda,
a decisão de capital é 100% do operador):
  JANELA_VENDA        listar imediatamente ao chegar (realiza em ~ciclo, ~24d)
  MANTER_30D/60D/90D  segurar N dias ALÉM do ciclo antes de listar
  EVITAR_COMPRA       lucro líquido negativo hoje E em todos os horizontes
  DADOS_INSUFICIENTES sem base para decidir — NUNCA estimamos no chute

Regra do hold: MANTER só quando `valor_de_esperar` (lucro esperado − lucro
hoje − custo de capital dos dias extras) supera `hold.min_wait_value_brl`.

Cada recomendação carrega: confiança 0-100 (qualidade dos DADOS), justificativa
objetiva com números, maior catalisador, maior risco, condição de invalidação e
data da próxima revisão — sempre com fontes/datas nas evidências do produto.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class Recommendation:
    state: str
    confidence_pct: int
    justification: str
    catalyst: str = ""
    risk: str = ""
    invalidation: str = ""
    next_review_date: str = ""
    best_horizon_days: int | None = None

    def as_dict(self) -> dict:
        return {"state": self.state, "confidence_pct": self.confidence_pct,
                "justification": self.justification, "catalyst": self.catalyst,
                "risk": self.risk, "invalidation": self.invalidation,
                "next_review_date": self.next_review_date,
                "best_horizon_days": self.best_horizon_days}


def confidence_pct(quality_inputs: dict[str, bool], weights: dict[str, float]) -> int:
    """Confiança 0-100 = soma dos pesos dos insumos de dado PRESENTES.

    `quality_inputs` = {nome_do_insumo: presente?}; pesos do config
    (`analysis.confidence.weights`). Insumo sem peso configurado é ignorado.
    """
    total = 0.0
    for name, ok in quality_inputs.items():
        w = float(weights.get(name, 0.0))
        if ok:
            total += w
    return max(0, min(100, round(total * 100)))


def _fmt_brl(v: float) -> str:
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def recommend(lucro_hoje_brl: float | None, per_horizon: dict[int, dict],
              confidence: int, signals: dict, acfg: dict,
              today: date | None = None) -> Recommendation:
    """Decide o estado a partir dos números já computados.

    `per_horizon` = {30: {"lucro_esperado_brl", "custo_capital_brl",
                          "valor_de_esperar_brl"}, 60: {...}, 90: {...}}
    (horizonte ausente = sem cenário; dict vazio = nenhuma projeção).
    """
    today = today or date.today()
    min_conf = int((acfg.get("confidence") or {}).get("min_confidence_for_call", 40))
    min_wait = float((acfg.get("hold") or {}).get("min_wait_value_brl", 0.0))

    catalyst, risk = _catalyst_and_risk(signals)

    if lucro_hoje_brl is None or not per_horizon or confidence < min_conf:
        why = []
        if lucro_hoje_brl is None:
            why.append("sem preço de venda de referência")
        if not per_horizon:
            why.append("sem projeção (coorte de comparáveis insuficiente)")
        if confidence < min_conf:
            why.append(f"confiança dos dados {confidence}% < mínimo {min_conf}%")
        return Recommendation(
            state="DADOS_INSUFICIENTES", confidence_pct=confidence,
            justification="Sem base para decidir: " + "; ".join(why) +
                          ". Nunca estimamos artificialmente.",
            catalyst=catalyst, risk=risk,
            invalidation="Importar vendas (Terapeak) / acumular snapshots de "
                         "oferta / rodar com rede eleva a confiança.",
            next_review_date=(today + timedelta(days=7)).isoformat())

    best_h = max(per_horizon, key=lambda h: per_horizon[h]["valor_de_esperar_brl"])
    best = per_horizon[best_h]
    all_negative = (lucro_hoje_brl < 0 and
                    all(v["lucro_esperado_brl"] < 0 for v in per_horizon.values()))

    if all_negative:
        return Recommendation(
            state="EVITAR_COMPRA", confidence_pct=confidence,
            justification=(f"Lucro líquido hoje {_fmt_brl(lucro_hoje_brl)} e lucro "
                           "esperado NEGATIVO em todos os horizontes — o deal do "
                           "scan não compensa no canal real (fator líquido aplicado)."),
            catalyst=catalyst, risk=risk,
            invalidation="Preço de compra BR cair ou preço US subir o bastante "
                         "para positivar o lucro líquido.",
            next_review_date=(today + timedelta(days=14)).isoformat(),
            best_horizon_days=best_h)

    if best["valor_de_esperar_brl"] > min_wait:
        return Recommendation(
            state=f"MANTER_{best_h}D", confidence_pct=confidence,
            justification=(f"Esperar {best_h}d além do ciclo rende "
                           f"{_fmt_brl(best['valor_de_esperar_brl'])} a mais que "
                           f"vender já ({_fmt_brl(best['lucro_esperado_brl'])} "
                           f"esperado vs {_fmt_brl(lucro_hoje_brl)} hoje, já "
                           f"descontado custo de capital "
                           f"{_fmt_brl(best['custo_capital_brl'])})."),
            catalyst=catalyst, risk=risk,
            invalidation=_hold_invalidation(signals),
            next_review_date=(today + timedelta(days=min(30, max(7, best_h // 2)))).isoformat(),
            best_horizon_days=best_h)

    return Recommendation(
        state="JANELA_VENDA", confidence_pct=confidence,
        justification=(f"Nenhum horizonte com valor de esperar positivo (melhor: "
                       f"{best_h}d = {_fmt_brl(best['valor_de_esperar_brl'])}); "
                       f"lucro líquido vendendo já: {_fmt_brl(lucro_hoje_brl)}. "
                       "Listar ao chegar."),
        catalyst=catalyst, risk=risk,
        invalidation="Evento CONFIRMADO_OFICIAL de escassez ou queda forte dos "
                     "anúncios ativos mudaria o cálculo — reavaliar.",
        next_review_date=(today + timedelta(days=14)).isoformat(),
        best_horizon_days=best_h)


def _catalyst_and_risk(signals: dict) -> tuple[str, str]:
    """Maior catalisador (melhor sinal a favor) e maior risco (pior contra)."""
    catalyst = ""
    risk = ""
    supply = signals.get("supply")
    trend = signals.get("price_trend")
    reprint = signals.get("reprint_risk")
    chases = signals.get("set_strength")
    if supply is not None and (supply.value or 0) < 0:
        catalyst = f"oferta ativa {supply.label}"
    elif trend is not None and (trend.value or 0) > 0:
        catalyst = f"preço em {trend.label}"
    elif chases is not None and (chases.value or 0) > 0:
        catalyst = f"chases do set: {chases.label}"
    if reprint is not None and (reprint.detail or {}).get("level") == "alto":
        risk = f"risco de reprint {reprint.label}"
    elif supply is not None and (supply.value or 0) > 0:
        risk = f"oferta ativa {supply.label}"
    elif trend is not None and (trend.value or 0) < 0:
        risk = f"preço em {trend.label}"
    return catalyst or "nenhum sinal positivo forte", risk or "nenhum risco forte identificado"


def _hold_invalidation(signals: dict) -> str:
    parts = ["evento de reprint/restock CONFIRMADO_OFICIAL"]
    supply = signals.get("supply")
    if supply is not None and supply.value is not None:
        parts.append("anúncios ativos subirem >25% na janela")
    trend = signals.get("price_trend")
    if trend is not None and trend.value is not None:
        parts.append("preço realizado cair >10% da projeção base")
    return "Invalida o hold: " + " OU ".join(parts) + "."


# ── Avaliação previsão-vs-realidade ────────────────────────────────────────
def evaluate_forecast(record: dict, realized_price_usd: float) -> dict:
    """Compara um registro do forecast log com o preço realizado.

    Retorna banda em que o realizado caiu (abaixo/pessimista/base/otimista/
    acima), erro % vs o cenário base e o dict pronto pro relatório.
    """
    sc = record.get("scenarios") or {}
    pess = (sc.get("pessimista") or {}).get("price_usd")
    base = (sc.get("base") or {}).get("price_usd")
    otim = (sc.get("otimista") or {}).get("price_usd")
    band = "sem_cenarios"
    if None not in (pess, base, otim):
        if realized_price_usd < pess:
            band = "abaixo_do_pessimista"
        elif realized_price_usd <= base:
            band = "pessimista_a_base"
        elif realized_price_usd <= otim:
            band = "base_a_otimista"
        else:
            band = "acima_do_otimista"
    base_err = (None if not base else
                round((realized_price_usd - base) / base, 4))
    return {"forecast_id": record.get("forecast_id"),
            "sku_id": record.get("sku_id"),
            "horizon_days": record.get("horizon_days"),
            "due_date": record.get("due_date"),
            "today_price_usd": record.get("today_price_usd"),
            "realized_price_usd": realized_price_usd,
            "band": band, "base_error_frac": base_err,
            "recommendation": record.get("recommendation")}
