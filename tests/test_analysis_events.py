"""Events YAML: entrada sem fonte é REJEITADA; tipos fechados; fórum vira
RUMOR; escopo por set_code/sku_ids."""
from pathlib import Path

from lib.analysis.events import events_for_sku, load_events


def _write(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "events.yaml"
    p.write_text(body, encoding="utf-8")
    return p


BASE = """events:
  - id: ok-1
    type: restock
    event_date: "2026-08-01"
    source_type: retailer
    source_url: "https://x"
    collected_at: "2026-08-20"
    classification: RESTOCK_OBSERVADO
    scope: {set_codes: [SSP]}
"""


def test_carrega_evento_valido(tmp_path):
    evs, rejected = load_events(_write(tmp_path, BASE), log=lambda *_: None)
    assert len(evs) == 1 and rejected == 0
    assert evs[0].set_codes == ["SSP"]


def test_rejeita_sem_source_url(tmp_path):
    body = BASE.replace('source_url: "https://x"\n    ', "")
    evs, rejected = load_events(_write(tmp_path, body), log=lambda *_: None)
    assert evs == [] and rejected == 1


def test_rejeita_tipo_desconhecido(tmp_path):
    # "esgotado" NÃO é evento — não prova descontinuação
    body = BASE.replace("type: restock", "type: esgotado")
    evs, rejected = load_events(_write(tmp_path, body), log=lambda *_: None)
    assert evs == [] and rejected == 1


def test_forum_nunca_confirmada(tmp_path):
    body = BASE.replace("source_type: retailer", "source_type: forum") \
               .replace("classification: RESTOCK_OBSERVADO", "classification: CONFIRMADA")
    evs, _ = load_events(_write(tmp_path, body), log=lambda *_: None)
    assert evs[0].classification == "RUMOR"


def test_arquivo_ausente_e_lista_vazia(tmp_path):
    evs, rejected = load_events(tmp_path / "nao_existe.yaml")
    assert evs == [] and rejected == 0


def test_escopo_por_set_e_por_sku(tmp_path):
    body = BASE + """  - id: ok-2
    type: allocation
    event_date: "2026-08-02"
    source_type: distributor
    source_url: "https://y"
    collected_at: "2026-08-21"
    scope: {sku_ids: [meu-sku]}
"""
    evs, _ = load_events(_write(tmp_path, body), log=lambda *_: None)
    assert [e.id for e in events_for_sku(evs, "meu-sku", "XXX")] == ["ok-2"]
    assert [e.id for e in events_for_sku(evs, "outro", "SSP")] == ["ok-1"]
    assert events_for_sku(evs, "outro", "XXX") == []
