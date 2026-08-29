"""lib/analysis/importers.py — parsers puros dos imports manuais.

  1. Terapeak (eBay Seller Hub > Product Research > Sold): NÃO existe export
     nem coluna de seller na UI (validado pelo operador em 2026-08-29, conta
     real) — a captura vem do snippet `scripts/terapeak_scrape.js` (lê só a
     tabela que a tela LOGADA renderiza; 100% oficial, nada de burlar auth).
     Colunas: item_id,title,avg_sold_price,avg_shipping,total_sold,item_sales,
     date_last_sold,query. O seller vem DEPOIS, por item, via Browse API
     getItem (scripts/import_terapeak.py) — anúncio encerrado há >~90d some da
     API → seller=null (nunca inventado; por isso a captura é mensal).
  2. Google Trends: CSV exportado manualmente da UI (API não-oficial é frágil
     — decisão de fase 1: só import manual).

Regras: linha ruim é CONTADA e pulada; título ambíguo (casa 2+ SKUs) é
DESCARTADO e contado (nunca chutamos SKU); exclusões de título (não-EN,
graded, aberto/usado, lote) reusam o gate do build_ebay_reference.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ImportStats:
    total: int = 0
    imported: int = 0
    bad_rows: int = 0
    no_match: int = 0
    ambiguous: int = 0
    duplicates: int = 0
    details: list[str] = field(default_factory=list)

    def summary(self) -> str:
        return (f"{self.imported}/{self.total} linhas importadas · "
                f"{self.bad_rows} inválidas · {self.no_match} sem match · "
                f"{self.ambiguous} ambíguas (descartadas) · "
                f"{self.duplicates} duplicadas")


def _f(v) -> float | None:
    try:
        x = float(str(v).replace("$", "").replace(",", ""))
        return x if x >= 0 else None
    except (TypeError, ValueError):
        return None


def _i(v) -> int | None:
    try:
        return int(float(str(v).replace(",", "")))
    except (TypeError, ValueError):
        return None


def match_title_to_sku(title: str, skus: list, gate) -> tuple[object | None, str]:
    """Casa um título eBay a EXATAMENTE um SKU via o gate injetado
    (build_ebay_reference.title_passes_gate). Retorna (sku|None, motivo)."""
    hits = [s for s in skus if gate(title, s)]
    if len(hits) == 1:
        return hits[0], "ok"
    if not hits:
        return None, "no_match"
    return None, "ambiguous"


def parse_terapeak_csv(csv_path: Path, skus: list, gate, lookback_days: int,
                       collected_at: str, sku_hint: str | None = None,
                       existing_keys: set | None = None
                       ) -> tuple[list[dict], ImportStats]:
    """CSV da captura Terapeak → registros normalizados p/ o store de sold.

    `gate(title, sku) -> bool` é injetado (o title_passes_gate real nos CLIs,
    um stub nos testes). `existing_keys` = chaves (item_id, lookback, arquivo)
    já no store — duplicata é pulada e contada (aditivo, nunca duplica).
    """
    stats = ImportStats()
    existing_keys = existing_keys or set()
    records: list[dict] = []
    forced = None
    if sku_hint:
        forced = next((s for s in skus if s.id == sku_hint), None)
        if forced is None:
            raise SystemExit(f"--sku {sku_hint!r} não existe no registry.")
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.DictReader(fh):
            stats.total += 1
            item_id = (row.get("item_id") or "").strip()
            title = (row.get("title") or "").strip().strip('"')
            price = _f(row.get("avg_sold_price"))
            qty = _i(row.get("total_sold"))
            if not item_id or not title or price is None or price <= 0:
                stats.bad_rows += 1
                continue
            if forced is not None:
                sku = forced
            else:
                sku, why = match_title_to_sku(title, skus, gate)
                if sku is None:
                    if why == "ambiguous":
                        stats.ambiguous += 1
                        stats.details.append(f"ambíguo: {title[:70]}")
                    else:
                        stats.no_match += 1
                    continue
            key = (item_id, lookback_days, csv_path.name)
            if key in existing_keys:
                stats.duplicates += 1
                continue
            existing_keys.add(key)
            records.append({
                "sku_id": sku.id,
                "source_type": "terapeak_capture",
                "item_id": item_id,
                "title": title,
                "avg_sold_price_usd": price,
                "avg_shipping_usd": _f(row.get("avg_shipping")),
                "total_sold": qty or 0,
                "item_sales_usd": _f(row.get("item_sales")),
                "date_last_sold": (row.get("date_last_sold") or "").strip().strip('"'),
                "lookback_days": lookback_days,
                "query": (row.get("query") or "").strip().strip('"'),
                "seller": None,          # preenchido pelo enrich (getItem)
                "is_probstein": None,
                "collected_at": collected_at,
                "source_url": f"terapeak_scrape:{csv_path.name}",
                "source_file": csv_path.name,
            })
            stats.imported += 1
    return records, stats


PROBSTEIN_SELLERS = ("probstein123", "probstein")


def enrich_sellers(records: list[dict], get_item, seller_cache: dict,
                   log=print) -> dict:
    """Preenche seller/is_probstein via Browse API getItem (injetável).

    `get_item(item_id) -> dict|None` (None = item sumiu da API — encerrado
    >~90d → seller fica None, honesto). `seller_cache` = {item_id: username}
    persistido pelo caller (poupa as 5k chamadas/dia)."""
    counts = {"cached": 0, "fetched": 0, "gone": 0, "errors": 0}
    for rec in records:
        iid = rec["item_id"]
        if iid in seller_cache:
            username = seller_cache[iid]
            counts["cached"] += 1
        else:
            try:
                item = get_item(iid)
            except Exception as exc:
                counts["errors"] += 1
                log(f"  [terapeak] getItem {iid}: erro {type(exc).__name__} — seller fica vazio")
                continue
            if not item:
                seller_cache[iid] = None
                counts["gone"] += 1
                continue
            username = ((item.get("seller") or {}).get("username") or None)
            seller_cache[iid] = username
            counts["fetched"] += 1
        if username:
            rec["seller"] = username
            rec["is_probstein"] = username.lower() in PROBSTEIN_SELLERS
    return counts


def parse_trends_csv(csv_path: Path, sku_id: str, term: str,
                     collected_at: str) -> tuple[list[dict], ImportStats]:
    """CSV do Google Trends (export manual da UI) → registros do store.

    Formato tolerado: linhas `data,valor` (o cabeçalho multilinha do export
    oficial é pulado — linha sem data ISO/valor numérico é ignorada e contada).
    """
    stats = ImportStats()
    records: list[dict] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as fh:
        for row in csv.reader(fh):
            stats.total += 1
            if len(row) < 2:
                stats.bad_rows += 1
                continue
            d = (row[0] or "").strip()
            v = _i(row[1])
            if len(d) < 7 or not d[:4].isdigit() or v is None:
                stats.bad_rows += 1
                continue
            records.append({
                "sku_id": sku_id, "source_type": "trends_import",
                "date": d, "value": v, "term": term,
                "collected_at": collected_at,
                "source_url": f"google_trends_export:{csv_path.name}",
                "source_file": csv_path.name,
            })
            stats.imported += 1
    return records, stats
