"""Store JSONL: append/read, linha corrompida contada e pulada, filtros."""
import json

from lib.analysis import history_store as store


def test_append_e_read(tmp_path):
    p = tmp_path / "h.jsonl"
    n = store.append_records(p, [{"sku_id": "a", "x": 1}, {"sku_id": "b", "x": 2}])
    assert n == 2
    recs, bad = store.read_records(p)
    assert len(recs) == 2 and bad == 0


def test_linha_corrompida_contada_e_pulada(tmp_path):
    p = tmp_path / "h.jsonl"
    p.write_text(json.dumps({"sku_id": "a"}) + "\n{quebrado\n[1,2]\n\n", encoding="utf-8")
    recs, bad = store.read_records(p)
    assert len(recs) == 1 and bad == 2


def test_filtros_por_sku_e_tipo(tmp_path):
    p = tmp_path / "h.jsonl"
    store.append_records(p, [
        {"sku_id": "a", "source_type": "ebay_active"},
        {"sku_id": "a", "source_type": "terapeak_capture"},
        {"sku_id": "b", "source_type": "ebay_active"},
    ])
    recs, _ = store.read_records(p, sku_id="a", source_type="ebay_active")
    assert len(recs) == 1
    grouped = store.by_sku(store.read_records(p)[0])
    assert set(grouped) == {"a", "b"} and len(grouped["a"]) == 2


def test_arquivo_ausente(tmp_path):
    recs, bad = store.read_records(tmp_path / "nada.jsonl")
    assert recs == [] and bad == 0
