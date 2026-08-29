"""NÃO-INTERFERÊNCIA (regra dura): a análise nunca altera o scan.

- rodar analyze_sealed sobre um scan deixa o unified_deals.csv BYTE-IDÊNTICO;
- a entrega do snapshot sem artefato de análise sai SEM a seção de decisão
  (byte-idêntica ao comportamento histórico); com artefato casando o scan,
  ganha a 3ª tabela — e as seções originais continuam todas lá;
- compute_margin segue com exatamente as 4 chaves (contrato de test_gross_only,
  reafirmado aqui do ponto de vista da camada nova).
"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

import analyze_sealed as az
import sealed_arbitrage_scanner as S

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import snapshot  # noqa: E402

FIXTURE = ROOT / "mock_data" / "analysis_sim" / "unified_fixture"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def test_analyze_nao_toca_o_csv_do_scan(tmp_path, monkeypatch):
    scan = tmp_path / "unified_20260829_000000"
    shutil.copytree(FIXTURE, scan)
    before = _sha(scan / "unified_deals.csv")
    out_root = tmp_path / "results"
    monkeypatch.setattr(az.S, "results_root_for", lambda g, r: out_root)
    rc = az.main(["--scan-dir", str(scan), "--offline", "--no-forecast-log",
                  "--stamp", "T1", "--today", "2026-08-29"])
    assert rc == 0
    assert _sha(scan / "unified_deals.csv") == before
    assert (out_root / "analysis_T1" / "analysis.json").exists()


def test_compute_margin_segue_com_4_chaves():
    out = S.compute_margin(100.0, 30.0, {"currency": {"usd_brl": 5.0}})
    assert set(out) == {"us_price_brl", "gross_profit_brl",
                       "total_margin_pct", "us_discount_pct"}


def _run_snapshot(tmp_path, monkeypatch, results_root, out_dir):
    monkeypatch.setattr(snapshot, "RESULTS", results_root)
    monkeypatch.setattr(snapshot, "OUT_DIR", out_dir)
    monkeypatch.setattr(sys, "argv", ["snapshot.py"])
    snapshot.main()
    files = sorted(out_dir.glob("scan-*.md"))
    assert files
    return files[-1].read_text(encoding="utf-8")


def test_snapshot_sem_artefato_nao_tem_secao_de_decisao(tmp_path, monkeypatch):
    results = tmp_path / "results"
    shutil.copytree(FIXTURE, results / "unified_20260829_000000")
    text = _run_snapshot(tmp_path, monkeypatch, results, tmp_path / "snaps")
    assert "Decisão de venda" not in text
    assert "## Notas" in text and "## Ranking completo por produto" in text


def test_snapshot_com_artefato_ganha_3a_tabela(tmp_path, monkeypatch):
    results = tmp_path / "results"
    scan = results / "unified_20260829_000000"
    shutil.copytree(FIXTURE, scan)
    adir = results / "analysis_T2"
    adir.mkdir(parents=True)
    (adir / "analysis.json").write_text(json.dumps({
        "scan_dir": scan.name, "simulated": True, "cycle_days": 24,
        "net_factor": 0.70, "generated_at": "2026-08-29T00:00:00Z",
        "stamp": "T2",
        "products": [{"sku_id": "sim-aaa-etb", "produto": "Simul Alpha ETB",
                      "buy": {"price_brl": 190.0},
                      "sell_now": {"gross_usd": 58.0},
                      "expected": {"lucro_hoje_brl": 18.4,
                                   "por_horizonte": {"90": {
                                       "lucro_esperado_brl": 38.7,
                                       "custo_capital_brl": 7.0,
                                       "valor_de_esperar_brl": 13.3}}},
                      "recommendation": {"state": "MANTER_90D",
                                         "confidence_pct": 90,
                                         "best_horizon_days": 90,
                                         "next_review_date": "2026-09-28"},
                      "score": {"total": 76}}]}), encoding="utf-8")
    text = _run_snapshot(tmp_path, monkeypatch, results, tmp_path / "snaps")
    assert "## 📊 Decisão de venda por produto" in text
    assert "MANTER_90D" in text and "DADOS SIMULADOS" in text
    # seções originais intactas
    assert "## 🟢🟡 Produtos acionáveis (GREEN + YELLOW)" in text
    assert "## Ranking completo por produto" in text and "## Notas" in text


def test_snapshot_artefato_de_outro_scan_e_ignorado(tmp_path, monkeypatch):
    results = tmp_path / "results"
    shutil.copytree(FIXTURE, results / "unified_20260829_000000")
    adir = results / "analysis_T3"
    adir.mkdir(parents=True)
    (adir / "analysis.json").write_text(json.dumps(
        {"scan_dir": "unified_OUTRO", "products": []}), encoding="utf-8")
    text = _run_snapshot(tmp_path, monkeypatch, results, tmp_path / "snaps")
    assert "Decisão de venda" not in text
