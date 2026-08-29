"""Importadores: Terapeak (linha ruim contada, ambíguo descartado, dedupe,
--sku força, seller via getItem com cache e encerrado>90d) e Trends CSV."""
from pathlib import Path
from types import SimpleNamespace

from lib.analysis.importers import (enrich_sellers, match_title_to_sku,
                                    parse_terapeak_csv, parse_trends_csv)

SKUS = [SimpleNamespace(id="ssp-etb-en", name="Surging Sparks ETB"),
        SimpleNamespace(id="ssp-bb-en", name="Surging Sparks Booster Box")]


def _gate(title: str, sku) -> bool:
    low = title.lower()
    if sku.id == "ssp-etb-en":
        return "elite trainer" in low
    if sku.id == "ssp-bb-en":
        return "booster box" in low or "elite trainer" in low  # p/ caso ambíguo
    return False


def _gate_strict(title: str, sku) -> bool:
    low = title.lower()
    if sku.id == "ssp-etb-en":
        return "elite trainer" in low
    return "booster box" in low


CSV = """item_id,title,avg_sold_price,avg_shipping,total_sold,item_sales,date_last_sold,query
111,"Surging Sparks Elite Trainer Box",44.90,0.00,3,134.70,"Aug 25, 2026","ssp etb"
222,"Surging Sparks Booster Box",180.00,0.00,1,180.00,"Aug 20, 2026","ssp etb"
333,"Coisa Aleatória Sem Match",10.00,0.00,1,10.00,"Aug 01, 2026","x"
,linha sem id,1.00,0,1,1,"d","q"
444,"Surging Sparks Elite Trainer Box",0,0.00,2,0,"Aug 02, 2026","q"
"""


def _write(tmp_path: Path) -> Path:
    p = tmp_path / "cap.csv"
    p.write_text(CSV, encoding="utf-8")
    return p


def test_match_unico_obrigatorio():
    sku, why = match_title_to_sku("Surging Sparks Booster Box", SKUS, _gate_strict)
    assert sku.id == "ssp-bb-en" and why == "ok"
    assert match_title_to_sku("Surging Sparks Elite Trainer Box", SKUS, _gate)[1] == "ambiguous"
    assert match_title_to_sku("nada", SKUS, _gate)[1] == "no_match"


def test_parse_terapeak_conta_tudo(tmp_path):
    recs, stats = parse_terapeak_csv(_write(tmp_path), SKUS, _gate_strict, 30,
                                     collected_at="2026-08-29")
    assert stats.total == 5
    assert stats.imported == 2          # 111 (ETB) + 222 (BB)
    assert stats.bad_rows == 2          # sem id + preço 0
    assert stats.no_match == 1
    r = recs[0]
    assert r["sku_id"] == "ssp-etb-en" and r["lookback_days"] == 30
    assert r["source_url"] == "terapeak_scrape:cap.csv"
    assert r["seller"] is None          # seller só via getItem


def test_parse_terapeak_dedupe_por_item_e_arquivo(tmp_path):
    p = _write(tmp_path)
    existing = {("111", 30, "cap.csv")}
    recs, stats = parse_terapeak_csv(p, SKUS, _gate_strict, 30, "2026-08-29",
                                     existing_keys=existing)
    assert stats.duplicates == 1
    assert all(r["item_id"] != "111" for r in recs)


def test_parse_terapeak_sku_forcado(tmp_path):
    recs, stats = parse_terapeak_csv(_write(tmp_path), SKUS, _gate_strict, 90,
                                     "2026-08-29", sku_hint="ssp-etb-en")
    # forçado: até o "sem match" entra como o SKU indicado
    assert stats.imported == 3
    assert {r["sku_id"] for r in recs} == {"ssp-etb-en"}


def test_enrich_sellers_cache_e_encerrado():
    recs = [{"item_id": "1"}, {"item_id": "2"}, {"item_id": "3"}]
    cache = {"1": "probstein123"}
    calls = []

    def get_item(item_id):
        calls.append(item_id)
        if item_id == "2":
            return {"seller": {"username": "lojista"}}
        return None                      # encerrado >90d — some da API

    counts = enrich_sellers(recs, get_item, cache, log=lambda *_: None)
    assert counts == {"cached": 1, "fetched": 1, "gone": 1, "errors": 0}
    assert calls == ["2", "3"]           # o 1 veio do cache
    assert recs[0]["seller"] == "probstein123" and recs[0]["is_probstein"] is True
    assert recs[1]["seller"] == "lojista" and recs[1]["is_probstein"] is False
    assert "seller" not in recs[2] or recs[2].get("seller") is None
    assert cache["3"] is None            # negativo cacheado (não re-gasta chamada)


def test_parse_trends_pula_cabecalho(tmp_path):
    p = tmp_path / "trends.csv"
    p.write_text("Categoria: Todas\n\nSemana,pokemon etb\n2026-08-10,55\n"
                 "2026-08-17,63\nlixo,abc\n", encoding="utf-8")
    recs, stats = parse_trends_csv(p, "ssp-etb-en", "pokemon etb", "2026-08-29")
    assert stats.imported == 2 and stats.bad_rows == 4  # cabeçalho, vazia, header, lixo
    assert recs[0]["value"] == 55 and recs[0]["source_type"] == "trends_import"
