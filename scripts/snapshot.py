#!/usr/bin/env python3
"""
snapshot.py — gera uma nota Markdown ranqueada com todos os matches das
runs do scanner (Liga / OLX / Amazon), pronta pra ler no Obsidian.

Uso:
    python sealed/scripts/snapshot.py
        # -> agrega TODAS as runs em sealed/results/
        # -> escreve sealed/snapshots/scan-YYYY-MM-DD-HHMM.md
    python sealed/scripts/snapshot.py --latest
        # -> apenas a run mais recente
        # -> escreve sealed/snapshots/scan-YYYY-MM-DD-HHMM-latest.md
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


def collect_rows(latest_only: bool = False) -> list[dict]:
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
                r["_total"] = float(r["Margem total %"]) if r["Margem total %"] else None
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
    if r["_total"] >= 30:
        return "🟠 RED+"
    if r["_total"] >= 0:
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Gera snapshot Markdown das runs do scanner.")
    ap.add_argument(
        "--latest",
        action="store_true",
        help="Considera apenas a run mais recente em sealed/results/ (default: agrega todas).",
    )
    args = ap.parse_args()

    rows = collect_rows(latest_only=args.latest)
    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    suffix = "-latest" if args.latest else ""
    out = OUT_DIR / f"scan-{stamp}{suffix}.md"

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
    title_suffix = " (última run)" if args.latest else " (agregado)"
    lines.append(f"# Scan TCG Sealed — {stamp}{title_suffix}")
    lines.append("")
    sources_seen = sorted({src(r) for r in rows})
    scope = "última run" if args.latest else f"todas as runs em `sealed/results/`"
    lines.append(f"**Fontes BR**: {' + '.join(sources_seen) if sources_seen else '—'} · **Referência US**: TCGPlayer Market via tcgcsv.com · **Escopo**: {scope}")
    lines.append("")
    lines.append(f"**Buckets**: 🟢 GREEN = {n_green} · 🟡 YELLOW = {n_yellow} · 🔴 RED = {n_red} · **Total matches** = {len(rows)}")
    lines.append("")
    lines.append("## Ranking completo (do mais vantajoso pro menos)")
    lines.append("")
    lines.append("| # | Status | Produto (EN) | TCG (R$, média) | Liga (R$) | Margem % | Δ R$/unid |")
    lines.append("|---|---|---|---:|---:|---:|---:|")
    for i, r in enumerate(rows, start=1):
        prod = r.get("Produto (canônico)") or "(ambíguo)"
        liga_brl = r.get("Preço BR (R$)") or ""
        tcg_brl = r.get("Preço US (R$)") or ""
        liga_url = r.get("URL") or ""
        tcg_url = tcg_link(r)

        tcg_cell = md_link(fmt_brl(tcg_brl), tcg_url) if tcg_brl else "-"
        liga_cell = md_link(fmt_brl(liga_brl), liga_url) if liga_brl else "-"

        lines.append(
            f"| {i} | {status_label(r)} | {prod[:60]} | "
            f"{tcg_cell} | {liga_cell} | "
            f"{fmt_pct(r.get('Margem total %'))} | "
            f"{delta_unit(tcg_brl, liga_brl)} |"
        )

    lines.append("")
    lines.append("## Notas")
    lines.append("")
    lines.append("- **TCG (R$, média)** = TCGPlayer Market price (US$) convertido pra R$ pelo câmbio do scan; clique pra abrir a página canônica do produto pra conferência.")
    lines.append("- **Liga (R$)** = preço atual do anúncio na Liga Pokémon (em R$); clique pra abrir o anúncio.")
    lines.append("- **Margem %** = (TCG − Liga) / Liga × 100 — markup bruto, ANTES de taxas e frete.")
    lines.append("- **Δ R$/unid** = TCG R$ − Liga R$, em reais por unidade do produto (diferença BRUTA de preço).")
    lines.append("- **GREEN** = margem total ≥ 40% · **YELLOW** = 30-40% ou match ambíguo · **RED** = < 30%.")
    lines.append("- **Sources blocked daqui**: Mercado Livre (anti-bot/auth). Liga = OK via patchright headful (`--janela`).")
    lines.append("")
    lines.append(f"Gerado em {datetime.now(timezone.utc).isoformat(timespec='seconds')}")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Snapshot escrito em {out}")
    print(f"  {n_green} GREEN, {n_yellow} YELLOW, {n_red} RED, {len(rows)} total")


if __name__ == "__main__":
    main()
