"""Risco de reprint: SEM_EVIDENCIA nunca é prova de risco baixo; evidência
curada com fonte vence heurística; fórum nunca passa de RUMOR (via events)."""
from lib.analysis.events import Event
from lib.analysis.reprint import is_heavy_reprint, reprint_risk

SCFG = {"print_cycle_late_months": 18, "print_cycle_old_months": 30}


def _ev(type_, cls="CONFIRMADA", id_="e1"):
    return Event(id=id_, type=type_, event_date="2026-08-01", source_type="news",
                 source_url="https://x", collected_at="2026-08-20",
                 classification=cls)


def test_sem_evidencia_set_jovem_nao_e_baixo():
    r = reprint_risk("SV10: Destined Rivals", 10, [], SCFG)
    assert r.detail["level"] != "baixo"          # jovem + sem evidência ≠ baixo
    assert r.detail["evidence_state"] == "SEM_EVIDENCIA"
    assert any("ausência" in reason for reason in r.detail["reasons"])


def test_sem_evidencia_set_velho_e_baixo_estrutural():
    r = reprint_risk("SWSH11: Lost Origin", 40, [], SCFG)
    assert r.detail["level"] == "baixo"


def test_heavy_reprint_e_alto():
    assert is_heavy_reprint("SV: 151")
    assert is_heavy_reprint("Prismatic Evolutions")
    assert not is_heavy_reprint("Surging Sparks")
    r = reprint_risk("SV: Prismatic Evolutions", 40, [], SCFG)
    assert r.detail["level"] == "alto"


def test_evento_restock_e_alto():
    r = reprint_risk("Surging Sparks", 40, [_ev("restock")], SCFG)
    assert r.detail["level"] == "alto"
    assert r.detail["evidence_state"] == "RESTOCK_OBSERVADO"


def test_oop_confirmado_vence_estrutural():
    r = reprint_risk("Surging Sparks", 10, [_ev("out_of_print_confirmed")], SCFG)
    assert r.detail["level"] == "baixo"
    assert r.detail["oop_confirmed"] is True
    assert "OOP_CONFIRMADO" in r.label


def test_rumor_nao_vira_alto():
    r = reprint_risk("Surging Sparks", 40, [_ev("reprint_announced", cls="RUMOR")], SCFG)
    assert r.detail["evidence_state"] == "RUMOR"
    assert r.detail["level"] != "alto"
    assert any("RUMOR" in reason for reason in r.detail["reasons"])
