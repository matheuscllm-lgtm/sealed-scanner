#!/usr/bin/env python3
"""
snapshot.py — gera a TABELA DE ENTREGA em Markdown a partir do scan.

⭐ ESTE É O GERADOR CANÔNICO E OBRIGATÓRIO DA ENTREGA (ver README invariante #7).
Quando for entregar o resultado de um scan ao operador, há **um caminho só**:
rode este script sobre o `unified_deals.csv` da run e cole/mostre o markdown
que ele gerou — NUNCA monte a tabela à mão. O formato (colunas, ordem, links,
quantidades, flags de suspeita) é a única fonte de verdade do layout.

⭐ MODELO DE ENTREGA (2026-06-20, padrão MYP cross-scanner — operador):
A entrega é **AGRUPADA POR PRODUTO** (SKU canônico), não uma lista plana de
anúncios. Cada produto traz, no estilo da tabela do MYP:
  - Status (🟢 GREEN / 🟡 YELLOW / 🔴 RED),
  - Produto canônico (nome) + Tipo,
  - **Ref. Nacional (R$)** = menor preço BR disponível agora (melhor entrada),
  - **Ref. TCG (R$)** = preço de referência TCGplayer Market (US$→R$),
  - Margem bruta % + Δ R$/unid (calculados na Ref. Nacional vs Ref. TCG),
  - **Qtd total disp.** (soma do estoque de todas as ofertas) + **Nº ofertas**,
  - coluna `Links` combinada `[oferta](url_BR) · [TCG](url_tcg)`.
E, logo abaixo de cada produto acionável, o **detalhamento das quantidades e
preços disponíveis de cada unidade** (escada de ofertas): por anúncio, o
vendedor, a fonte, a quantidade disponível e o preço BR — porque o operador
importa em LOTE e quer ver cada unidade disponível e seu preço.

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
from statistics import median

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


def _bucket_label(bucket: str, margin: float | None) -> str:
    if bucket == "real_opportunities":
        return "🟢 GREEN"
    if bucket == "review_required":
        return "🟡 YELLOW"
    if (margin or 0) >= 30:
        return "🟠 RED+"
    if (margin or 0) >= 0:
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


def _to_float(v):
    if v in (None, "", "-", "?"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


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


# ──────────────────────────────────────────────────────────────────────────
# Agrupamento por produto (SKU canônico) — modelo de entrega 2026-06-20
# ──────────────────────────────────────────────────────────────────────────
def _group_key(r: dict) -> str:
    """Chave de agrupamento: SKU canônico. Anúncios sem SKU (ambíguos / sem
    match) caem num pseudo-grupo por título pra não serem perdidos."""
    sku = (r.get("SKU") or "").strip()
    if sku:
        return f"sku::{sku}"
    prod = (r.get("Produto (canônico)") or "").strip()
    if prod:
        return f"prod::{prod}"
    return f"titulo::{(r.get('Título (BR)') or '?').strip()}"


_BUCKET_RANK = {"real_opportunities": 0, "review_required": 1, "rejected": 2}


def group_products(rows: list[dict]) -> list[dict]:
    """Agrupa anúncios pelo produto canônico e consolida, por grupo:

      - melhor bucket (GREEN > YELLOW > RED),
      - **referência nacional** = menor preço BR disponível agora (melhor entrada),
      - mediana BR (contexto do mercado nacional),
      - **referência TCG** (US$ e R$) — única por SKU,
      - margem na referência nacional + Δ R$/unid,
      - quantidade total disponível (soma) e nº de ofertas,
      - a oferta "líder" (mais barata) p/ o link da coluna Links,
      - a escada de ofertas (todas as unidades disponíveis, BR asc).

    Retorna a lista ordenada pela melhor margem desc.
    """
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(_group_key(r), []).append(r)

    out: list[dict] = []
    for key, listings in groups.items():
        # escada de unidades disponíveis: BR asc (mais barata primeiro)
        ladder = sorted(
            listings,
            key=lambda x: (_to_float(x.get("Preço BR (R$)")) is None, _to_float(x.get("Preço BR (R$)")) or 0.0),
        )

        # Oferta de REFERÊNCIA = a mais barata que é um deal AUTO-CONSISTENTE
        # (tem preço BR **E** referência TCG na MESMA linha). Todo o cabeçalho do
        # produto — preço nacional, margem, Δ, status e link — sai DESSA única
        # oferta. Nunca cruzamos campos de anúncios diferentes: senão a linha
        # mostraria uma margem (ex.: BR de um anúncio × TCG de outro) que não
        # existe em nenhuma oferta real e o link levaria a um preço diferente do
        # exibido. Fallback: a mais barata, se nenhuma tiver referência TCG.
        #
        # ⭐ Dentre as válidas, prefira o MELHOR bucket (GREEN > YELLOW > RED) antes
        # de "a mais barata". Senão uma oferta RED barata anômala (ex.: acessório
        # mal-casado a R$64 com margem 1600% que o scanner já marcou margem_anomala,
        # ou um anúncio abaixo do preço mínimo) viraria a referência, herdaria o
        # bucket RED pro grupo INTEIRO e ESCONDERIA ofertas GREEN legítimas do mesmo
        # produto da entrega. A oferta mais barata sempre tem a MAIOR margem, então
        # uma RED-mais-barata só acontece por motivo NÃO-margem (anômala / abaixo do
        # mínimo / sem ref) — exatamente os casos a pular como referência. `valid`
        # herda a ordem BR-asc do `ladder`, então o primeiro do melhor bucket é a
        # entrada mais barata daquele bucket (auto-consistência preservada).
        valid = [
            x for x in ladder
            if _to_float(x.get("Preço BR (R$)")) is not None
            and _to_float(x.get("Preço US (R$)")) is not None
        ]
        if valid:
            best_rank = min(_BUCKET_RANK.get(x.get("_bucket"), 9) for x in valid)
            ref = next(x for x in valid if _BUCKET_RANK.get(x.get("_bucket"), 9) == best_rank)
        else:
            ref = ladder[0] if ladder else listings[0]

        br_prices = [p for p in (_to_float(x.get("Preço BR (R$)")) for x in listings) if p is not None]
        qtys = [q for q in (_to_float(x.get("Qtd disponível")) for x in listings) if q is not None]
        qtd_partial = len(qtys) < len(listings)

        br_ref = _to_float(ref.get("Preço BR (R$)"))
        tcg_brl = _to_float(ref.get("Preço US (R$)"))
        if br_ref and tcg_brl:
            margem = (tcg_brl - br_ref) / br_ref * 100.0
            delta = tcg_brl - br_ref
        else:
            margem = ref.get("_total")
            delta = None

        out.append(
            {
                "key": key,
                "produto": ref.get("Produto (canônico)") or "(ambíguo)",
                "tipo": (ref.get("Tipo") or "").strip() or "—",
                "colecao": (ref.get("Coleção") or "").strip() or "—",
                "sku": (ref.get("SKU") or "").strip(),
                "bucket": ref.get("_bucket", "rejected"),
                "br_ref": br_ref,            # referência nacional (oferta válida mais barata)
                "br_max": max(br_prices) if br_prices else None,
                "br_median": median(br_prices) if br_prices else None,
                "tcg_usd": _to_float(ref.get("Preço US (US$)")),
                "tcg_brl": tcg_brl,          # referência TCGplayer (R$)
                "margem": margem,
                "delta": delta,
                "qtd_total": int(sum(qtys)) if qtys else None,
                "qtd_partial": qtd_partial,  # algum anúncio sem estoque parseado
                "n_ofertas": len(listings),
                "ref": ref,
                "leader": ref,               # alias retrocompat (== ref)
                "ladder": ladder,
                "suspect": any(is_suspect(x) for x in listings),
            }
        )

    out.sort(key=lambda g: (g["margem"] if g["margem"] is not None else -1e9), reverse=True)
    return out


def group_status_label(g: dict) -> str:
    return _bucket_label(g["bucket"], g["margem"])


def fmt_qtd_total(g: dict) -> str:
    """Qtd total do produto. `N+?` quando algum anúncio não teve estoque parseado
    (a soma é um piso, não um total exato); `?` quando nenhum teve."""
    t = g.get("qtd_total")
    if t is None:
        return "?"
    return f"{t}+?" if g.get("qtd_partial") else str(t)


def group_links_cell(g: dict) -> str:
    """Links combinados do grupo: oferta da unidade de REFERÊNCIA (a mais barata
    com referência TCG — a mesma que dá o preço/margem do cabeçalho) + TCG."""
    return links_cell(g["ref"])


def group_risco(g: dict) -> str:
    for x in g["ladder"]:
        risco = (x.get("Risco principal") or "").strip()
        if risco and is_suspect(x):
            return risco
    return "match ambíguo (1 anúncio casa com 2+ SKUs)"


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

    groups = group_products(rows)

    # Contagens por anúncio (referência) e por produto (entrega).
    n_green = sum(1 for r in rows if r["_bucket"] == "real_opportunities")
    n_yellow = sum(1 for r in rows if r["_bucket"] == "review_required")
    n_red = sum(1 for r in rows if r["_bucket"] == "rejected")
    g_green = sum(1 for g in groups if g["bucket"] == "real_opportunities")
    g_yellow = sum(1 for g in groups if g["bucket"] == "review_required")
    g_red = sum(1 for g in groups if g["bucket"] == "rejected")

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
    lines.append(f"green: {g_green}")
    lines.append(f"yellow: {g_yellow}")
    lines.append(f"red: {g_red}")
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
        f"**Produtos**: 🟢 GREEN = {g_green} · 🟡 YELLOW = {g_yellow} · "
        f"🔴 RED = {g_red} · **Total produtos** = {len(groups)} "
        f"_(consolidados de {len(rows)} anúncios: {n_green} GREEN / {n_yellow} YELLOW / {n_red} RED)_"
    )
    lines.append("")

    # ── Entrega AGRUPADA POR PRODUTO: GREEN + YELLOW (acionáveis) ──
    actionable = [g for g in groups if g["bucket"] in ("real_opportunities", "review_required")]
    lines.append("## 🟢🟡 Produtos acionáveis (GREEN + YELLOW)")
    lines.append("")
    if not actionable:
        lines.append("> Nenhum produto GREEN/YELLOW neste scan.")
    else:
        lines.append(
            "| # | Status | Produto (EN) | Tipo | Ref. Nacional (R$) | Ref. TCG (R$) | "
            "Margem bruta % | Δ R$/unid | Qtd total | Ofertas | ⚠️ | Links |"
        )
        lines.append("|---|---|---|---|---:|---:|---:|---:|---:|---:|---|---|")
        for i, g in enumerate(actionable, start=1):
            flag = "⚠️" if g["suspect"] else ""
            lines.append(
                f"| {i} | {group_status_label(g)} | {g['produto'][:60]} | {g['tipo']} | "
                f"{fmt_brl(g['br_ref'])} | {fmt_brl(g['tcg_brl'])} | {fmt_pct(g['margem'])} | "
                f"{fmt_brl(g['delta'])} | {fmt_qtd_total(g)} | "
                f"{g['n_ofertas']} | {flag} | {group_links_cell(g)} |"
            )

        # ── Detalhamento: quantidades e preços disponíveis de CADA unidade ──
        lines.append("")
        lines.append("### Quantidades e preços disponíveis por unidade")
        lines.append("")
        lines.append(
            "Cada produto acionável e a escada de ofertas (cada anúncio = uma unidade "
            "disponível, com vendedor, estoque e preço BR). Importamos em LOTE."
        )
        lines.append("")
        for i, g in enumerate(actionable, start=1):
            ref_tcg = fmt_brl(g["tcg_brl"])
            med = fmt_brl(g["br_median"])
            lines.append(
                f"**#{i} — {g['produto']}** · {g['tipo']} · Coleção: {g['colecao']} · "
                f"Ref. TCG {ref_tcg} · Ref. Nacional (menor) {fmt_brl(g['br_ref'])} · "
                f"mediana BR {med} · {g['n_ofertas']} oferta(s) · Qtd total "
                f"{fmt_qtd_total(g)}"
            )
            lines.append("")
            lines.append("| Vendedor | Fonte | Qtd disp. | Preço BR (R$) | Margem bruta % | Oferta |")
            lines.append("|---|---|---:|---:|---:|---|")
            for x in g["ladder"]:
                vendedor = (x.get("Vendedor") or "—").strip() or "—"
                oferta_url = (x.get("URL") or "").strip()
                oferta = md_link("oferta", oferta_url) if oferta_url else "—"
                lines.append(
                    f"| {vendedor} | {src(x)} | {fmt_qty(x.get('Qtd disponível'))} | "
                    f"{fmt_brl(x.get('Preço BR (R$)'))} | {fmt_pct(x.get('Margem total %'))} | {oferta} |"
                )
            lines.append("")

        # Notas de suspeita por produto (motivo da flag ⚠️).
        suspects = [(i, g) for i, g in enumerate(actionable, start=1) if g["suspect"]]
        if suspects:
            lines.append("**⚠️ Conferir manualmente antes de comprar:**")
            lines.append("")
            for i, g in suspects:
                lines.append(f"- **#{i}** {g['produto']}: {group_risco(g)}")
            lines.append("")

    # ── Ranking completo por produto (todos, incl. RED) — referência ──
    lines.append("## Ranking completo por produto (do mais vantajoso pro menos)")
    lines.append("")
    lines.append(
        "| # | Status | Produto (EN) | Ref. Nacional (R$) | Ref. TCG (R$) | "
        "Margem bruta % | Δ R$/unid | Qtd total | Ofertas | Links |"
    )
    lines.append("|---|---|---|---:|---:|---:|---:|---:|---:|---|")
    for i, g in enumerate(groups, start=1):
        lines.append(
            f"| {i} | {group_status_label(g)} | {g['produto'][:60]} | "
            f"{fmt_brl(g['br_ref'])} | {fmt_brl(g['tcg_brl'])} | {fmt_pct(g['margem'])} | "
            f"{fmt_brl(g['delta'])} | {fmt_qtd_total(g)} | "
            f"{g['n_ofertas']} | {group_links_cell(g)} |"
        )

    lines.append("")
    lines.append("## Notas")
    lines.append("")
    lines.append("- A entrega é **agrupada por produto** (SKU canônico): cada linha consolida todas as ofertas BR do mesmo produto. O nº entre parênteses no topo mostra quantos anúncios brutos viraram quantos produtos.")
    lines.append("- **Ref. Nacional (R$)** = preço da oferta de REFERÊNCIA = a unidade mais barata que tem referência TCG (a mesma oferta que dá a margem e o link da linha — nunca cruzamos preço de um anúncio com referência de outro). A `mediana BR` no detalhamento dá o contexto de mercado nacional; a escada mostra unidades ainda mais baratas que eventualmente estejam sem referência.")
    lines.append("- **Ref. TCG (R$)** = TCGPlayer Market price (US$) convertido pra R$ pelo câmbio do scan — a referência internacional de revenda.")
    lines.append("- **Qtd total** = soma do estoque de TODAS as ofertas do produto (importamos em LOTE). **Ofertas** = nº de anúncios. `N+?` quando algum anúncio não teve estoque parseado (a soma é um piso); `?` quando nenhum teve.")
    lines.append("- O bloco **Quantidades e preços disponíveis por unidade** lista, por produto, CADA anúncio (vendedor, fonte, qtd e preço BR) — a escada de unidades disponíveis, da mais barata pra mais cara.")
    lines.append("- **Links** = `[oferta](anúncio BR mais barato) · [TCG](página TCGplayer)` numa coluna só (modelo MYP). A oferta linkada é a unidade de menor preço; as demais estão no detalhamento.")
    lines.append("- **Margem bruta %** = (Ref. TCG − Ref. Nacional) / Ref. Nacional × 100 — só preço vs preço, SEM taxas/frete. Custos operacionais ficam fora do scanner (o operador calcula por fora).")
    lines.append("- **Δ R$/unid** = Ref. TCG R$ − Ref. Nacional R$, em reais por unidade do produto.")
    lines.append("- **⚠️** = produto com alguma oferta que precisa de conferência manual (match ambíguo YELLOW ou margem/variante suspeita) — o motivo está listado acima.")
    lines.append("- **GREEN** = margem bruta ≥ 30% · **YELLOW** = match ambíguo (1 anúncio casa com 2+ SKUs) · **RED** = < 30%, sem match, sem referência US ou preço inválido. (Selado NÃO tem piso de preço — o piso R$50 vale só para cartas avulsas.)")
    lines.append("- Sem recomendação de compra — o operador decide capital.")
    lines.append("")
    lines.append(f"Gerado em {datetime.now(timezone.utc).isoformat(timespec='seconds')} via `scripts/snapshot.py`")

    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Snapshot escrito em {out}")
    print(
        f"  {g_green} GREEN, {g_yellow} YELLOW, {g_red} RED produtos "
        f"(de {len(rows)} anúncios)"
        + (" (modo legado por-bucket)" if legacy else "")
    )


if __name__ == "__main__":
    main()
