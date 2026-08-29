"""Score: componentes separados, renormalização quando falta dado (ausência
nunca vira nota) e sinalização do que faltou."""
import pytest

from lib.analysis import score
from lib.analysis.signals import SignalResult

WEIGHTS = {"margem": 0.20, "demanda_liquidez": 0.15, "tendencia": 0.15,
           "forca_colecao": 0.10, "risco_reprint": 0.15, "risco_mercado": 0.10,
           "confianca": 0.15}


def _signals(level="medio"):
    return {"liquidity": SignalResult("alta (3.0 vendas/semana)", 3.0),
            "price_trend": SignalResult("alta", 0.10, {"volatility": 0.05}),
            "set_strength": SignalResult("forte", 0.10),
            "reprint_risk": SignalResult(level, None, {"level": level})}


def test_componentes_completos():
    comp = score.component_scores(0.25, _signals(), 80)
    assert set(comp) == set(WEIGHTS)
    assert comp["confianca"] == 80
    assert comp["risco_reprint"] == 50
    total, missing = score.total_score(comp, WEIGHTS)
    assert missing == [] and 0 <= total <= 100


def test_componente_sem_dado_e_excluido_com_renormalizacao():
    signals = _signals()
    signals["set_strength"] = SignalResult("n/d", None)
    comp = score.component_scores(None, signals, 50)
    assert comp["margem"] is None and comp["forca_colecao"] is None
    total, missing = score.total_score(comp, WEIGHTS)
    assert set(missing) == {"margem", "forca_colecao"}
    assert total is not None
    # renormalizado: média ponderada só dos presentes
    present = {k: v for k, v in comp.items() if v is not None}
    expect = sum(v * WEIGHTS[k] for k, v in present.items()) / \
        sum(WEIGHTS[k] for k in present)
    assert total == pytest.approx(expect, abs=1)


def test_tudo_ausente_score_none():
    empty = {k: None for k in WEIGHTS}
    total, missing = score.total_score(empty, WEIGHTS)
    assert total is None and len(missing) == len(WEIGHTS)


def test_reprint_invertido():
    assert score.component_scores(0.0, _signals("baixo"), 50)["risco_reprint"] == 90
    assert score.component_scores(0.0, _signals("alto"), 50)["risco_reprint"] == 10
