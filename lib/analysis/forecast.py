"""lib/analysis/forecast.py — cenários 30/60/90d derivados de COMPARÁVEIS.

Exigência do operador: probabilidades e preços de cenário NUNCA são estimativa
arbitrária — derivam de regras documentadas + comparáveis históricos + backtest.

Como funciona (100% dirigido por config, sem ML):
  1. COORTE: produtos selados do MESMO product_type no registry, com data de
     lançamento real (set_meta). Para cada comparável, alinhamos por IDADE:
     medimos o retorno que ELE teve quando tinha a idade que o alvo tem hoje,
     na janela do horizonte (ciclo + 30/60/90d), usando o ARQUIVO tcgcsv
     (preços reais; datas quantizadas ao dia 1º do mês p/ compartilhar cache).
  2. CENÁRIOS: percentis documentados da distribuição de retornos da coorte
     (default p20/p50/p80 → pessimista/base/otimista) aplicados ao preço de
     hoje. Probabilidades base = `comparables.base_probs` (massa dos quartis
     em torno da mediana).
  3. AJUSTES por sinais, cada um citando a regra:
     - reprint alto/confirmado → cenário base capado em ≤ 0, pessimista
       alargado (`reprint_high_extra_downside`), prob desloca p/ pessimista;
     - oferta subindo forte → prob desloca p/ pessimista;
     - oferta caindo forte + fora da janela de impressão → otimista alargado
       (`supply_falling_extra_upside`), prob desloca p/ otimista.
  4. Invariantes: soma das probs ≈ 1; pessimista < base < otimista.
  5. Coorte menor que `comparables.min_cohort` → **None** (DADOS_INSUFICIENTES;
     nunca chutamos probabilidade).

O avaliador (scripts/evaluate_forecasts.py) mede previsão-vs-realidade e
realimenta a calibração dos percentis — o backtest é parte do método.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Callable

from .signals import SignalResult


@dataclass
class Scenario:
    price_usd: float
    prob: float
    justificativa: str

    def as_dict(self) -> dict:
        return {"price_usd": self.price_usd, "prob": round(self.prob, 3),
                "justificativa": self.justificativa}


def percentile(values: list[float], p: float) -> float:
    """Percentil com interpolação linear (sem numpy — stdlib pura)."""
    vals = sorted(values)
    if not vals:
        raise ValueError("percentile de lista vazia")
    if len(vals) == 1:
        return vals[0]
    k = (len(vals) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(vals) - 1)
    frac = k - lo
    return vals[lo] * (1 - frac) + vals[hi] * frac


def _month_floor(d: date) -> date:
    return date(d.year, d.month, 1)


def cohort_returns(target_release: date, comparables: list[tuple[str, date]],
                   window_days: int, today: date,
                   price_map_fn: Callable[[date], dict | None],
                   max_cohort: int = 40) -> tuple[list[float], dict]:
    """Retornos históricos da coorte, alinhados pela idade do alvo.

    `comparables` = [(product_id, release_date)] do MESMO product_type (sem o
    alvo). `price_map_fn(d)` → {productId: usd} ou None (injetável: no run real
    é o lib.tcgcsv_history.price_map_for_date; nos testes, um dict fixo).

    Retorna (retornos_fracionários, stats) — stats conta cada exclusão
    (fora do arquivo / sem preço), nunca silencioso.
    """
    target_age_days = (today - target_release).days
    stats = {"considered": 0, "usable": 0, "out_of_range": 0, "no_price": 0}
    returns: list[float] = []
    for pid, release in comparables[:max_cohort]:
        stats["considered"] += 1
        t0 = _month_floor(release + timedelta(days=target_age_days))
        t1 = t0 + timedelta(days=window_days)
        if t1 >= today:            # janela ainda não fechou no mundo real
            stats["out_of_range"] += 1
            continue
        m0 = price_map_fn(t0)
        m1 = price_map_fn(t1)
        if not m0 or not m1:
            stats["no_price"] += 1
            continue
        p0 = m0.get(str(pid))
        p1 = m1.get(str(pid))
        if not p0 or not p1 or p0 <= 0:
            stats["no_price"] += 1
            continue
        returns.append((p1 - p0) / p0)
        stats["usable"] += 1
    return returns, stats


def _shift(probs: dict[str, float], src: str, dst: str, amount: float) -> None:
    moved = min(probs[src], amount)
    probs[src] -= moved
    probs[dst] += moved


def build_scenarios(today_usd: float, returns: list[float],
                    supply: SignalResult, reprint: SignalResult,
                    print_cycle_sig: SignalResult, trend: SignalResult,
                    acfg: dict, horizon_label: str) -> dict[str, Scenario] | None:
    """Cenários pessimista/base/otimista de um horizonte. None = insuficiente."""
    comp = acfg.get("comparables") or {}
    scen = acfg.get("scenarios") or {}
    min_cohort = int(comp.get("min_cohort", 8))
    if not today_usd or today_usd <= 0 or len(returns) < min_cohort:
        return None
    pcts = comp.get("percentiles") or {"pessimista": 20, "base": 50, "otimista": 80}
    deltas = {name: percentile(returns, float(p)) for name, p in pcts.items()}
    just = {name: (f"p{int(pcts[name])} dos retornos de {len(returns)} comparáveis "
                   f"do mesmo tipo, alinhados por idade, em {horizon_label}: "
                   f"{deltas[name]:+.1%}") for name in deltas}

    reprint_level = (reprint.detail or {}).get("level")
    supply_falling = supply.value is not None and \
        supply.value <= float((acfg.get("signals") or {}).get("supply_falling_strong", -0.25))
    supply_rising = supply.value is not None and \
        supply.value >= float((acfg.get("signals") or {}).get("supply_rising_strong", 0.25))
    out_of_print = (print_cycle_sig.value or 0) >= \
        float((acfg.get("signals") or {}).get("print_cycle_late_months", 18))
    trend_up = (trend.value or 0) > 0

    if reprint_level == "alto":
        if deltas["base"] > 0:
            deltas["base"] = 0.0
            just["base"] += " · capado em 0% (risco de reprint alto — regra reprint_high)"
        extra = float(scen.get("reprint_high_extra_downside", -0.10))
        deltas["pessimista"] += extra
        just["pessimista"] += f" · alargado {extra:+.0%} (risco de reprint alto)"
    if supply_falling and out_of_print:
        extra = float(scen.get("supply_falling_extra_upside", 0.05))
        deltas["otimista"] += extra
        just["otimista"] += (f" · alargado {extra:+.0%} (oferta caindo forte + "
                             "fora da janela de impressão)")

    probs = dict(comp.get("base_probs") or {"pessimista": 0.25, "base": 0.50,
                                            "otimista": 0.25})
    shift = float(scen.get("prob_shift", 0.10))
    if reprint_level == "alto" or supply_rising:
        _shift(probs, "otimista", "pessimista", shift)
        just["pessimista"] += " · +prob (reprint alto/oferta subindo)"
    if supply_falling and out_of_print and trend_up and reprint_level != "alto":
        _shift(probs, "pessimista", "otimista", shift)
        just["otimista"] += " · +prob (escassez: oferta caindo, OOP, tendência ↑)"
    total = sum(probs.values()) or 1.0
    probs = {k: v / total for k, v in probs.items()}

    # invariante de ordem: pess ≤ base ≤ otim (ajustes não podem cruzar)
    if deltas["pessimista"] > deltas["base"]:
        deltas["pessimista"] = deltas["base"]
    if deltas["otimista"] < deltas["base"]:
        deltas["otimista"] = deltas["base"]

    return {name: Scenario(price_usd=round(today_usd * (1 + deltas[name]), 2),
                           prob=probs[name], justificativa=just[name])
            for name in ("pessimista", "base", "otimista")}
