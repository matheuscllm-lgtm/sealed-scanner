#!/usr/bin/env python3
"""analyze_sealed.py — camada de ANÁLISE TÉCNICA US (hold vs sell) — CLI.

O que faz: lê o resultado do ÚLTIMO scan da Liga (unified_deals.csv — preço de
compra BR, margem bruta e links vêm de lá) e, para cada produto selado com SKU
casado, responde: **vender imediatamente ao chegar nos EUA, segurar 30/60/90
dias além do ciclo (~24d), evitar a compra, ou dados insuficientes?**

Camada PÓS-SCAN e INFORMATIVA (regras duras, travadas em teste):
  - NÃO altera o scan: classify/compute_margin/CSV_COLUMNS/GREEN-YELLOW-RED
    ficam intocados; o unified_deals.csv sai byte-idêntico com ou sem análise.
  - Nunca inventa dado: fonte ausente → sinal `n/d`/HISTORICO_INSUFICIENTE e
    recomendação DADOS_INSUFICIENTES quando a base não sustenta decisão.
  - Rótulos NEUTROS (classificação técnica): a decisão de capital é do operador.
  - Falha da análise NUNCA derruba o scanner (o hook do run_liga_local só avisa).

Saída: results/[<jogo>/]analysis_<stamp>/{analysis.json, analise_tecnica.md}
(+ log de previsões em data/forecasts/, p/ o evaluate_forecasts conferir depois)
e o markdown impresso no stdout (a 3ª tabela também entra na entrega do
scripts/snapshot.py quando a análise existe).

Uso:
    python analyze_sealed.py                       # último scan Pokémon
    python analyze_sealed.py --game onepiece
    python analyze_sealed.py --offline             # sem rede (sinais degradam p/ n/d)
    python analyze_sealed.py --mock                # exemplo com DADOS SIMULADOS
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
for p in (str(ROOT), str(ROOT / "scripts")):
    if p not in sys.path:
        sys.path.insert(0, p)

import yaml

import sealed_arbitrage_scanner as S
import snapshot as snap
from lib import tcgcsv_history as hist
from lib.analysis import costs, events as events_mod, forecast, recommend, report, score
from lib.analysis import history_store as store
from lib.analysis import signals as sig
from lib.analysis import reprint as reprint_mod
from lib.analysis.profiles import analysis_config, cycle_days, resolve_path

MOCK_DIR = ROOT / "mock_data" / "analysis_sim"


# ── Chases (top cards do set — indicador AUXILIAR de demanda) ──────────────
CHASES_CACHE_TTL_H = 20   # mesmo espírito dos caches tcgcsv da frota (~diário)


def _fetch_group_cards(gid: int, category_id: str, cache_dir: Path,
                       offline: bool, log=print) -> tuple[list[dict], str]:
    """Top cards de um group tcgcsv: ([{id, name, market}], fetched_at).

    Cache em disco com TTL de ~20h (online, cache velho é re-baixado);
    offline → usa o cache que houver, e o `fetched_at` devolvido carimba a
    evidência com a data REAL da coleta (nunca "hoje" para dado velho).
    Sem cache e sem rede = lista vazia (sinal fica n/d)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    cp = cache_dir / f"group_cards_{category_id}_{gid}.json"
    cached_cards: list[dict] = []
    cached_at = ""
    if cp.exists():
        try:
            payload = json.loads(cp.read_text(encoding="utf-8"))
            cached_cards = payload.get("cards", [])
            cached_at = payload.get("fetched_at", "")
        except ValueError:
            pass
    if cached_cards:
        age_ok = False
        try:
            dt = datetime.strptime(cached_at[:19], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc)
            age_ok = (datetime.now(timezone.utc) - dt).total_seconds() \
                < CHASES_CACHE_TTL_H * 3600
        except (ValueError, TypeError):
            age_ok = False
        if age_ok or offline:
            return cached_cards, cached_at
    if offline:
        return cached_cards, cached_at
    base = f"https://tcgcsv.com/tcgplayer/{category_id}/{gid}"
    try:
        def _get(url):
            req = urllib.request.Request(url, headers={"User-Agent": "sealed-scanner/1.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        products = _get(f"{base}/products").get("results", [])
        prices = _get(f"{base}/prices").get("results", [])
    except (urllib.error.URLError, OSError, ValueError) as exc:
        log(f"  [chases] group {gid}: indisponível ({type(exc).__name__}) — "
            + ("usando cache antigo" if cached_cards else "sinal fica n/d"))
        return cached_cards, cached_at
    best: dict[str, float] = {}
    for r in prices:
        if "reverse" in (r.get("subTypeName") or "").lower():
            continue
        m = r.get("marketPrice")
        if isinstance(m, (int, float)) and m > 0:
            pid = str(r.get("productId"))
            best[pid] = max(best.get(pid, 0.0), float(m))
    cards = []
    for prod in products:
        ext = {e.get("name"): e.get("value") for e in (prod.get("extendedData") or [])}
        if not ext.get("Rarity"):
            continue  # sem raridade = selado/acessório; chases são CARDS
        pid = str(prod.get("productId"))
        market = best.get(pid)
        if market:
            cards.append({"id": pid, "name": prod.get("name", ""), "market": market})
    cards.sort(key=lambda c: -c["market"])
    fetched_at = store.utc_now_iso()
    cp.write_text(json.dumps({"fetched_at": fetched_at, "cards": cards[:50]},
                             ensure_ascii=False), encoding="utf-8")
    return cards[:50], fetched_at


def _load_registry_meta(registry_path: Path) -> dict[str, dict]:
    """{sku_id: {product_type, set, set_code, product_id, group_id}}.

    Parse próprio DE PROPÓSITO (não reusa S.build_registry): o dataclass Sku
    do scanner descarta set_code/tcgplayer_group_id/tcgplayer_product_id —
    exatamente os campos que a análise precisa (join tcgcsv + eventos)."""
    data = yaml.safe_load(registry_path.read_text(encoding="utf-8")) or {}
    out: dict[str, dict] = {}
    for sku in data.get("skus", []) or []:
        sid = sku.get("id")
        if not sid:
            continue
        out[sid] = {
            "product_type": sku.get("product_type") or "",
            "set": sku.get("set") or "",
            "set_code": sku.get("set_code") or "",
            "product_id": sku.get("tcgplayer_product_id"),
            "group_id": sku.get("tcgplayer_group_id"),
        }
    return out


def _release_for(group_id, set_meta: dict) -> str | None:
    g = (set_meta.get("groups") or {}).get(str(group_id)) if group_id else None
    return (g or {}).get("publishedOn")


def _latest_events_review(evs: list) -> str | None:
    dates = [e.collected_at for e in evs if e.collected_at]
    return max(dates) if dates else None


def build_analysis(config: dict, acfg: dict, game: str, scan_dir: Path,
                   groups: list[dict], meta: dict,
                   registry_meta: dict, set_meta: dict, all_events: list,
                   supply_by_sku: dict, sold_by_sku: dict, trends_by_sku: dict,
                   ebay_entries: dict, ebay_captured_at: str | None,
                   maps: dict[int, dict[str, float]], price_map_fn,
                   offline: bool, simulated: bool, stamp: str,
                   today: date | None = None, log=print) -> dict:
    """Monta o dict `analysis` completo (puro sobre os dados carregados)."""
    today = today or date.today()
    scfg = acfg.get("signals") or {}
    ccfg = acfg.get("confidence") or {}
    net_factor = float(acfg.get("net_factor", 0.70))
    cyc = cycle_days(acfg)
    fx = meta.get("fx") or (config.get("currency") or {}).get("usd_brl") or 0.0
    horizons = [int(h) for h in acfg.get("horizons_days", [30, 60, 90])]
    min_margin = float((acfg.get("buy_price") or {}).get("min_margin_over_cost", 0.25))
    annual_cap = float((acfg.get("capital") or {}).get("annual_cost_pct", 0.15))
    basis_mode = str(acfg.get("sale_price_basis") or "ebay_then_tcg")
    events_review_at = _latest_events_review(all_events)
    ev_max_age = int(ccfg.get("events_reviewed_max_age_days", 45))
    # Idade da referência eBay relativa ao `today` do RUN (determinístico no
    # modo simulado/testes; no run real today = hoje, mesmo resultado).
    ebay_age = None
    if ebay_captured_at:
        try:
            cap = date.fromisoformat(str(ebay_captured_at)[:10])
            ebay_age = (today - cap).days
        except ValueError:
            ebay_age = None

    # comparáveis por tipo: {product_type: [(pid, release_date)]}
    comps_by_type: dict[str, list] = {}
    for sid, m in registry_meta.items():
        rel = _release_for(m.get("group_id"), set_meta)
        if m.get("product_id") and rel:
            try:
                rd = date.fromisoformat(str(rel).replace("/", "-")[:10])
            except ValueError:
                continue
            comps_by_type.setdefault(m["product_type"], []).append(
                (str(m["product_id"]), rd, sid))

    cat = str((acfg.get("tcgcsv") or {}).get("category_id", "3"))
    chases_cache = resolve_path(ROOT, (acfg.get("tcgcsv") or {}).get(
        "cache_dir", "data/cache/tcgcsv_history"))
    chases_by_group: dict = {}

    products: list[dict] = []
    skipped_no_sku = 0
    for g in groups:
        sku_id = g.get("sku")
        if not sku_id:
            skipped_no_sku += 1
            continue
        rmeta = registry_meta.get(sku_id) or {}
        pid = str(rmeta.get("product_id") or "")
        gid = rmeta.get("group_id")
        release = _release_for(gid, set_meta)
        ref_row = g.get("ref") or {}
        buy_price = g.get("br_ref")
        tcg_usd = g.get("tcg_usd")

        # ── sinais (cada dimensão separada, com fonte/data) ────────────────
        # VOLUME honesto: só a captura Terapeak MAIS RECENTE (o store é
        # append-only e capturas mensais repetem os mesmos anúncios — somar
        # tudo inflaria unidades/semana e sell-through cumulativamente).
        sold_recs = store.latest_capture(sold_by_sku.get(sku_id, []))
        supply_recs = supply_by_sku.get(sku_id, [])
        ebay_entry = (ebay_entries or {}).get(sku_id) or {}
        active_count = ebay_entry.get("active_count")
        if active_count is None and supply_recs:
            last = max(supply_recs, key=lambda r: r.get("captured_at") or "")
            active_count = last.get("active_count")

        pcts = hist.pct_changes(pid, tcg_usd or 0.0, maps) if pid else {}
        s_trend = sig.price_trend(pid, tcg_usd, pcts, sold_recs, scfg)
        s_supply = sig.supply_trend(supply_recs, scfg)
        s_liq = sig.liquidity(active_count, sold_recs, scfg)
        s_cycle = sig.print_cycle(release, scfg, today)
        sku_events = events_mod.events_for_sku(all_events, sku_id,
                                               rmeta.get("set_code") or "")
        s_reprint = reprint_mod.reprint_risk(
            (set_meta.get("groups", {}).get(str(gid), {}) or {}).get("name")
            or rmeta.get("set") or "",
            s_cycle.value, sku_events, scfg)
        if gid not in chases_by_group:
            cards, cards_as_of = (_fetch_group_cards(gid, cat, chases_cache, offline, log)
                                  if gid else ([], ""))
            top_n = int(scfg.get("chases_top_n", 10))
            chases = []
            for c in cards[:top_n]:
                cpcts = hist.pct_changes(c["id"], c["market"], maps)
                chases.append({"product_id": c["id"], "name": c["name"],
                               "price_usd": c["market"],
                               "pct_30": cpcts.get(30), "pct_90": cpcts.get(90)})
            chases_by_group[gid] = (chases, cards_as_of)
        g_chases, g_as_of = chases_by_group.get(gid) or ([], "")
        s_set = sig.set_strength(g_chases, scfg, as_of=g_as_of)
        signals = {"price_trend": s_trend, "supply": s_supply, "liquidity": s_liq,
                   "print_cycle": s_cycle, "set_strength": s_set,
                   "reprint_risk": s_reprint}

        # ── base de venda (bruta) ──────────────────────────────────────────
        ebay_usd = ebay_entry.get("usd") if ebay_entry.get("status") == "ok" else None
        if basis_mode == "tcg_only":
            gross_today, basis = tcg_usd, "tcg_market"
        else:
            gross_today = ebay_usd if ebay_usd else tcg_usd
            basis = "ebay_active_min" if ebay_usd else "tcg_market"

        # ── cenários por horizonte (comparáveis alinhados por idade) ───────
        comparables = [(cpid, crel) for cpid, crel, csid in
                       comps_by_type.get(rmeta.get("product_type") or "", [])
                       if csid != sku_id]
        rel_date = None
        if release:
            try:
                rel_date = date.fromisoformat(str(release).replace("/", "-")[:10])
            except ValueError:
                rel_date = None
        max_cohort = int((acfg.get("comparables") or {}).get("max_cohort", 40))

        def _cohort(window: int):
            # (não curto-circuita em offline: o price_map_fn já devolve None
            # sem rede — e no modo simulado ele lê os mapas da fixture)
            if rel_date is None:
                return [], {"skipped": "sem data de lançamento"}
            return forecast.cohort_returns(rel_date, comparables, window, today,
                                           price_map_fn, max_cohort)

        scenarios: dict[str, dict] = {}
        cohort_stats: dict[str, dict] = {}
        sell_gross = gross_today
        sell_gross_applied = False
        if gross_today:
            rets_cycle, st_cycle = _cohort(cyc)
            cohort_stats["cycle"] = st_cycle
            sc_cycle = forecast.build_scenarios(gross_today, rets_cycle, s_supply,
                                                s_reprint, s_cycle, s_trend, acfg,
                                                f"~{cyc}d (ciclo)")
            if sc_cycle:
                sell_gross = sc_cycle["base"].price_usd
                sell_gross_applied = True
            for h in horizons:
                rets, st_h = _cohort(cyc + h)
                cohort_stats[str(h)] = st_h
                sc = forecast.build_scenarios(gross_today, rets, s_supply,
                                              s_reprint, s_cycle, s_trend, acfg,
                                              f"ciclo+{h}d")
                if sc:
                    scenarios[str(h)] = {k: v.as_dict() for k, v in sc.items()}

        # ── financeiro (fator único configurável) ──────────────────────────
        sell_now: dict = {"basis": basis, "gross_usd": gross_today,
                          "gross_usd_realizacao": sell_gross,
                          "projecao_aplicada": sell_gross_applied,
                          "net_factor": net_factor}
        lucro_hoje = None
        if sell_gross and buy_price and fx:
            liq_usd = costs.receita_liquida_usd(sell_gross, net_factor)
            lucro_hoje = costs.lucro_liquido_brl(liq_usd, fx, buy_price)
            sell_now.update({
                "receita_liquida_brl": round(liq_usd * fx, 2),
                "lucro_liquido_brl": lucro_hoje,
                "margem_sobre_custo": costs.margem_sobre_custo(lucro_hoje, buy_price),
                "preco_maximo_compra_brl": costs.preco_maximo_compra_brl(
                    sell_gross, net_factor, fx, min_margin),
            })
        per_horizon: dict = {}
        if lucro_hoje is not None and buy_price and fx:
            for h_str, sc in scenarios.items():
                h = int(h_str)
                esperado = costs.lucro_esperado_brl(sc, net_factor, fx, buy_price)
                cap = costs.custo_capital_brl(buy_price, annual_cap, h)
                per_horizon[h] = {
                    "lucro_esperado_brl": esperado,
                    "custo_capital_brl": cap,
                    "valor_de_esperar_brl": costs.valor_de_esperar_brl(
                        esperado, lucro_hoje, cap),
                }

        # ── confiança (qualidade dos DADOS, pesos no config) ───────────────
        quality = {
            "price_history_180d": 180 in pcts,
            "price_history_90d": 90 in pcts,
            "supply_series": not s_supply.insufficient,
            "ebay_ref_fresh": bool(ebay_usd) and ebay_age is not None and ebay_age <= 7,
            "sold_data_imported": bool(sold_recs),
            "set_meta_known": bool(release),
            "events_reviewed": bool(events_review_at) and (
                (today - date.fromisoformat(events_review_at[:10])).days <= ev_max_age
                if events_review_at else False),
        }
        conf = recommend.confidence_pct(quality, ccfg.get("weights") or {})
        rec = recommend.recommend(lucro_hoje, per_horizon, conf, signals, acfg, today)

        comp_scores = score.component_scores(sell_now.get("margem_sobre_custo"),
                                             signals, conf)
        total, missing_comp = score.total_score(comp_scores,
                                                acfg.get("score_weights") or {})

        evidence: list[dict] = []
        for s in signals.values():
            evidence.extend(s.evidence)
        if buy_price:
            evidence.append({"fact": f"compra BR: R$ {buy_price:.2f} "
                                     f"(margem bruta do scan {g.get('margem') or 0:.1f}%)",
                             "source_type": ref_row.get("Fonte") or "liga",
                             "source_url": (ref_row.get("URL") or "").strip(),
                             "collected_at": meta.get("stamp") or stamp})
        if ebay_usd:
            evidence.append({"fact": f"menor anúncio ativo eBay US: US$ {ebay_usd:.2f} (pedida)",
                             "source_type": "ebay_active",
                             "source_url": ebay_entry.get("url") or "",
                             "collected_at": ebay_captured_at or ""})
        tr = trends_by_sku.get(sku_id) or []
        if tr:
            last = max(tr, key=lambda r: r.get("date") or "")
            evidence.append({"fact": f"interesse de busca (Google Trends, termo "
                                     f"'{last.get('term')}'): {last.get('value')} "
                                     f"em {last.get('date')}",
                             "source_type": "trends_import",
                             "source_url": last.get("source_url") or "",
                             "collected_at": last.get("collected_at") or ""})

        products.append({
            "sku_id": sku_id,
            "produto": g.get("produto"),
            "product_type": rmeta.get("product_type"),
            "set_name": rmeta.get("set"),
            "set_code": rmeta.get("set_code"),
            "tcgplayer_product_id": rmeta.get("product_id"),
            "buy": {"price_brl": buy_price,
                    "url": (ref_row.get("URL") or "").strip(),
                    "source": ref_row.get("Fonte") or "",
                    "seller": ref_row.get("Vendedor") or "",
                    "bucket": g.get("bucket"),
                    "margem_bruta_scan_pct": g.get("margem"),
                    "n_ofertas": g.get("n_ofertas"),
                    "qtd_total": g.get("qtd_total")},
            "sell_now": sell_now,
            "signals": {k: v.as_dict() for k, v in signals.items()},
            "scenarios": scenarios,
            "cohort_stats": cohort_stats,
            "expected": {"lucro_hoje_brl": lucro_hoje,
                         "por_horizonte": {str(h): v for h, v in per_horizon.items()}},
            "recommendation": rec.as_dict(),
            "score": {"total": total, "components": comp_scores,
                      "missing": missing_comp},
            "evidence": evidence,
            "data_quality": {"confidence_pct": conf, "inputs": quality,
                             "missing": [k for k, ok in quality.items() if not ok]},
        })

    products.sort(key=lambda p: -(p["score"]["total"] or -1))
    return {
        "schema": 1,
        "generated_at": store.utc_now_iso(),
        "stamp": stamp,
        "game": game,
        "scan_dir": scan_dir.name,
        "usd_brl": fx,
        "fx_source": meta.get("fx_source") or "",
        "cycle_days": cyc,
        "net_factor": net_factor,
        "simulated": simulated,
        "offline": offline,
        "skipped_sem_sku": skipped_no_sku,
        "config_snapshot": {"horizons_days": horizons,
                            "sale_price_basis": basis_mode,
                            "capital_annual_pct": annual_cap,
                            "min_margin_over_cost": min_margin},
        "products": products,
    }


def append_forecast_log(analysis: dict, path: Path) -> int:
    recs: list[dict] = []
    created = analysis["generated_at"][:10]
    for p in analysis.get("products") or []:
        for h_str, sc in (p.get("scenarios") or {}).items():
            h = int(h_str)
            due = (date.fromisoformat(created) +
                   timedelta(days=analysis.get("cycle_days", 0) + h)).isoformat()
            recs.append({
                "forecast_id": f"{analysis['stamp']}:{p['sku_id']}:{h}",
                "created_at": created,
                "sku_id": p["sku_id"],
                "tcgplayer_product_id": p.get("tcgplayer_product_id"),
                "horizon_days": h,
                "cycle_days": analysis.get("cycle_days"),
                "due_date": due,
                "today_price_usd": (p.get("sell_now") or {}).get("gross_usd"),
                "basis": (p.get("sell_now") or {}).get("basis"),
                "scenarios": sc,
                "recommendation": (p.get("recommendation") or {}).get("state"),
                "confidence_pct": (p.get("recommendation") or {}).get("confidence_pct"),
            })
    return store.append_records(path, recs)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Análise técnica US (hold vs sell) sobre o último scan de selados.")
    ap.add_argument("--game", default=None, choices=sorted(S.GAME_PROFILES))
    ap.add_argument("--config", default=None, help="config.yaml (default: do --game)")
    ap.add_argument("--scan-dir", default=None,
                    help="run específica (default: o unified_* mais recente do jogo)")
    ap.add_argument("--offline", action="store_true",
                    help="sem rede: histórico/chases degradam p/ n/d (honesto)")
    ap.add_argument("--mock", action="store_true",
                    help="exemplo com DADOS SIMULADOS (mock_data/analysis_sim/)")
    ap.add_argument("--no-forecast-log", action="store_true",
                    help="não registrar previsões no log (previsão-vs-real)")
    ap.add_argument("--stamp", default=None, help="carimbo do run (default: agora)")
    ap.add_argument("--today", default=None,
                    help="data-base YYYY-MM-DD (testes/mock; default: hoje — "
                         "no --mock é fixada em 2026-08-29 p/ determinismo)")
    ap.add_argument("--force", action="store_true",
                    help="roda mesmo com analysis.enabled=false no config")
    args = ap.parse_args(argv)

    game = S.resolve_cli_game(args)
    profile = S.GAME_PROFILES[game]
    cfg_path = Path(args.config) if args.config else ROOT / profile["config"]
    config = S.load_yaml(cfg_path, "config.yaml")
    acfg = analysis_config(config)
    if not acfg.get("enabled") and not args.force and not args.mock:
        print(f"  [analysis] desligada no config do jogo {game!r} "
              "(analysis.enabled=false) — nada a fazer. Use --force p/ rodar.")
        return 0

    simulated = bool(args.mock)
    offline = bool(args.offline or args.mock)
    stamp = args.stamp or datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── fontes do run ──────────────────────────────────────────────────────
    if args.mock:
        scan_dir = MOCK_DIR / "unified_fixture"
        registry_path = MOCK_DIR / "sku_registry_sim.yaml"
        set_meta_path = MOCK_DIR / "set_meta_sim.json"
        events_path = MOCK_DIR / "events_sim.yaml"
        supply_path = MOCK_DIR / "supply_sim.jsonl"
        sold_path = MOCK_DIR / "ebay_sold_sim.jsonl"
        trends_path = MOCK_DIR / "trends_sim.jsonl"
        ebay_ref_path = MOCK_DIR / "ebay_reference_sim.json"
        price_maps_path = MOCK_DIR / "price_maps_sim.json"
        results_root = MOCK_DIR / "out"
    else:
        scan_dir = Path(args.scan_dir) if args.scan_dir else \
            snap.latest_unified_dir(S.results_root_for(game, ROOT))
        if scan_dir is None or not (Path(scan_dir) / "unified_deals.csv").exists():
            print("  [analysis] nenhum scan unified_* encontrado — rode "
                  f"`python run_liga_local.py --game {game}` primeiro.")
            return 0
        scan_dir = Path(scan_dir)
        registry_path = ROOT / profile["registry"]
        files = acfg.get("files") or {}
        set_meta_path = resolve_path(ROOT, files.get("set_meta", "data/set_meta.json"))
        events_path = resolve_path(ROOT, files.get("events", "data/events_pokemon.yaml"))

        # path vazio no config = store DESLIGADO (None → no-op) — resolver ""
        # daria a RAIZ do repo e a leitura estouraria em IsADirectoryError.
        def _optional_path(key: str) -> Path | None:
            rel = str(files.get(key) or "").strip()
            return resolve_path(ROOT, rel) if rel else None

        supply_path = _optional_path("supply_history")
        sold_path = _optional_path("sold_imports")
        trends_path = _optional_path("trends_imports")
        ebay_ref_path = resolve_path(
            ROOT, S.ebay_reference_settings(config)["reference_file"])
        results_root = S.results_root_for(game, ROOT)

    rows = snap.collect_rows_unified(scan_dir)
    if not rows:
        print(f"  [analysis] {scan_dir}/unified_deals.csv sem linhas válidas — nada a analisar.")
        return 0
    groups = snap.group_products(rows)
    meta = snap.load_run_meta(scan_dir)

    registry_meta = _load_registry_meta(registry_path)
    set_meta = {}
    if set_meta_path.exists():
        try:
            set_meta = json.loads(set_meta_path.read_text(encoding="utf-8"))
        except ValueError:
            print(f"  [analysis] {set_meta_path.name} ilegível — datas de lançamento n/d.")
    else:
        print(f"  [analysis] {set_meta_path.name} ausente — rode build_set_meta.py "
              "(datas de lançamento ficam n/d).")
    all_events, rejected = events_mod.load_events(events_path)
    if rejected:
        print(f"  [analysis] {rejected} evento(s) rejeitado(s) por falta de fonte/campo.")

    supply_recs, bad_s = store.read_records(supply_path) if supply_path else ([], 0)
    sold_recs, bad_v = store.read_records(sold_path) if sold_path else ([], 0)
    trends_recs, bad_t = store.read_records(trends_path) if trends_path else ([], 0)
    for label, bad in (("supply", bad_s), ("sold", bad_v), ("trends", bad_t)):
        if bad:
            print(f"  [analysis] store {label}: {bad} linha(s) corrompida(s) pulada(s).")

    ebay_data = S.load_json_optional(ebay_ref_path) or {}
    ebay_entries = ebay_data.get("entries") or {}
    ebay_captured_at = ebay_data.get("captured_at")

    # ── histórico de preço (arquivo tcgcsv) ────────────────────────────────
    cat = str((acfg.get("tcgcsv") or {}).get("category_id", "3"))
    cache_dir = resolve_path(ROOT, (acfg.get("tcgcsv") or {}).get(
        "cache_dir", "data/cache/tcgcsv_history"))
    if args.today:
        today = date.fromisoformat(args.today)
    elif args.mock:
        today = date(2026, 8, 29)   # data-base FIXA do exemplo simulado
    else:
        today = date.today()
    _memo: dict = {}
    if args.mock:
        fixture = json.loads(price_maps_path.read_text(encoding="utf-8")) \
            if price_maps_path.exists() else {}
        maps = {int(k): v for k, v in (fixture.get("windows") or {}).items()}
        dates_fx = fixture.get("dates") or {}

        def price_map_fn(d: date):
            return dates_fx.get(d.isoformat())
    elif offline or not hist.py7zr_available():
        if not offline and not hist.py7zr_available():
            print("  [analysis] py7zr ausente — histórico de preço n/d "
                  "(pip install py7zr habilita).")
        maps = {}

        def price_map_fn(d: date):
            return None
    else:
        windows = tuple(int(w) for w in (acfg.get("signals") or {}).get(
            "trend_windows_days", [30, 90, 180]))
        maps = hist.build_price_maps(today, windows, cat, cache_dir, log=print)

        def price_map_fn(d: date):
            if d not in _memo:
                _memo[d] = hist.price_map_for_date(d, cat, cache_dir)
            return _memo[d]

    trends_by = store.by_sku(trends_recs)
    analysis = build_analysis(
        config, acfg, game, scan_dir, groups, meta, registry_meta,
        set_meta, all_events, store.by_sku(supply_recs), store.by_sku(sold_recs),
        trends_by, ebay_entries, ebay_captured_at, maps, price_map_fn,
        offline, simulated, stamp, today=today)

    out_dir = results_root / f"analysis_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "analysis.json").write_text(
        json.dumps(analysis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = report.render_markdown(analysis)
    (out_dir / "analise_tecnica.md").write_text(md, encoding="utf-8")

    if not simulated and not args.no_forecast_log:
        flog = resolve_path(ROOT, (acfg.get("files") or {}).get(
            "forecast_log", "data/forecasts/forecasts.jsonl"))
        n = append_forecast_log(analysis, flog)
        if n:
            print(f"  [analysis] {n} previsão(ões) registradas em {flog} "
                  "(conferência futura: scripts/evaluate_forecasts.py)")

    print(f"  [analysis] artefato: {out_dir}")
    print()
    print(md)
    return 0


if __name__ == "__main__":
    from lib.console import harden_stdout
    harden_stdout()
    sys.exit(main())
