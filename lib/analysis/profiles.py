"""lib/analysis/profiles.py — resolução do perfil de DADOS da análise por jogo.

Mesmo padrão dos GAME_PROFILES do scanner (isolamento por DADOS, nunca
`if game ==` na lógica): todos os caminhos vêm do bloco `analysis:` do config
do jogo; aqui só aplicamos defaults seguros e resolvemos paths relativos à
raiz do repo. Config sem o bloco = análise desligada (no-op honesto).
"""
from __future__ import annotations

from pathlib import Path

# Defaults seguros — o config VENCE; isto só evita KeyError em config parcial.
# (Números de regra ficam no config.yaml comentado; estes são o espelho 1:1.)
DEFAULTS: dict = {
    "enabled": False,
    "sale_price_basis": "ebay_then_tcg",
    "net_factor": 0.70,
    "cycle": {"delivery_br_days": 10, "us_forwarding_days": 7, "listing_days": 7},
    "capital": {"annual_cost_pct": 0.15},
    "buy_price": {"min_margin_over_cost": 0.25},
    "horizons_days": [30, 60, 90],
    "comparables": {
        "min_cohort": 8, "max_cohort": 40,
        "percentiles": {"pessimista": 20, "base": 50, "otimista": 80},
        "base_probs": {"pessimista": 0.25, "base": 0.50, "otimista": 0.25},
    },
    "scenarios": {
        "prob_shift": 0.10,
        "reprint_high_extra_downside": -0.10,
        "supply_falling_extra_upside": 0.05,
    },
    "signals": {
        "trend_windows_days": [30, 90, 180],
        "trend_flat_band": 0.05,
        "supply_windows_days": [7, 30, 90],
        "supply_falling_strong": -0.25,
        "supply_rising_strong": 0.25,
        "liquidity_active_high": 8,
        "liquidity_active_low": 3,
        "chases_top_n": 10,
        "chases_concentration_top": 3,
        "print_cycle_late_months": 18,
        "print_cycle_old_months": 30,
    },
    "confidence": {
        "weights": {
            "price_history_180d": 0.25, "price_history_90d": 0.15,
            "supply_series": 0.20, "ebay_ref_fresh": 0.10,
            "sold_data_imported": 0.15, "set_meta_known": 0.10,
            "events_reviewed": 0.05,
        },
        "events_reviewed_max_age_days": 45,
        "min_confidence_for_call": 40,
    },
    "data_quality": {"min_history_points": 2, "min_history_span_days": 60},
    "score_weights": {
        "margem": 0.20, "demanda_liquidez": 0.15, "tendencia": 0.15,
        "forca_colecao": 0.10, "risco_reprint": 0.15, "risco_mercado": 0.10,
        "confianca": 0.15,
    },
    "hold": {"min_wait_value_brl": 0.0},
    "files": {
        "supply_history": "data/history/supply_pokemon.jsonl",
        "sold_imports": "data/history/ebay_sold_pokemon.jsonl",
        "trends_imports": "data/history/trends_pokemon.jsonl",
        "forecast_log": "data/forecasts/forecasts_pokemon.jsonl",
        "events": "data/events_pokemon.yaml",
        "set_meta": "data/set_meta.json",
        "intel_candidates": "data/history/market_intel_pokemon.jsonl",
    },
    "tcgcsv": {"category_id": "3", "cache_dir": "data/cache/tcgcsv_history"},
    "market_intel": {"feeds": []},
}


def _merge(base: dict, override: dict) -> dict:
    """Merge raso-recursivo: override vence; dicts aninhados são mesclados."""
    out = dict(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def analysis_config(config: dict) -> dict:
    """Bloco `analysis:` do config do jogo mesclado sobre os defaults."""
    return _merge(DEFAULTS, (config or {}).get("analysis") or {})


def cycle_days(acfg: dict) -> int:
    """Ciclo operacional (comprar → produto listado nos EUA), em dias.

    Decisão do operador (2026-08-29): ~10d chegada + ~7d envio US + ~7d p/
    listar — o delay natural de uma tentativa de venda imediata. Derivado da
    SOMA dos componentes do config, nunca hardcoded."""
    c = acfg.get("cycle") or {}
    return int(c.get("delivery_br_days", 0)) + int(c.get("us_forwarding_days", 0)) \
        + int(c.get("listing_days", 0))


def resolve_path(root: Path, rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else root / p
