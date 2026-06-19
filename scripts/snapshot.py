#!/usr/bin/env python3
"""
snapshot.py — gera a TABELA DE ENTREGA em Markdown a partir do scan.

⭐ ESTE É O GERADOR CANÔNICO E OBRIGATÓRIO DA ENTREGA (ver README invariante #7).
Quando for entregar o resultado de um scan ao operador, há **um caminho só**:
rode este script sobre o `unified_deals.csv` da run e cole/mostre o markdown
que ele gerou — NUNCA monte a tabela à mão. O formato (colunas, ordem, links,
`Qtd disponível`, flags de suspeita) é a única fonte de verdade do layout.

A tabela traz, para CADA deal:
  - Status (🟢 GREEN / 🟡 YELLOW / 🔴 RED),
  - Produto canônico (nome/descrição) + Tipo,
  - `Qtd disponível` (estoque do vendedor — o operador importa em LOTE),
  - Preço BR (R$) com link CLICÁVEL pro anúncio (verificável),
  - Preço US (R$) com link CLICÁVEL pra página TCGPlayer de referência (verificável),
  - Margem bruta % + Δ R$/unid,
  - flag ⚠️ de suspeita quando o anúncio precisa de conferência manual.

Lê o `unified_deals.csv` produzido por `run_all_sources.py` (a saída canônica
do orquestrador). Se não houver `unified_deals.csv`, cai pros CSVs por bucket
legados (`real_opportunities.csv` etc.) só por compatibilidade.

Uso:
    python scripts/snapshot.py
        # -> usa o results/unified_* mais recente
        # -> escreve snapshots/scan-YYYY-MM-DD-HHMM.md
    python scripts/snapshot.py --scan-dir results/unified_20260615_154401
        # -> aponta um diretório de scan específico
    python scripts/snapshot.py --all
        # -> agrega TODAS as runs em results/ (modo legado por-bucket)
"""
from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT_DIR = ROOT / "snapshots"
REGISTRY = ROOT / "sku_registry.yaml"


def load_tcg_product_ids() -> dict[str, int]:
    if not REGISTRY.exists():
        return {}
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    out: dict[str, int] = {}
    for sku in data.get("skus", []) or []:
        sid = sku.get("id")
        pid = sku.get("tcgplayer_product_id")
        if sid and pid:
            out[sid] = pid
    return out


TCG_PRODUCT_IDS = load_tcg_product_ids()


