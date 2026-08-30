"""Cenários derivados de COMPARÁVEIS: percentis, alinhamento por idade,
ajustes documentados, invariantes (soma de prob ≈ 1; pess ≤ base ≤ otim) e o
gate de coorte insuficiente (nunca probabilidade arbitrária)."""
from datetime import date

import pytest

from lib.analysis import forecast
from lib.analysis.signals import SignalResult

ACFG = {
    "comparables": {"min_cohort": 4, "max_cohort": 40,
                    "percentiles": {"pessimista": 20, "base": 50, "otimista": 80},
                    "base_probs": {"pessimista": 0.25, "base": 0.50, "otimista": 0.25}},
    "scenarios": {"prob_shift": 0.10, "reprint_high_extra_downside": -0.10,
                  "supply_falling_extra_upside": 0.05},
    "signals": {"supply_falling_strong": -0.25, "supply_rising_strong": 0.25,
                "print_cycle_late_months": 18},
}


def _sig(value=None, label="x", detail=None):
    return SignalResult(label, value, detail or {})


def test_percentile_interpolacao():
    vals = [0.0, 0.10, 0.20, 0.30, 0.40]
    assert forecast.percentile(vals, 50) == pytest.approx(0.20)
    assert forecast.percentile(vals, 20) == pytest.approx(0.08)
    assert forecast.percentile([0.5], 80) == 0.5


def test_cohort_returns_alinha_por_idade_e_conta_exclusoes():
    today = date(2026, 8, 29)
    target_release = date(2025, 6, 13)          # idade ~442d
    # comparável A: release 2024-01-10 → t0 = floor(2024-01-10+442d)=2025-03-01
    maps = {"2025-03-01": {"11": 50.0}, "2025-03-31": {"11": 55.0}}

    def pm(d):
        return maps.get(d.isoformat())

    comps = [("11", date(2024, 1, 10)),          # utilizável (+10%)
             ("12", date(2026, 8, 1)),           # janela não fechou → out_of_range
             ("13", date(2024, 1, 10))]          # sem preço nos mapas → no_price
    rets, stats = forecast.cohort_returns(target_release, comps, 30, today, pm)
    assert rets == [pytest.approx(0.10)]
    assert stats == {"considered": 3, "usable": 1, "out_of_range": 1, "no_price": 1}


def _neutral_signals():
    return (_sig(0.0, "estável"),                       # supply
            _sig(None, "medio (SEM_EVIDENCIA)", {"level": "medio"}),  # reprint
            _sig(20.0, "fim da janela"),                # print_cycle (meses)
            _sig(0.05, "alta"))                          # trend


def test_build_scenarios_percentis_e_ordem():
    supply, reprint, cyc, trend = _neutral_signals()
    rets = [-0.10, -0.05, 0.0, 0.05, 0.10, 0.15, 0.20, 0.25]
    sc = forecast.build_scenarios(100.0, rets, supply, reprint, cyc, trend,
                                  ACFG, "ciclo+30d")
    assert sc is not None
    assert sc["pessimista"].price_usd < sc["base"].price_usd < sc["otimista"].price_usd
    assert sum(s.prob for s in sc.values()) == pytest.approx(1.0)
    assert "p50" in sc["base"].justificativa      # derivação documentada


def test_build_scenarios_coorte_insuficiente_retorna_none():
    supply, reprint, cyc, trend = _neutral_signals()
    assert forecast.build_scenarios(100.0, [0.1, 0.2], supply, reprint, cyc,
                                    trend, ACFG, "x") is None
    assert forecast.build_scenarios(0.0, [0.1] * 10, supply, reprint, cyc,
                                    trend, ACFG, "x") is None


def test_reprint_alto_capa_base_e_desloca_probabilidade():
    supply, _, cyc, trend = _neutral_signals()
    reprint_alto = _sig(None, "alto", {"level": "alto"})
    rets = [0.05, 0.06, 0.07, 0.08, 0.09, 0.10]
    sc = forecast.build_scenarios(100.0, rets, supply, reprint_alto, cyc, trend,
                                  ACFG, "x")
    assert sc["base"].price_usd <= 100.0          # base capada em ≤ 0%
    assert sc["pessimista"].prob == pytest.approx(0.35)   # 0.25 + shift 0.10
    assert sc["otimista"].prob == pytest.approx(0.15)
    assert "reprint" in sc["pessimista"].justificativa


def test_escassez_desloca_probabilidade_para_otimista():
    _, reprint, cyc, trend = _neutral_signals()
    supply_caindo = _sig(-0.30, "caindo forte")
    sc = forecast.build_scenarios(100.0, [0.0, 0.05, 0.1, 0.15, 0.2, 0.25],
                                  supply_caindo, reprint, cyc, trend, ACFG, "x")
    assert sc["otimista"].prob == pytest.approx(0.35)
    assert sc["pessimista"].prob == pytest.approx(0.15)
