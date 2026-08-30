"""Decisão hold-vs-sell: tabela de decisão, gates de DADOS_INSUFICIENTES,
EVITAR_COMPRA, confiança por pesos e avaliação previsão-vs-realidade."""
from datetime import date

import pytest

from lib.analysis import recommend
from lib.analysis.signals import SignalResult

ACFG = {"confidence": {"min_confidence_for_call": 40},
        "hold": {"min_wait_value_brl": 0}}
SIGNALS = {"supply": SignalResult("caindo", -0.1),
           "price_trend": SignalResult("alta", 0.1),
           "reprint_risk": SignalResult("medio", None, {"level": "medio"}),
           "set_strength": SignalResult("neutra", 0.0)}


def _ph(esperado, capital=5.0, hoje=50.0):
    return {"lucro_esperado_brl": esperado, "custo_capital_brl": capital,
            "valor_de_esperar_brl": round(esperado - hoje - capital, 2)}


def test_confidence_soma_pesos_presentes():
    weights = {"a": 0.5, "b": 0.3, "c": 0.2}
    assert recommend.confidence_pct({"a": True, "b": False, "c": True}, weights) == 70
    assert recommend.confidence_pct({"a": True, "b": True, "c": True}, weights) == 100
    assert recommend.confidence_pct({}, weights) == 0


def test_manter_quando_valor_de_esperar_positivo():
    rec = recommend.recommend(50.0, {30: _ph(60.0), 60: _ph(90.0), 90: _ph(80.0)},
                              80, SIGNALS, ACFG, today=date(2026, 8, 29))
    assert rec.state == "MANTER_60D"       # maior valor_de_esperar (90−50−5=35)
    assert rec.best_horizon_days == 60
    assert rec.confidence_pct == 80
    assert rec.invalidation and rec.next_review_date


def test_janela_venda_quando_esperar_nao_compensa():
    rec = recommend.recommend(50.0, {30: _ph(52.0), 60: _ph(53.0)}, 80,
                              SIGNALS, ACFG, today=date(2026, 8, 29))
    assert rec.state == "JANELA_VENDA"


def test_evitar_compra_quando_tudo_negativo():
    rec = recommend.recommend(-30.0, {30: _ph(-20.0, hoje=-30.0),
                                      60: _ph(-10.0, hoje=-30.0)}, 80,
                              SIGNALS, ACFG, today=date(2026, 8, 29))
    assert rec.state == "EVITAR_COMPRA"


def test_dados_insuficientes_sem_projecao():
    rec = recommend.recommend(50.0, {}, 80, SIGNALS, ACFG)
    assert rec.state == "DADOS_INSUFICIENTES"
    assert "coorte" in rec.justification


def test_dados_insuficientes_confianca_baixa():
    # confiança abaixo do mínimo → nunca decide, mesmo com números na mão
    rec = recommend.recommend(50.0, {30: _ph(200.0)}, 20, SIGNALS, ACFG)
    assert rec.state == "DADOS_INSUFICIENTES"
    assert "confiança" in rec.justification


def test_dados_insuficientes_sem_preco_de_venda():
    rec = recommend.recommend(None, {30: _ph(200.0)}, 90, SIGNALS, ACFG)
    assert rec.state == "DADOS_INSUFICIENTES"


def test_evaluate_forecast_bandas():
    record = {"forecast_id": "x", "sku_id": "s", "horizon_days": 30,
              "due_date": "2026-10-01", "today_price_usd": 100.0,
              "scenarios": {"pessimista": {"price_usd": 90.0},
                            "base": {"price_usd": 100.0},
                            "otimista": {"price_usd": 115.0}},
              "recommendation": "MANTER_30D"}
    assert recommend.evaluate_forecast(record, 80.0)["band"] == "abaixo_do_pessimista"
    assert recommend.evaluate_forecast(record, 95.0)["band"] == "pessimista_a_base"
    assert recommend.evaluate_forecast(record, 110.0)["band"] == "base_a_otimista"
    assert recommend.evaluate_forecast(record, 130.0)["band"] == "acima_do_otimista"
    assert recommend.evaluate_forecast(record, 95.0)["base_error_frac"] == pytest.approx(-0.05)
