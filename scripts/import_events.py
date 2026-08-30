#!/usr/bin/env python3
"""import_events.py — registra evento de reprint/restock no events YAML.

Único caminho que PROMOVE informação a evento (`data/events_<jogo>.yaml`,
versionado). Exige fonte real: sem `--source-url`, sem evento. Um candidato do
collect_market_intel.py vira evento por AQUI, depois de curadoria (operador ou
sessão do agente com a URL conferida). "Esgotado" não é evento.

Uso (um evento por chamada — auditável):
    python scripts/import_events.py --game pokemon \
        --id ev-2026-08-ssp-restock --type restock --event-date 2026-08-20 \
        --source-type retailer --source-url "https://..." \
        --classification RESTOCK_OBSERVADO --set-codes SSP \
        --note "Restock ETB SSP na Target US"
"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import yaml

import sealed_arbitrage_scanner as S
from lib.analysis.events import EVENT_TYPES, EVIDENCE_CLASSES, SOURCE_TYPES, load_events
from lib.analysis.profiles import analysis_config, resolve_path


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Registra um evento curado no events YAML.")
    ap.add_argument("--game", default="pokemon", choices=sorted(S.GAME_PROFILES))
    ap.add_argument("--id", required=True)
    ap.add_argument("--type", required=True, choices=EVENT_TYPES)
    ap.add_argument("--event-date", required=True, help="YYYY-MM-DD")
    ap.add_argument("--source-type", required=True, choices=SOURCE_TYPES)
    ap.add_argument("--source-url", required=True)
    ap.add_argument("--classification", default="INDETERMINADA", choices=EVIDENCE_CLASSES)
    ap.add_argument("--set-codes", default="", help="códigos de set, separados por vírgula")
    ap.add_argument("--sku-ids", default="", help="sku_ids explícitos, separados por vírgula")
    ap.add_argument("--note", default="")
    args = ap.parse_args(argv)

    if not args.set_codes and not args.sku_ids:
        print("ERRO: informe --set-codes e/ou --sku-ids (escopo do evento).")
        return 2

    config = S.load_yaml(ROOT / S.GAME_PROFILES[args.game]["config"], "config.yaml")
    acfg = analysis_config(config)
    path = resolve_path(ROOT, (acfg.get("files") or {}).get(
        "events", f"data/events_{args.game}.yaml"))

    data = {}
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    events = data.get("events") or []
    if any((e or {}).get("id") == args.id for e in events):
        print(f"ERRO: evento {args.id!r} já existe em {path.name}.")
        return 2

    entry = {
        "id": args.id, "type": args.type, "event_date": args.event_date,
        "source_type": args.source_type, "source_url": args.source_url,
        "collected_at": date.today().isoformat(),
        "classification": args.classification, "market": "US",
        "note": args.note,
        "scope": {},
    }
    if args.set_codes:
        entry["scope"]["set_codes"] = [s.strip() for s in args.set_codes.split(",") if s.strip()]
    if args.sku_ids:
        entry["scope"]["sku_ids"] = [s.strip() for s in args.sku_ids.split(",") if s.strip()]
    events.append(entry)
    data["events"] = events
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False),
                    encoding="utf-8")

    ok, rejected = load_events(path)  # re-valida o arquivo inteiro
    print(f"  [events] {args.id} gravado em {path.name} — arquivo agora tem "
          f"{len(ok)} evento(s) válido(s)"
          + (f" · {rejected} rejeitado(s) (conferir!)" if rejected else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