def latest_unified_dir() -> Path | None:
    dirs = sorted(RESULTS.glob("unified_*"), key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs[0] if dirs else None


def _bucket_from_confidence(conf: str) -> str:
    """Mapeia a coluna `Confiança do deal` (GREEN/YELLOW/RED) do unified_deals.csv
    para o nome de bucket interno usado pelo resto do snapshot."""
    return {
        "GREEN": "real_opportunities",
        "YELLOW": "review_required",
        "RED": "rejected",
    }.get((conf or "").strip().upper(), "rejected")


def collect_rows_unified(scan_dir: Path) -> list[dict]:
    """Lê o unified_deals.csv (saída canônica de run_all_sources.py)."""
    p = scan_dir / "unified_deals.csv"
    if not p.exists():
        return []
    rows: list[dict] = []
    for r in csv.DictReader(open(p, encoding="utf-8")):
        r["_bucket"] = _bucket_from_confidence(r.get("Confiança do deal"))
        try:
            r["_total"] = float(r["Margem total %"]) if r.get("Margem total %") else None
        except ValueError:
            r["_total"] = None
        if r["_total"] is None:
            continue
        rows.append(r)
    rows.sort(key=lambda r: r["_total"], reverse=True)
    return rows


def collect_rows_legacy(latest_only: bool = False) -> list[dict]:
    """Modo legado: agrega os CSVs por bucket (real_opportunities.csv etc.)
    produzidos pelo `sealed_arbitrage_scanner.py` (1 fonte por vez)."""
    rows: list[dict] = []
    dirs = sorted(RESULTS.glob("*/"))
    if latest_only and dirs:
        dirs = [dirs[-1]]
    for d in dirs:
        for fn in ["real_opportunities.csv", "review_required.csv", "rejected.csv"]:
            p = d / fn
            if not p.exists():
                continue
            for r in csv.DictReader(open(p, encoding="utf-8")):
                r["_bucket"] = fn.replace(".csv", "")
                try:
                    r["_total"] = float(r["Margem total %"]) if r.get("Margem total %") else None
                except ValueError:
                    r["_total"] = None
                if r["_total"] is None:
                    continue
                rows.append(r)
    rows.sort(key=lambda r: r["_total"], reverse=True)
    return rows


def status_label(r: dict) -> str:
    b = r["_bucket"]
    if b == "real_opportunities":
        return "🟢 GREEN"
    if b == "review_required":
        return "🟡 YELLOW"
    if (r["_total"] or 0) >= 30:
        return "🟠 RED+"
    if (r["_total"] or 0) >= 0:
        return "🔴 RED"
    return "⚫ RED–"


def src(r: dict) -> str:
    aid = r.get("ID Anúncio", "")
    if aid.startswith("LIGA-"):
        return "Liga"
    if aid.startswith("OLX-"):
        return "OLX"
    if aid.startswith("AMZ-") or aid.startswith("AMAZON-"):
        return "Amazon"
    fonte = (r.get("Fonte") or "").strip()
    return fonte or "?"


def tcg_link(r: dict) -> str:
    sku = (r.get("SKU") or "").strip()
    pid = TCG_PRODUCT_IDS.get(sku)
    if pid:
        return f"https://www.tcgplayer.com/product/{pid}"
    return ""


def fmt_brl(v) -> str:
    if v in (None, "", "-"):
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"R$ {f:.2f}".replace(".", ",")


def fmt_pct(v) -> str:
    if v in (None, "", "-"):
        return "-"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{f:.1f}%".replace(".", ",")


def fmt_qty(v) -> str:
    """Qtd disponível (estoque do vendedor). '?' quando o adapter não parseou."""
    if v in (None, "", "-"):
        return "?"
    try:
        return str(int(float(v)))
    except (TypeError, ValueError):
        return str(v)


def is_suspect(r: dict) -> bool:
    """True quando o deal precisa de conferência manual antes de comprar:
    match ambíguo (YELLOW) ou risco sinalizado (margem anômala / variante
    trocada). O scanner não casa por engano — mas marca pra revisão."""
    if r["_bucket"] == "review_required":
        return True
    risco = (r.get("Risco principal") or "").lower()
    return any(t in risco for t in ("anômal", "anomal", "trocad", "variante", "verifique", "confirm"))


def delta_unit(tcg_brl, liga_brl) -> str:
    try:
        return fmt_brl(float(tcg_brl) - float(liga_brl))
    except (TypeError, ValueError):
        return "-"


def md_link(label: str, url: str) -> str:
    if not url:
        return label
    if any(c in url for c in " ()<>"):
        return f"[{label}](<{url}>)"
    return f"[{label}]({url})"


def links_cell(r: dict) -> str:
    """Coluna `Links` combinada (modelo de tabela do MYP, padrão cross-scanner —
    operador 2026-06-19): `[oferta](url_BR) · [TCG](url_tcg)` numa célula só.
    `oferta` = anúncio BR (Liga/OLX/Amazon/ML); `TCG` = página TCGplayer de
    referência. Só inclui o que existir; sem nenhum, vira '—'."""
    parts = []
    liga_url = (r.get("URL") or "").strip()
    tcg_url = tcg_link(r)
    if liga_url:
        parts.append(md_link("oferta", liga_url))
    if tcg_url:
        parts.append(md_link("TCG", tcg_url))
    return " · ".join(parts) if parts else "—"


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera a tabela de ENTREGA (Markdown) do scan de selados.")
    ap.add_argument(
        "--scan-dir",
        help="Diretório de uma run específica (ex.: results/unified_20260615_154401). "
             "Default: o results/unified_* mais recente.",
    )
    ap.add_argument(
        "--all",
        action="store_true",
        help="Modo legado: agrega TODAS as runs por bucket (real_opportunities.csv etc.).",
    )
    ap.add_argument(
        "--latest",
        action="store_true",
        help="(legado, com --all) só a run mais recente por bucket.",
    )
    args = ap.parse_args()

    legacy = False
    if args.all:
        rows = collect_rows_legacy(latest_only=args.latest)
        legacy = True
        scope = "última run (legado)" if args.latest else "todas as runs em `results/` (legado)"
    else:
        scan_dir = Path(args.scan_dir) if args.scan_dir else latest_unified_dir()
        if scan_dir is None:
            # Sem unified_* — cai pro legado por-bucket pra não falhar silenciosamente.
            rows = collect_rows_legacy(latest_only=True)
            legacy = True
            scope = "última run (legado — sem unified_deals.csv)"
        else:
            rows = collect_rows_unified(scan_dir)
            scope = f"`{scan_dir.name}`"
            if not rows:
                raise SystemExit(
                    f"ERRO: {scan_dir / 'unified_deals.csv'} não tem linhas válidas. "
                    "Rode `python run_all_sources.py` primeiro."
                )

    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    out = OUT_DIR / f"scan-{stamp}.md"

    n_green = sum(1 for r in rows if r["_bucket"] == "real_opportunities")
    n_yellow = sum(1 for r in rows if r["_bucket"] == "review_required")
    n_red = sum(1 for r in rows if r["_bucket"] == "rejected")

    lines: list[str] = []
    lines.append("---")
    lines.append("tags:")
    lines.append("  - tcg")
    lines.append("  - arbitragem")
    lines.append("  - pokemon")
    lines.append("  - selado")
    lines.append("  - scan")
    lines.append(f"date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    lines.append(f"hora: {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    lines.append(f"green: {n_green}")
    lines.append(f"yellow: {n_yellow}")
    lines.append(f"red: {n_red}")
    lines.append("---")
    lines.append("")
    lines.append(f"# Scan TCG Sealed — {stamp}")
    lines.append("")
    sources_seen = sorted({src(r) for r in rows})
    lines.append(
        f"**Fontes BR**: {' + '.join(sources_seen) if sources_seen else '—'} · "
        f"**Referência US**: TCGPlayer Market via tcgcsv.com · **Escopo**: {scope}"
    )
    lines.append("")
    lines.append(
        f"**Buckets**: 🟢 GREEN = {n_green} · 🟡 YELLOW = {n_yellow} · "
        f"🔴 RED = {n_red} · **Total matches** = {len(rows)}"
    )
    lines.append("")

    # ── Tabela de ENTREGA: GREEN + YELLOW (os acionáveis), TODOS, sem curar ──
    actionable = [r for r in rows if r["_bucket"] in ("real_opportunities", "review_required")]
    lines.append("## 🟢🟡 Deals acionáveis (GREEN + YELLOW)")
    lines.append("")
    if not actionable:
        lines.append("> Nenhum deal GREEN/YELLOW neste scan.")
    else:
        lines.append(
            "| # | Status | Produto (EN) | Tipo | Qtd disp. | "
            "TCG (R$) | BR (R$) | Margem bruta % | Δ R$/unid | ⚠️ | Links |"
        )
        lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---|---|")
        for i, r in enumerate(actionable, start=1):
            prod = r.get("Produto (canônico)") or "(ambíguo)"
            tipo = (r.get("Tipo") or "").strip() or "—"
            liga_brl = r.get("Preço BR (R$)") or ""
            tcg_brl = r.get("Preço US (R$)") or ""
            tcg_cell = fmt_brl(tcg_brl) if tcg_brl else "-"
            liga_cell = fmt_brl(liga_brl) if liga_brl else "-"
            flag = "⚠️" if is_suspect(r) else ""
            lines.append(
                f"| {i} | {status_label(r)} | {prod[:60]} | {tipo} | "
                f"{fmt_qty(r.get('Qtd disponível'))} | {tcg_cell} | {liga_cell} | "
                f"{fmt_pct(r.get('Margem total %'))} | {delta_unit(tcg_brl, liga_brl)} | {flag} | {links_cell(r)} |"
            )
        # Notas de suspeita por linha (motivo da flag ⚠️).
        suspects = [(i, r) for i, r in enumerate(actionable, start=1) if is_suspect(r)]
        if suspects:
            lines.append("")
            lines.append("**⚠️ Conferir manualmente antes de comprar:**")
            lines.append("")
            for i, r in suspects:
                risco = (r.get("Risco principal") or "").strip() or "match ambíguo (1 anúncio casa com 2+ SKUs)"
                lines.append(f"- **#{i}** {r.get('Produto (canônico)') or '(ambíguo)'}: {risco}")
    lines.append("")

    # ── Ranking completo (todas as linhas, incl. RED) — referência ──
    lines.append("## Ranking completo (do mais vantajoso pro menos)")
    lines.append("")
    lines.append(
        "| # | Status | Produto (EN) | Qtd disp. | TCG (R$) | BR (R$) | Margem bruta % | Δ R$/unid | Links |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---|")
    for i, r in enumerate(rows, start=1):
        prod = r.get("Produto (canônico)") or "(ambíguo)"
        liga_brl = r.get("Preço BR (R$)") or ""
        tcg_brl = r.get("Preço US (R$)") or ""
        tcg_cell = fmt_brl(tcg_brl) if tcg_brl else "-"
        liga_cell = fmt_brl(liga_brl) if liga_brl else "-"
        lines.append(
            f"| {i} | {status_label(r)} | {prod[:60]} | "
            f"{fmt_qty(r.get('Qtd disponível'))} | {tcg_cell} | {liga_cell} | "
            f"{fmt_pct(r.get('Margem total %'))} | {delta_unit(tcg_brl, liga_brl)} | {links_cell(r)} |"
        )

    lines.append("")
    lines.append("## Notas")
    lines.append("")
    lines.append("- **Qtd disp.** = estoque do vendedor pra esse anúncio (importamos em LOTE, nunca 1 unidade). `?` quando o adapter da fonte não parseou o estoque.")
    lines.append("- **TCG (R$)** = TCGPlayer Market price (US$) convertido pra R$ pelo câmbio do scan.")
    lines.append("- **BR (R$)** = preço atual do anúncio (Liga/OLX/Amazon/ML) em R$.")
    lines.append("- **Links** = `[oferta](anúncio BR) · [TCG](página TCGplayer)` numa coluna só (modelo MYP, padrão cross-scanner). Clique em **oferta** pra validar preço + estoque no anúncio, e em **TCG** pra conferir a referência no TCGplayer.")
    lines.append("- **Margem bruta %** = (TCG − BR) / BR × 100 — só preço vs preço, SEM taxas/frete. Custos operacionais ficam fora do scanner (o operador calcula por fora).")
    lines.append("- **Δ R$/unid** = TCG R$ − BR R$, em reais por unidade do produto.")
    lines.append("- **⚠️** = deal que precisa de conferência manual (match ambíguo YELLOW ou margem/variante suspeita) — o motivo está listado acima da tabela.")
    lines.append("- **GREEN** = margem bruta ≥ 30% · **YELLOW** = match ambíguo (1 anúncio casa com 2+ SKUs) · **RED** = < 30%, sem match, sem referência US ou preço inválido/baixo.")
    lines.append("- Sem recomendação de compra — o operador decide capital.")
    lines.append("")
    lines.append(f"Gerado em {datetime.now(timezone.utc).isoformat(timespec='seconds')} via `scripts/snapshot.py`")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Snapshot escrito em {out}")
    print(f"  {n_green} GREEN, {n_yellow} YELLOW, {n_red} RED, {len(rows)} total"
          + (" (modo legado por-bucket)" if legacy else ""))


if __name__ == "__main__":
    main()
