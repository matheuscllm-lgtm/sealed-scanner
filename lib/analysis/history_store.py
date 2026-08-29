"""lib/analysis/history_store.py — stores JSONL append-only da análise.

Um objeto JSON por linha (histórico de oferta eBay, imports de sold/trends,
log de previsões). Todos GITIGNORED (`data/history/`, `data/forecasts/`) —
dado de mercado nunca entra no repo (postura de repo público da frota).

Robustez: linha corrompida é CONTADA e pulada (nunca derruba a leitura);
escrita é append simples (cada registro é independente).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def append_records(path: Path, records: list[dict]) -> int:
    """Anexa registros (1 JSON/linha). Retorna quantos gravou."""
    if not records:
        return 0
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return len(records)


def read_records(path: Path, sku_id: str | None = None,
                 source_type: str | None = None) -> tuple[list[dict], int]:
    """Lê o JSONL. Retorna (registros, linhas_corrompidas_puladas)."""
    if not path.exists():
        return [], 0
    out: list[dict] = []
    bad = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                bad += 1
                continue
            if not isinstance(rec, dict):
                bad += 1
                continue
            if sku_id is not None and rec.get("sku_id") != sku_id:
                continue
            if source_type is not None and rec.get("source_type") != source_type:
                continue
            out.append(rec)
    return out, bad


def by_sku(records: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for rec in records:
        sid = rec.get("sku_id")
        if sid:
            out.setdefault(sid, []).append(rec)
    return out
