#!/usr/bin/env python3
"""evaluate_forecasts.py — previsão vs REALIDADE (calibração do método).

Lê o log de previsões (`analysis.files.forecast_log`), pega as VENCIDAS
(due_date <= hoje) e compara com o preço realizado no arquivo tcgcsv da
due_date (avaliação RETROATIVA — o arquivo guarda o preço real de cada dia).
Relata por previsão a banda em que o realizado caiu e o erro do cenário base,
mais o agregado (hit-rate por banda + erro absoluto médio) — é este número que
calibra os percentis dos comparáveis (`analysis.comparables`).

Uso:
    python scripts/evaluate_forecasts.py [--game pokemon] [--as-of YYYY-MM-DD]
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sealed_arbitrage_scanner as S
from lib import tcgcsv_history as hist
from lib.analysis import history_store as store
from lib.analysis.profiles import analysis_config, resolve_path
from lib.analysis.recommend import evaluate_forecast


def evaluate_all(records: list[dict], as_of: date, price_map_fn,
                 pid_of: dict[str, str]) -> tuple[list[dict], int]:
    """Avalia previsões vencidas. Retorna (avaliações, sem_preço).

    ⚠️ Base comparável: os cenários partem da base de VENDA da previsão
    (default = menor pedida eBay), mas o arquivo tcgcsv guarda o MARKET do
    TCGplayer — níveis diferentes por um spread. Por isso o realizado é
    calculado em termos RELATIVOS sempre que possível: aplica-se o RETORNO
    do market entre a criação e o vencimento ao preço-base da previsão
    (`today_price_usd × market(due)/market(created)`) — retorno contra
    retorno, sem artefato de base. Fallback absoluto (nível do market) só
    quando a previsão é antiga sem `created_at` E a base era tcg_market.
    """
    out: list[dict] = []
    no_price = 0
    for rec in records:
        due = rec.get("due_date") or ""
        if not due or due > as_of.isoformat():
            continue
        pid = str(rec.get("tcgplayer_product_id") or pid_of.get(rec.get("sku_id"), ""))
        base_price = rec.get("today_price_usd")
        m_due = price_map_fn(date.fromisoformat(due)) if pid else None
        due_market = (m_due or {}).get(pid)
        if not due_market:
            no_price += 1
            continue
        realized = None
        created = rec.get("created_at") or ""
        if created and base_price:
            m_created = price_map_fn(date.fromisoformat(created[:10]))
            created_market = (m_created or {}).get(pid)
            if created_market:
                realized = float(base_price) * float(due_market) / float(created_market)
        if realized is None:
            if (rec.get("basis") or "tcg_market") != "tcg_market" or not base_price:
                no_price += 1   # sem base comparável — melhor não avaliar que avaliar torto
                continue
            realized = float(due_market)
        out.append(evaluate_forecast(rec, round(realized, 2)))
    return out, no_price


def render(evals: list[dict], pending: int, no_price: int) -> str:
    lines = ["# Previsão vs realidade — selados", ""]
    if not evals:
        lines.append(f"> Nenhuma previsão vencida avaliável ainda "
                     f"({pending} pendente(s), {no_price} sem preço realizado no arquivo).")
        return "\n".join(lines) + "\n"
    lines.append("| Previsão | Horizonte | Vencimento | Preço na previsão | "
                 "Realizado | Banda | Erro vs base | Recomendação dada |")
    lines.append("|---|---|---|---:|---:|---|---:|---|")
    hits = 0
    abs_err = []
    for e in evals:
        if e["band"] in ("pessimista_a_base", "base_a_otimista"):
            hits += 1
        err = e["base_error_frac"]
        if err is not None:
            abs_err.append(abs(err))
        err_txt = "-" if err is None else f"{err * 100:+.1f}%"
        lines.append(
            f"| {e['forecast_id']} | {e['horizon_days']}d | {e['due_date']} | "
            f"US$ {e['today_price_usd']:.2f} | US$ {e['realized_price_usd']:.2f} | "
            f"{e['band']} | {err_txt} | {e['recommendation']} |")
    lines.append("")
    mae = (sum(abs_err) / len(abs_err) * 100) if abs_err else None
    lines.append(f"**Agregado**: {len(evals)} avaliadas · {hits}/{len(evals)} dentro "
                 f"da faixa pessimista–otimista · erro absoluto médio do cenário base "
                 f"{'n/d' if mae is None else f'{mae:.1f}%'} · {pending} pendente(s) · "
                 f"{no_price} sem preço realizado")
    lines.append("")
    lines.append("_Hit-rate baixo/erro alto = recalibrar `analysis.comparables` "
                 "(percentis/coorte) — o backtest é parte do método._")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Avalia previsões vencidas vs preço real.")
    ap.add_argument("--game", default="pokemon", choices=sorted(S.GAME_PROFILES))
    ap.add_argument("--as-of", default=None, help="data de corte (default: hoje)")
    args = ap.parse_args(argv)

    profile = S.GAME_PROFILES[args.game]
    config = S.load_yaml(ROOT / profile["config"], "config.yaml")
    acfg = analysis_config(config)
    flog = resolve_path(ROOT, (acfg.get("files") or {}).get(
        "forecast_log", "data/forecasts/forecasts_pokemon.jsonl"))
    records, bad = store.read_records(flog)
    if bad:
        print(f"  [eval] {bad} linha(s) corrompida(s) no log — puladas.")
    if not records:
        print(f"  [eval] log de previsões vazio ({flog}) — rode analyze_sealed.py primeiro.")
        return 0
    as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()

    import yaml as _yaml
    reg = _yaml.safe_load((ROOT / profile["registry"]).read_text(encoding="utf-8")) or {}
    pid_of = {s.get("id"): str(s.get("tcgplayer_product_id") or "")
              for s in reg.get("skus", []) or []}

    cat = str((acfg.get("tcgcsv") or {}).get("category_id", "3"))
    cache_dir = resolve_path(ROOT, (acfg.get("tcgcsv") or {}).get(
        "cache_dir", "data/cache/tcgcsv_history"))
    _memo: dict = {}

    def price_map_fn(d: date):
        if d not in _memo:
            _memo[d] = hist.price_map_for_date(d, cat, cache_dir)
        return _memo[d]

    evals, no_price = evaluate_all(records, as_of, price_map_fn, pid_of)
    pending = sum(1 for r in records if (r.get("due_date") or "") > as_of.isoformat())
    print(render(evals, pending, no_price))
    return 0


if __name__ == "__main__":
    from lib.console import harden_stdout
    harden_stdout()
    sys.exit(main())
