#!/usr/bin/env python3
"""build_delivery_xlsx.py — XLSX condensado p/ entrega (Drive via MCP).

Lê o unified_deals.csv de um scan e gera um XLSX pequeno só com os deals
ACIONÁVEIS (GREEN + YELLOW) + aba Resumo. O arquivo cheio (~800 linhas, a
maioria RED) é grande demais pra upload inline do MCP; este condensado cabe.

Uso: python scripts/build_delivery_xlsx.py [<dir do scan>] [<saida.xlsx>]
     (sem args: usa o results/unified_* mais recente; saida em TEMP)
"""
from __future__ import annotations

import csv
import sys
import tempfile
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent

COLS = [
    ("Confiança do deal", "Tier"),
    ("Fonte", "Fonte"),
    ("Produto (canônico)", "Produto"),
    ("Tipo", "Tipo"),
    ("Preço BR (R$)", "BR R$"),
    ("Preço US (R$)", "US R$"),
    ("Margem total %", "Margem %"),
    ("Margem líquida est. %", "Líq %"),
    ("Confiança do match", "Match"),
    ("URL", "URL"),
]
FILLS = {
    "GREEN": PatternFill("solid", fgColor="C6EFCE"),
    "YELLOW": PatternFill("solid", fgColor="FFEB9C"),
}
ORDER = {"GREEN": 0, "YELLOW": 1}


def latest_scan_dir() -> Path:
    dirs = sorted((ROOT / "results").glob("unified_*"), key=lambda d: d.stat().st_mtime, reverse=True)
    if not dirs:
        sys.exit("ERRO: nenhum results/unified_* encontrado.")
    return dirs[0]


def _margin(row: dict) -> float:
    try:
        return float(row.get("Margem total %") or -999)
    except ValueError:
        return -999.0


def main() -> None:
    scan_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else latest_scan_dir()
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(tempfile.gettempdir()) / "sealed_delivery.xlsx"
    src = scan_dir / "unified_deals.csv"
    rows = list(csv.DictReader(src.open(encoding="utf-8")))
    sel = [r for r in rows if r["Confiança do deal"] in ("GREEN", "YELLOW")]
    sel.sort(key=lambda r: (ORDER.get(r["Confiança do deal"], 9), -_margin(r)))

    wb = Workbook()
    ws = wb.active
    ws.title = "Deals (GREEN+YELLOW)"
    ws.append([lbl for _, lbl in COLS])
    for c in ws[1]:
        c.font = Font(bold=True)
    for r in sel:
        ws.append([r.get(k, "") for k, _ in COLS])
        fill = FILLS.get(r["Confiança do deal"])
        if fill:
            for c in ws[ws.max_row]:
                c.fill = fill
    for i, (_, lbl) in enumerate(COLS, 1):
        ws.column_dimensions[get_column_letter(i)].width = max(10, min(44, len(lbl) + 4))
    ws.freeze_panes = "A2"

    green = sum(1 for r in sel if r["Confiança do deal"] == "GREEN")
    yellow = len(sel) - green
    ws2 = wb.create_sheet("Resumo")
    summary = [
        ("Scan", scan_dir.name),
        ("GREEN", green),
        ("YELLOW", yellow),
        ("RED (não incluídos)", len(rows) - len(sel)),
        ("Total linhas scan", len(rows)),
    ]
    for k, v in summary:
        ws2.append([k, v])
    for i in range(1, len(summary) + 1):
        ws2[f"A{i}"].font = Font(bold=True)

    out.parent.mkdir(parents=True, exist_ok=True)
    wb.save(out)
    print(f"OK | GREEN={green} YELLOW={yellow} | {out} | {out.stat().st_size} bytes")
    print(f"PATH={out}")


if __name__ == "__main__":
    main()
