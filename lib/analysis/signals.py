"""lib/analysis/signals.py — os 5 sinais de mercado, calculados SEPARADAMENTE.

Cada sinal responde uma pergunta própria, com fonte/data registradas, e retorna
um `SignalResult` com valor + tendência + evidências + `insufficient` honesto.
Ausência de dado NUNCA vira evidência favorável — vira `n/d` /
`HISTORICO_INSUFICIENTE` e derruba a confiança da recomendação.

  2.1 price_trend    — preço realizado/market: tcgcsv (arquivo) + Terapeak.
  2.2 liquidity      — volume/liquidez: SÓ dados de venda (Terapeak) + ativos.
                       Market Price do TCGplayer NUNCA mede volume.
  2.3 supply_trend   — anúncios ativos no eBay ao longo do tempo (snapshots).
  2.4 (reprint)      — vive em reprint.py (eventos + risco estrutural).
  2.5 set_strength   — demanda pelas top chases do set (indicador AUXILIAR;
                       não prova escassez do selado — e não é análise de singles).

Funções PURAS sobre dados injetados — zero I/O aqui (testável offline).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime, timezone


@dataclass
class SignalResult:
    label: str                      # rótulo humano ("alta", "caindo", "n/d"...)
    value: float | None = None      # valor principal (fração/contagem)
    detail: dict = field(default_factory=dict)
    evidence: list[dict] = field(default_factory=list)
    insufficient: bool = False

    def as_dict(self) -> dict:
        return {"label": self.label, "value": self.value, "detail": self.detail,
                "evidence": self.evidence, "insufficient": self.insufficient}


def _ev(fact: str, source_type: str, source_url: str, collected_at: str) -> dict:
    return {"fact": fact, "source_type": source_type, "source_url": source_url,
            "collected_at": collected_at}


def _parse_dt(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.strptime(iso[:19].rstrip("Z"), "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(iso[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


# ── 2.1 Tendência de preço ─────────────────────────────────────────────────
def price_trend(product_id: str, today_usd: float | None,
                pct_by_window: dict[int, float],
                sold_records: list[dict], scfg: dict,
                archive_url: str = "https://tcgcsv.com/archive/tcgplayer/") -> SignalResult:
    """Tendência do preço do SELADO: variação real por janela (tcgcsv) +
    mediana vendida (Terapeak, quando importado) + volatilidade + spread.

    `pct_by_window` vem de lib.tcgcsv_history.pct_changes (frações).
    `sold_records` = registros terapeak_capture do SKU (já filtrados).
    """
    flat = float(scfg.get("trend_flat_band", 0.05))
    detail: dict = {}
    evidence: list[dict] = []
    if today_usd and pct_by_window:
        for w in sorted(pct_by_window):
            detail[f"pct_{w}d"] = round(pct_by_window[w], 4)
            evidence.append(_ev(
                f"variação {w}d do market TCGplayer: {pct_by_window[w]:+.1%}",
                "tcgcsv_archive", archive_url, date.today().isoformat()))
        # inclinação simples: média das variações normalizadas por janela
        slopes = [pct_by_window[w] / w for w in pct_by_window]
        detail["slope_per_day"] = round(sum(slopes) / len(slopes), 6)
        # volatilidade: desvio-padrão das variações por janela (proxy honesto
        # com poucos pontos; rotulado como aproximação)
        if len(pct_by_window) >= 2:
            detail["volatility"] = round(statistics.pstdev(pct_by_window.values()), 4)
    # Mediana vendida (Terapeak): ponderada por total_sold da captura.
    med = sold_weighted_median(sold_records)
    if med is not None:
        detail["sold_median_usd"] = med
        src_file = (sold_records[0].get("source_url") or "terapeak") if sold_records else "terapeak"
        evidence.append(_ev(f"mediana vendida (Terapeak): US$ {med:.2f}",
                            "terapeak_capture", src_file,
                            sold_records[0].get("collected_at", "") if sold_records else ""))
        if today_usd:
            detail["spread_sold_vs_market"] = round((med - today_usd) / today_usd, 4)
        pmed = sold_weighted_median([r for r in sold_records if r.get("is_probstein")])
        if pmed is not None:
            detail["probstein_median_usd"] = pmed
    headline = None
    for w in (90, 180, 30):
        if f"pct_{w}d" in detail:
            headline = (detail[f"pct_{w}d"], w)
            break
    if headline is None:
        return SignalResult("n/d (sem histórico de preço)", None, detail,
                            evidence, insufficient=True)
    pct, w = headline
    label = "alta" if pct > flat else "queda" if pct < -flat else "estável"
    return SignalResult(f"{label} ({pct:+.0%} em {w}d)", pct, detail, evidence)


def sold_weighted_median(sold_records: list[dict]) -> float | None:
    """Mediana do preço vendido ponderada por unidades (total_sold por anúncio).

    A tabela do Terapeak é AGREGADA por anúncio (avg_sold_price × total_sold) —
    não temos transação a transação, então expandimos por unidade (honesto:
    aproximação declarada; melhor proxy disponível sem a API restrita de sold).
    """
    pairs = []
    for r in sold_records:
        price = r.get("avg_sold_price_usd")
        qty = r.get("total_sold") or 0
        if isinstance(price, (int, float)) and price > 0 and qty:
            pairs.append((float(price), int(qty)))
    if not pairs:
        return None
    expanded: list[float] = []
    for price, qty in pairs:
        expanded.extend([price] * min(int(qty), 10_000))
    return round(statistics.median(expanded), 2) if expanded else None


# ── 2.2 Volume e liquidez ──────────────────────────────────────────────────
def liquidity(active_count: int | None, sold_records: list[dict],
              scfg: dict) -> SignalResult:
    """Liquidez: unidades vendidas na janela capturada + vendas/semana +
    sell-through + share Probstein. Fonte de volume = SÓ vendas (Terapeak);
    o nº de anúncios ativos entra como denominador do sell-through.
    """
    hi = int(scfg.get("liquidity_active_high", 8))
    lo = int(scfg.get("liquidity_active_low", 3))
    detail: dict = {}
    evidence: list[dict] = []
    units = sum(int(r.get("total_sold") or 0) for r in sold_records)
    lookbacks = {int(r.get("lookback_days") or 0) for r in sold_records if r.get("lookback_days")}
    lookback = max(lookbacks) if lookbacks else None
    if sold_records and lookback:
        per_week = units / (lookback / 7.0)
        detail.update({"units_sold": units, "lookback_days": lookback,
                       "sales_per_week": round(per_week, 2)})
        evidence.append(_ev(
            f"{units} unidades vendidas em {lookback}d (Terapeak) ≈ {per_week:.1f}/semana",
            "terapeak_capture", sold_records[0].get("source_url", ""),
            sold_records[0].get("collected_at", "")))
        sellers = {r.get("seller") for r in sold_records if r.get("seller")}
        if sellers:
            detail["distinct_sellers"] = len(sellers)
        pb_units = sum(int(r.get("total_sold") or 0) for r in sold_records if r.get("is_probstein"))
        if units:
            detail["probstein_share"] = round(pb_units / units, 3)
        null_seller = sum(1 for r in sold_records if not r.get("seller"))
        if null_seller:
            detail["listings_sem_seller"] = null_seller  # encerrados >90d: getItem não devolve
    if active_count is not None:
        detail["active_count"] = int(active_count)
        if units and lookback:
            detail["sell_through"] = round(units / (units + int(active_count)), 3) \
                if (units + active_count) else None
    if not sold_records:
        if active_count is None:
            return SignalResult("n/d (sem dado de vendas nem de ativos)", None,
                                detail, evidence, insufficient=True)
        # Só ativos: dá para rotular a PROFUNDIDADE do mercado, não o volume.
        label = ("alta" if active_count >= hi else
                 "média" if active_count >= lo else "baixa")
        detail["basis"] = "só anúncios ativos (sem vendas importadas)"
        return SignalResult(f"{label} (proxy: {active_count} ativos; sem sold)",
                            float(active_count), detail, evidence,
                            insufficient=True)  # volume real segue faltando
    spw = detail.get("sales_per_week") or 0.0
    label = "alta" if spw >= 3 else "média" if spw >= 1 else "baixa"
    return SignalResult(f"{label} ({spw:.1f} vendas/semana)", spw, detail, evidence)


# ── 2.3 Disponibilidade e evolução da oferta ───────────────────────────────
def supply_trend(supply_records: list[dict], scfg: dict,
                 now: datetime | None = None) -> SignalResult:
    """Evolução dos anúncios ativos: variação nas janelas configuradas.

    `supply_records` = snapshots {captured_at, active_count, ...} do SKU.
    <2 snapshots utilizáveis → HISTORICO_INSUFICIENTE (a série começa vazia
    por design — as primeiras semanas saem honestas, sem chute).
    """
    now = now or datetime.now(timezone.utc)
    windows = [int(w) for w in scfg.get("supply_windows_days", [7, 30, 90])]
    falling = float(scfg.get("supply_falling_strong", -0.25))
    rising = float(scfg.get("supply_rising_strong", 0.25))
    pts = []
    for r in supply_records:
        dt = _parse_dt(r.get("captured_at") or "")
        cnt = r.get("active_count")
        if dt and isinstance(cnt, (int, float)):
            pts.append((dt, int(cnt), r))
    pts.sort()
    if len(pts) < 2:
        return SignalResult("HISTORICO_INSUFICIENTE (série de oferta começando)",
                            None, {"points": len(pts)}, [], insufficient=True)
    latest_dt, latest_cnt, latest_rec = pts[-1]
    detail: dict = {"active_now": latest_cnt, "points": len(pts)}
    evidence = [_ev(f"{latest_cnt} anúncios ativos no eBay US",
                    latest_rec.get("source_type", "ebay_active"),
                    latest_rec.get("source_url", ""),
                    latest_rec.get("captured_at", ""))]
    headline = None
    for w in sorted(windows):
        target = latest_dt.timestamp() - w * 86400
        past = [p for p in pts[:-1] if p[0].timestamp() <= target + 86400 * 2]
        if not past:
            continue
        base_dt, base_cnt, base_rec = past[-1]
        if base_cnt <= 0:
            continue
        delta = (latest_cnt - base_cnt) / base_cnt
        detail[f"delta_{w}d"] = round(delta, 4)
        evidence.append(_ev(
            f"anúncios ativos {base_cnt} → {latest_cnt} em ~{w}d ({delta:+.0%})",
            base_rec.get("source_type", "ebay_active"),
            base_rec.get("source_url", ""), base_rec.get("captured_at", "")))
        if headline is None or w in (30,):
            headline = (delta, w)
    if headline is None:
        return SignalResult("HISTORICO_INSUFICIENTE (janelas sem par de snapshots)",
                            float(latest_cnt), detail, evidence, insufficient=True)
    delta, w = headline
    label = ("caindo forte" if delta <= falling else
             "subindo forte" if delta >= rising else
             "caindo" if delta < 0 else "subindo" if delta > 0 else "estável")
    return SignalResult(f"{label} ({delta:+.0%} em ~{w}d)", delta, detail, evidence)


# ── 2.5 Demanda pelas chases ───────────────────────────────────────────────
def set_strength(chases: list[dict], scfg: dict) -> SignalResult:
    """Demanda pelas top chases do set (indicador AUXILIAR — não prova
    escassez do selado; não é análise de singles).

    `chases` = [{"product_id", "name", "price_usd", "pct_30", "pct_90"}]
    (top-N por market price do MESMO group_id, com variações do arquivo).
    """
    top_conc = int(scfg.get("chases_concentration_top", 3))
    if not chases:
        return SignalResult("n/d (chases não coletadas)", None, {}, [],
                            insufficient=True)
    with_pct = [c for c in chases if isinstance(c.get("pct_90"), (int, float))]
    detail: dict = {"top_n": len(chases)}
    total_val = sum(c.get("price_usd") or 0.0 for c in chases)
    if total_val > 0:
        conc = sum(sorted((c.get("price_usd") or 0.0 for c in chases),
                          reverse=True)[:top_conc]) / total_val
        detail[f"concentration_top{top_conc}"] = round(conc, 3)
    evidence = [_ev(
        f"top {len(chases)} chases do set somam US$ {total_val:.0f} (market)",
        "tcgcsv", "https://tcgcsv.com/", date.today().isoformat())]
    if not with_pct:
        detail["basis"] = "sem histórico das chases"
        return SignalResult("n/d (sem histórico das chases)", None, detail,
                            evidence, insufficient=True)
    # variação agregada ponderada pelo valor da chase
    wsum = sum(c.get("price_usd") or 0.0 for c in with_pct) or 1.0
    agg90 = sum((c.get("pct_90") or 0.0) * (c.get("price_usd") or 0.0)
                for c in with_pct) / wsum
    up = sum(1 for c in with_pct if (c.get("pct_90") or 0.0) > 0)
    down = sum(1 for c in with_pct if (c.get("pct_90") or 0.0) < 0)
    detail.update({"agg_pct_90d": round(agg90, 4), "chases_up": up,
                   "chases_down": down})
    evidence.append(_ev(
        f"chases 90d: {agg90:+.0%} agregado · {up} subindo × {down} caindo",
        "tcgcsv_archive", "https://tcgcsv.com/archive/tcgplayer/",
        date.today().isoformat()))
    label = ("forte" if agg90 > 0.05 and up > down else
             "fraca" if agg90 < -0.05 and down > up else "neutra")
    return SignalResult(f"{label} ({agg90:+.0%} 90d, {up}↑/{down}↓)",
                        agg90, detail, evidence)


# ── Ciclo de impressão (idade do set) ──────────────────────────────────────
def print_cycle(release_iso: str | None, scfg: dict,
                today: date | None = None) -> SignalResult:
    """Posição no ciclo de impressão pela IDADE REAL do set (publishedOn do
    tcgcsv, nunca inferida). Sem data → n/d."""
    today = today or date.today()
    late = int(scfg.get("print_cycle_late_months", 18))
    old = int(scfg.get("print_cycle_old_months", 30))
    if not release_iso:
        return SignalResult("n/d (data de lançamento desconhecida)", None, {},
                            [], insufficient=True)
    try:
        rel = date.fromisoformat(release_iso.replace("/", "-")[:10])
    except ValueError:
        return SignalResult("n/d (data de lançamento ilegível)", None, {},
                            [], insufficient=True)
    months = (today.year - rel.year) * 12 + (today.month - rel.month)
    label = ("fora da janela de impressão (provável)" if months >= old else
             "fim da janela de impressão" if months >= late else
             "em impressão (provável)")
    return SignalResult(f"{label} ({months}m)", float(months),
                        {"age_months": months, "release": rel.isoformat()},
                        [_ev(f"lançado em {rel.isoformat()} ({months} meses)",
                             "tcgcsv", "https://tcgcsv.com/", today.isoformat())])
