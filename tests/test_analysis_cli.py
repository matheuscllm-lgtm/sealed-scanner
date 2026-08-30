"""CLI analyze_sealed: exemplo simulado ponta a ponta (sem rede), degradação
offline honesta (exit 0, DADOS_INSUFICIENTES — nunca crash, nunca chute) e
log de previsões."""
import json
from pathlib import Path

import analyze_sealed as az
from lib.analysis import history_store as store

ROOT = Path(__file__).resolve().parent.parent
MOCK_OUT = ROOT / "mock_data" / "analysis_sim" / "out"


def test_mock_roda_ponta_a_ponta(capsys):
    rc = az.main(["--mock", "--stamp", "TESTMOCK"])
    assert rc == 0
    out_dir = MOCK_OUT / "analysis_TESTMOCK"
    data = json.loads((out_dir / "analysis.json").read_text(encoding="utf-8"))
    assert data["simulated"] is True
    assert data["cycle_days"] == 24            # 10 + 7 + 7 do config
    states = {p["recommendation"]["state"] for p in data["products"]}
    # produto rico em dados decide; produto pobre é honesto
    assert "DADOS_INSUFICIENTES" in states
    assert any(s.startswith(("MANTER_", "JANELA_VENDA", "EVITAR_COMPRA"))
               for s in states)
    rich = next(p for p in data["products"] if p["sku_id"] == "sim-aaa-etb")
    assert rich["scenarios"]                    # cenários dos comparáveis
    for h, sc in rich["scenarios"].items():
        probs = [sc[n]["prob"] for n in ("pessimista", "base", "otimista")]
        assert abs(sum(probs) - 1.0) < 1e-6
        assert sc["pessimista"]["price_usd"] <= sc["base"]["price_usd"] \
            <= sc["otimista"]["price_usd"]
    # toda evidência carrega fonte + data
    for ev in rich["evidence"]:
        assert ev.get("source_type") and "collected_at" in ev
    md = (out_dir / "analise_tecnica.md").read_text(encoding="utf-8")
    assert "DADOS SIMULADOS" in md
    captured = capsys.readouterr().out
    assert "DADOS SIMULADOS" in captured        # entrega impressa no stdout


def test_mock_nao_grava_forecast_log():
    # simulado NUNCA contamina o log de previsões reais
    az.main(["--mock", "--stamp", "TESTMOCK2"])
    flog = ROOT / "data" / "forecasts" / "forecasts_pokemon.jsonl"
    if flog.exists():
        recs, _ = store.read_records(flog)
        assert not any("TESTMOCK2" in str(r.get("forecast_id")) for r in recs)


def test_offline_degrada_honesto(tmp_path, monkeypatch):
    import shutil
    scan = tmp_path / "unified_x"
    shutil.copytree(ROOT / "mock_data" / "analysis_sim" / "unified_fixture", scan)
    out_root = tmp_path / "results"
    monkeypatch.setattr(az.S, "results_root_for", lambda g, r: out_root)
    rc = az.main(["--scan-dir", str(scan), "--offline", "--no-forecast-log",
                  "--stamp", "OFF", "--today", "2026-08-29"])
    assert rc == 0
    data = json.loads((out_root / "analysis_OFF" / "analysis.json").read_text())
    # sem rede + sem stores: nenhum produto pode sair com decisão inventada
    for p in data["products"]:
        assert p["recommendation"]["state"] == "DADOS_INSUFICIENTES"
        assert p["signals"]["price_trend"]["insufficient"] is True


def test_scan_inexistente_sai_limpo(monkeypatch, tmp_path):
    monkeypatch.setattr(az.S, "results_root_for", lambda g, r: tmp_path / "vazio")
    monkeypatch.setattr(az.snap, "latest_unified_dir", lambda root: None)
    assert az.main(["--offline"]) == 0
