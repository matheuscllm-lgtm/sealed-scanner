#!/usr/bin/env python3
"""
snapshot_friendly.py — versão DIDÁTICA do snapshot.

Gera uma nota Markdown legível pra humano não-técnico. Agrupa por
produto (não por anúncio), destaca o melhor vendedor de cada SKU,
explica o que cada coluna significa.

Saída ao lado do snapshot técnico:
    sealed/snapshots/scan-YYYY-MM-DD-HHMM-friendly.md

Uso:
    python sealed/scripts/snapshot_friendly.py
    # ou junto com o técnico:
    python sealed/scripts/snapshot.py && python sealed/scripts/snapshot_friendly.py
"""
from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT_DIR = ROOT / "snapshots"


def _f(s: str | None) -> float | None:
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def collect_rows() -> list[dict]:
    """Lê todos os CSVs de todas as runs e devolve uma lista única."""
    rows: list[dict] = []
    for d in sorted(RESULTS.glob("*/")):
        for fn in ["real_opportunities.csv", "review_required.csv", "rejected.csv"]:
            p = d / fn
            if not p.exists():
                continue
            for r in csv.DictReader(open(p, encoding="utf-8")):
                r["_bucket"] = fn.replace(".csv", "")
                r["_total"] = _f(r.get("Margem total %"))
                r["_net"] = _f(r.get("Margem líquida est. %"))
                r["_net_brl"] = _f(r.get("Lucro líquido est. (R$)"))
                r["_price"] = _f(r.get("Preço BR (R$)"))
                r["_us_brl"] = _f(r.get("Preço US (R$)"))
                if r["_price"] is None:
                    continue
                rows.append(r)
    return rows


def _src(r: dict) -> str:
    lid = r.get("ID Anúncio", "")
    if lid.startswith("LIGA-"):
        return "Liga Pokémon"
    if lid.startswith("OLX-"):
        return "OLX"
    if lid.startswith("AMZ-"):
        return "Amazon BR"
    return r.get("Fonte", "?")


def group_by_product(rows: list[dict]) -> dict[str, list[dict]]:
    """Agrupa por produto canônico + tipo (mesmo SKU virtual)."""
    grp: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        prod = r.get("Produto (canônico)") or r.get("Título (BR)") or "(ambíguo)"
        tipo = r.get("Tipo") or ""
        key = f"{prod} | {tipo}" if tipo else prod
        grp[key].append(r)
    # Ordena cada grupo pelo melhor (líquido decrescente, depois preço)
    for k in grp:
        grp[k].sort(key=lambda r: (-(r["_net_brl"] or -9e9), r["_price"] or 9e9))
    return grp


def render_product_block(produto: str, ofertas: list[dict], rank: int) -> list[str]:
    """Bloco didático pra um SKU agrupado.

    Mostra só ofertas com lucro líquido positivo (as caras do mesmo SKU que
    dão prejuízo poluem a tabela). Se nenhuma for positiva, mostra a melhor.
    """
    best = ofertas[0]
    positivas = [o for o in ofertas if (o["_net_brl"] or -1) > 0]
    perdedoras = len(ofertas) - len(positivas)
    mostrar = positivas[:5] if positivas else ofertas[:1]

    out: list[str] = []
    out.append(f"### {rank}. {produto}")
    out.append("")
    out.append(f"- **{len(ofertas)} vendedor(es)** vendendo esse produto")
    out.append(f"- **{len(positivas)} oferta(s) com lucro real** (resto: preço alto demais)")
    if best["_us_brl"]:
        usd = _f(best.get("Preço US (US$)")) or 0
        out.append(f"- **Vale nos EUA**: R$ {best['_us_brl']:.2f} (= US$ {usd:.2f})")
    out.append("")
    out.append(f"**{'Top ' + str(len(mostrar)) + ' ofertas vencedoras' if positivas else 'Menos pior oferta'}:**")
    out.append("")
    out.append("| Onde comprar | Preço Brasil | Lucro líquido/unid | ROI líquido | Link |")
    out.append("|---|---:|---:|---:|---|")
    # CSV armazena margens já em percentual (ex.: 9.12 = 9,12%) — não multiplicar.
    for o in mostrar:
        roi = f"{o['_net']:.1f}%" if o["_net"] is not None else "-"
        net = f"R$ {o['_net_brl']:.2f}" if o["_net_brl"] is not None else "-"
        price = f"R$ {o['_price']:.2f}" if o["_price"] is not None else "-"
        seller = o.get("Vendedor", "") or "—"
        out.append(f"| {_src(o)} ({seller}) | {price} | {net} | {roi} | [abrir]({o.get('URL', '')}) |")
    if perdedoras:
        out.append("")
        out.append(f"_+{perdedoras} outro(s) vendedor(es) desse mesmo produto com preço alto demais — ignorados._")
    risco = best.get("Risco principal", "")
    acao = best.get("Ação recomendada", "")
    if risco:
        out.append("")
        out.append(f"> 🛈 {risco}")
    if acao:
        out.append(f"> 🎯 **Ação**: {acao}")
    out.append("")
    return out


