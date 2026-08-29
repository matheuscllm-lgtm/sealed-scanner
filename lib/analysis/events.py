"""lib/analysis/events.py — eventos de reprint/restock (curadoria manual).

Arquivo VERSIONADO `data/events_<jogo>.yaml` (conhecimento curado, como o
registry): eventos de reprint/restock/out-of-print do mercado US, SEMPRE com
fonte real (`source_url` + `collected_at`). Regras duras:
  - entrada sem `source_url`/`collected_at`/`event_date` é REJEITADA com aviso
    (sem fonte, sem fato — nunca deduzir);
  - "esgotado" NÃO é tipo de evento (não prova descontinuação);
  - `SEM_EVIDENCIA` (nenhum evento) ≠ risco baixo de reprint — o risco
    estrutural (heavy-reprint/idade) continua valendo (ver reprint.py).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

# Tipos de evento aceitos (fechados de propósito).
EVENT_TYPES = (
    "reprint_announced",       # reprint anunciado oficialmente
    "reprint_shipping",        # nova onda/reprint chegando ao varejo
    "restock",                 # restock observado (PC/varejista/distribuidor)
    "out_of_print_confirmed",  # fim de impressão CONFIRMADO por fonte
    "allocation",              # alocação/limite de distribuidor (oferta apertada)
    "new_product_with_set",    # produto futuro contendo boosters da coleção
)
# Classificação da EVIDÊNCIA (força da fonte).
EVIDENCE_CLASSES = ("CONFIRMADA", "SINAL_DE_MERCADO", "RUMOR", "INDETERMINADA")
# Tipos de fonte aceitos.
SOURCE_TYPES = ("pokemon_official", "pokemon_center", "distributor", "retailer",
                "news", "forum", "operator_note")


@dataclass
class Event:
    id: str
    type: str
    event_date: str                 # YYYY-MM-DD
    source_type: str
    source_url: str
    collected_at: str               # YYYY-MM-DD
    classification: str = "INDETERMINADA"
    market: str = "US"
    note: str = ""
    set_codes: list[str] = field(default_factory=list)
    sku_ids: list[str] = field(default_factory=list)


def load_events(path: Path, log=print) -> tuple[list[Event], int]:
    """Carrega e VALIDA o events YAML. Retorna (eventos_válidos, rejeitados).

    Arquivo ausente = lista vazia (condição esperada num jogo sem curadoria).
    """
    if not path.exists():
        return [], 0
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        log(f"  [events] AVISO: {path.name} inválido ({exc}) — ignorado.")
        return [], 0
    rejected = 0
    out: list[Event] = []
    for raw in (data.get("events") or []):
        if not isinstance(raw, dict):
            rejected += 1
            continue
        missing = [k for k in ("id", "type", "event_date", "source_type",
                               "source_url", "collected_at") if not raw.get(k)]
        if missing:
            rejected += 1
            log(f"  [events] entrada rejeitada ({raw.get('id') or '?'}): "
                f"faltando {', '.join(missing)} — sem fonte, sem fato.")
            continue
        if raw["type"] not in EVENT_TYPES:
            rejected += 1
            log(f"  [events] entrada rejeitada ({raw['id']}): type "
                f"{raw['type']!r} desconhecido (aceitos: {', '.join(EVENT_TYPES)}). "
                "Lembre: 'esgotado' não é evento — não prova descontinuação.")
            continue
        if raw["source_type"] not in SOURCE_TYPES:
            rejected += 1
            log(f"  [events] entrada rejeitada ({raw['id']}): source_type "
                f"{raw['source_type']!r} desconhecido.")
            continue
        cls = raw.get("classification") or "INDETERMINADA"
        if cls not in EVIDENCE_CLASSES:
            cls = "INDETERMINADA"
        # Fórum/rede social NUNCA passa de RUMOR (regra dura).
        if raw["source_type"] == "forum" and cls == "CONFIRMADA":
            cls = "RUMOR"
        scope = raw.get("scope") or {}
        out.append(Event(
            id=str(raw["id"]), type=raw["type"], event_date=str(raw["event_date"]),
            source_type=raw["source_type"], source_url=str(raw["source_url"]),
            collected_at=str(raw["collected_at"]), classification=cls,
            market=str(raw.get("market") or "US"), note=str(raw.get("note") or ""),
            set_codes=[str(s) for s in (scope.get("set_codes") or ([scope["set_code"]] if scope.get("set_code") else []))],
            sku_ids=[str(s) for s in (scope.get("sku_ids") or [])],
        ))
    return out, rejected


def events_for_sku(events: list[Event], sku_id: str, set_code: str) -> list[Event]:
    """Eventos cujo escopo cobre este SKU (por sku_id explícito ou set_code)."""
    out = []
    for ev in events:
        if sku_id in ev.sku_ids or (set_code and set_code in ev.set_codes):
            out.append(ev)
    return out
