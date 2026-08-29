"""Avaliador previsão-vs-realidade: só vencidas, preço do arquivo, bandas."""
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import evaluate_forecasts as ef  # noqa: E402

RECORDS = [
    {"forecast_id": "a:30", "sku_id": "s1", "tcgplayer_product_id": "900001",
     "horizon_days": 30, "due_date": "2026-08-01", "today_price_usd": 100.0,
     "scenarios": {"pessimista": {"price_usd": 95.0}, "base": {"price_usd": 105.0},
                   "otimista": {"price_usd": 115.0}}, "recommendation": "MANTER_30D"},
    {"forecast_id": "b:90", "sku_id": "s1", "tcgplayer_product_id": "900001",
     "horizon_days": 90, "due_date": "2026-12-01", "today_price_usd": 100.0,
     "scenarios": {}, "recommendation": "JANELA_VENDA"},          # pendente
    {"forecast_id": "c:30", "sku_id": "s2", "tcgplayer_product_id": "900002",
     "horizon_days": 30, "due_date": "2026-08-01", "today_price_usd": 50.0,
     "scenarios": {}, "recommendation": "JANELA_VENDA"},          # sem preço realizado
]


def _pm(d: date):
    if d == date(2026, 8, 1):
        return {"900001": 108.0}
    return None


def test_evaluate_all_separa_vencidas_pendentes_e_sem_preco():
    evals, no_price = ef.evaluate_all(RECORDS, date(2026, 8, 29), _pm, {})
    assert len(evals) == 1 and no_price == 1
    e = evals[0]
    assert e["forecast_id"] == "a:30"
    assert e["realized_price_usd"] == 108.0
    assert e["band"] == "base_a_otimista"


def test_render_com_e_sem_avaliacoes():
    evals, no_price = ef.evaluate_all(RECORDS, date(2026, 8, 29), _pm, {})
    text = ef.render(evals, pending=1, no_price=no_price)
    assert "base_a_otimista" in text and "1/1 dentro" in text
    empty = ef.render([], pending=2, no_price=0)
    assert "Nenhuma previsão vencida" in empty