def main() -> None:
    rows = collect_rows()
    if not rows:
        print("Nenhum resultado encontrado em sealed/results/. Rode um scan primeiro.")
        return
    OUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")
    out = OUT_DIR / f"scan-{stamp}-friendly.md"

    grouped = group_by_product(rows)
    greens: list[tuple[str, list[dict]]] = []
    yellows: list[tuple[str, list[dict]]] = []
    reds: list[tuple[str, list[dict]]] = []
    for prod, ofertas in grouped.items():
        best = ofertas[0]
        if best["_bucket"] == "real_opportunities":
            greens.append((prod, ofertas))
        elif best["_bucket"] == "review_required":
            yellows.append((prod, ofertas))
        else:
            reds.append((prod, ofertas))
    greens.sort(key=lambda kv: -(kv[1][0]["_net_brl"] or -9e9))
    yellows.sort(key=lambda kv: -(kv[1][0]["_net_brl"] or -9e9))
    reds.sort(key=lambda kv: len(kv[1]), reverse=True)

    n_green_listings = sum(1 for r in rows if r["_bucket"] == "real_opportunities")
    n_yellow_listings = sum(1 for r in rows if r["_bucket"] == "review_required")
    n_red_listings = sum(1 for r in rows if r["_bucket"] == "rejected")

    L: list[str] = []
    L.append("---")
    L.append("tags: [tcg, arbitragem, pokemon, selado, scan, didatico]")
    L.append(f"date: {datetime.now(timezone.utc).strftime('%Y-%m-%d')}")
    L.append(f"hora: {datetime.now(timezone.utc).strftime('%H:%M UTC')}")
    L.append("---")
    L.append("")
    L.append(f"# 🛒 O que comprar — scan {stamp}")
    L.append("")
    L.append("## Resumo executivo")
    L.append("")
    L.append(f"- ✅ **{len(greens)} produto(s) com oportunidade forte** ({n_green_listings} anúncio(s) GREEN)")
    L.append(f"- ⚠️ **{len(yellows)} produto(s) com cautela** ({n_yellow_listings} anúncio(s) YELLOW)")
    L.append(f"- ❌ {len(reds)} produto(s) ignorar ({n_red_listings} anúncio(s) RED)")
    L.append("")
    L.append("**Tradução simples**: GREEN = pode comprar com confiança; YELLOW = vale a pena, mas confira o alerta; RED = não dá lucro, ignora.")
    L.append("")

    # ----- GREENS -----
    L.append("---")
    L.append("")
    L.append("## ✅ Compre agora — produtos GREEN")
    L.append("")
    if not greens:
        L.append("_Nenhum produto verde neste scan._")
        L.append("")
    else:
        L.append("Em ordem de **lucro líquido por unidade** (do mais lucrativo pro menos).")
        L.append("")
        for i, (prod, ofertas) in enumerate(greens, start=1):
            L += render_product_block(prod, ofertas, i)

    # ----- YELLOWS -----
    L.append("---")
    L.append("")
    L.append("## ⚠️ Olha com cautela — produtos YELLOW")
    L.append("")
    if not yellows:
        L.append("_Nenhum produto amarelo neste scan._")
        L.append("")
    else:
        L.append("Margem boa **no papel**, mas o alerta de cada um diz por que precisa revisão. Ofertas em ordem de lucro líquido.")
        L.append("")
        for i, (prod, ofertas) in enumerate(yellows, start=1):
            L += render_product_block(prod, ofertas, i)

    # ----- REDS (resumo só) -----
    L.append("---")
    L.append("")
    L.append("## ❌ Ignore — produtos RED")
    L.append("")
    if not reds:
        L.append("_Nenhum produto vermelho._")
    else:
        L.append("Sem lucro real. Listados só pra você saber que foram avaliados.")
        L.append("")
        L.append("| Produto | Anúncios vistos | Preço médio BR |")
        L.append("|---|---:|---:|")
        for prod, ofertas in reds[:20]:
            avg = sum(o["_price"] for o in ofertas if o["_price"]) / max(1, sum(1 for o in ofertas if o["_price"]))
            L.append(f"| {prod} | {len(ofertas)} | R$ {avg:.2f} |")
        if len(reds) > 20:
            L.append(f"| _...e mais {len(reds)-20} produto(s)_ | | |")
    L.append("")

    # ----- Glossário -----
    L.append("---")
    L.append("")
    L.append("## 📚 Como interpretar os números")
    L.append("")
    L.append("- **Preço Brasil**: quanto você paga aqui (Liga/OLX/Amazon BR)")
    L.append("- **Vale nos EUA**: preço de venda na TCGPlayer Market (convertido pelo câmbio)")
    L.append("- **Lucro líquido / unidade**: o que sobra _por unidade_ depois de tudo: taxas de marketplace (13%), processamento (3%), spread cambial (2%), frete internacional (R$90) e logística 3PL (R$25). Custos fixos amortizados por bulk (packs = 24/box).")
    L.append("- **ROI líquido**: lucro_líquido ÷ preço_BR. É o **retorno do seu dinheiro investido**. Acima de 5% é o mínimo defensável; acima de 15% é excelente.")
    L.append("- **GREEN**: margem total ≥ 40% **E** ROI líquido ≥ 5% **E** lucro líquido positivo.")
    L.append("- **YELLOW**: margem entre 30-40%, OU margem ≥ 40% mas algum dos guarda-chuvas (líquido negativo, ROI raso) trava.")
    L.append("- **RED**: margem total < 30%. Sem retorno suficiente.")
    L.append("")
    L.append("### Premissas do cálculo (editáveis em `sealed/config.yaml`)")
    L.append("")
    L.append("- Câmbio USD→BRL: **R$ 5,40** (ajustar conforme cotação real)")
    L.append("- Taxa eBay/TCGPlayer: 13% · processamento: 3% · spread cambial: 2%")
    L.append("- Frete internacional: R$ 90 por embarque · 3PL: R$ 25")
    L.append("")
    L.append(f"_Gerado em {datetime.now(timezone.utc).isoformat(timespec='seconds')}_")

    out.write_text("\n".join(L) + "\n", encoding="utf-8")
    print(f"Snapshot didático escrito em {out}")
    print(f"  {len(greens)} verdes, {len(yellows)} amarelos, {len(reds)} vermelhos (agrupados por produto)")


if __name__ == "__main__":
    main()
