#!/usr/bin/env python3
"""analysis_report.py — reimprime o markdown da ÚLTIMA análise (entrega).

A entrega da análise é o markdown gerado por `lib/analysis/report.py` (fonte
única de formato) — este CLI só localiza o artefato `analysis_<stamp>` mais
recente do jogo e o imprime, pra colar VERBATIM no chat (regra da frota).

Uso: python scripts/analysis_report.py [--game pokemon] [--analysis-dir PATH]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import sealed_arbitrage_scanner as S
from lib.analysis import report


def latest_analysis_dir(results_root: Path) -> Path | None:
    dirs = sorted(results_root.glob("analysis_*"),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    return dirs[0] if dirs else None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Reimprime a última análise técnica.")
    ap.add_argument("--game", default="pokemon", choices=sorted(S.GAME_PROFILES))
    ap.add_argument("--analysis-dir", default=None)
    args = ap.parse_args(argv)

    d = Path(args.analysis_dir) if args.analysis_dir else \
        latest_analysis_dir(S.results_root_for(args.game, ROOT))
    if d is None or not (d / "analysis.json").exists():
        print("  [analysis] nenhum artefato de análise encontrado — rode "
              f"`python analyze_sealed.py --game {args.game}` primeiro.")
        return 0
    analysis = json.loads((d / "analysis.json").read_text(encoding="utf-8"))
    print(report.render_markdown(analysis))
    return 0


if __name__ == "__main__":
    from lib.console import harden_stdout
    harden_stdout()
    sys.exit(main())
