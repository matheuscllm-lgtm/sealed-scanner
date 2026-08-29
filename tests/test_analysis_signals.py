"""Sinais separados: dado ausente → n/d/HISTORICO_INSUFICIENTE (nunca nota),
volume só de VENDAS (Market Price nunca mede volume), oferta por snapshots."""
from datetime import datetime, timezone

import pytest

from lib.analysis import signals as sig

SCFG = {"trend_flat_band": 0.05, "supply_windows_days": [7, 30, 90],
        "supply_falling_strong": -0.25, "supply_rising_strong": 0.25,
        "liquidity_active_high": 8, "liquidity_active_low": 3,
        "chases_top_n": 10, "chases_concentration_top": 3,
        "print_cycle_late_months": 18, "print_cycle_old_months": 30}


def _sold(price, qty, seller=None, lookback=30):
    return {"avg_sold_price_usd": price, "total_sold": qty, "seller": seller,
            "is_probstein": seller == "probstein123", "lookback_days": lookback,
            "collected_at": "2026-08-28", "source_url": "terapeak_scrape:t.csv"}


def _snap(days_ago, count):
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    ts = now.timestamp() - days_ago * 86400
    iso = datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {"captured_at": iso, "active_count": count,
            "source_type": "ebay_active", "source_url": "u"}


def test_price_trend_sem_historico_e_insuficiente():
    r = sig.price_trend("1", 50.0, {}, [], SCFG)
    assert r.insufficient and "n/d" in r.label


def test_price_trend_headline_90d_e_mediana_ponderada():
    r = sig.price_trend("1", 55.0, {30: 0.02, 90: 0.10, 180: 0.2},
                        [_sold(50.0, 3), _sold(60.0, 1)], SCFG)
    assert not r.insufficient
    assert "alta" in r.label and "90d" in r.label
    assert r.detail["sold_median_usd"] == 50.0      # ponderada por unidades
    assert r.detail["volatility"] is not None
    assert any(e["source_type"] == "tcgcsv_archive" for e in r.evidence)


def test_supply_menos_de_2_pontos_e_historico_insuficiente():
    r = sig.supply_trend([_snap(1, 40)], SCFG)
    assert r.insufficient and "HISTORICO_INSUFICIENTE" in r.label


def test_supply_caindo_forte():
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    r = sig.supply_trend([_snap(30, 60), _snap(1, 40)], SCFG, now=now)
    assert not r.insufficient
    assert "caindo forte" in r.label
    assert r.value == pytest.approx((40 - 60) / 60, abs=1e-4)


def test_liquidity_volume_so_de_vendas():
    # SÓ ativos (sem sold) → proxy rotulado E insuficiente (volume real falta)
    r = sig.liquidity(10, [], SCFG)
    assert r.insufficient and "proxy" in r.label
    # com vendas → vendas/semana + sell-through + share probstein
    r2 = sig.liquidity(10, [_sold(50.0, 6, "a"), _sold(52.0, 6, "probstein123")], SCFG)
    assert not r2.insufficient
    assert r2.detail["units_sold"] == 12
    assert r2.detail["sales_per_week"] == pytest.approx(12 / (30 / 7), rel=1e-3)
    assert r2.detail["sell_through"] == pytest.approx(12 / 22, rel=1e-3)
    assert r2.detail["probstein_share"] == pytest.approx(0.5)


def test_liquidity_sem_nada_e_insuficiente():
    assert sig.liquidity(None, [], SCFG).insufficient


def test_print_cycle_sem_data_e_nd():
    assert sig.print_cycle(None, SCFG).insufficient


def test_set_strength_agregado_e_contagem():
    chases = [{"product_id": "1", "name": "A", "price_usd": 100.0, "pct_90": 0.10},
              {"product_id": "2", "name": "B", "price_usd": 50.0, "pct_90": -0.05},
              {"product_id": "3", "name": "C", "price_usd": 25.0, "pct_90": 0.20}]
    r = sig.set_strength(chases, SCFG)
    assert not r.insufficient
    assert r.detail["chases_up"] == 2 and r.detail["chases_down"] == 1
    assert r.detail["concentration_top3"] == pytest.approx(1.0)


def test_set_strength_sem_chases_e_nd():
    assert sig.set_strength([], SCFG).insufficient


def test_supply_ponto_velho_nao_serve_de_base_para_janela_curta():
    # pontos a 90d e agora: para w=7 NÃO há base válida (banda [0.6w, 1.5w+2]);
    # o Δ de meses não pode ser rotulado/limiarizado como variação de ~7d
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    r = sig.supply_trend([_snap(90, 60), _snap(0, 41)], SCFG, now=now)
    assert "delta_7d" not in r.detail
    assert "delta_90d" in r.detail          # a janela certa continua medida


def test_supply_pisos_incompativeis_pulados():
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    a = _snap(30, 60); a["floor_usd"] = 30.0
    b = _snap(0, 90); b["floor_usd"] = 20.0   # ref caiu → piso caiu → total sobe sozinho
    r = sig.supply_trend([a, b], SCFG, now=now)
    assert r.insufficient
    assert r.detail.get("janelas_puladas_piso_incompativel") == 1


def test_supply_piso_ausente_e_compativel():
    now = datetime(2026, 8, 29, tzinfo=timezone.utc)
    r = sig.supply_trend([_snap(30, 60), _snap(0, 40)], SCFG, now=now)
    assert not r.insufficient               # snapshots antigos sem floor seguem valendo
