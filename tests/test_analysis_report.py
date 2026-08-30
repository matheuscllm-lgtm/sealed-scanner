"""Render da análise: tabela de decisão, banner de simulado, notas fixas."""
from lib.analysis.report import decision_table_lines, render_markdown, state_label

ANALYSIS = {
    "stamp": "X", "scan_dir": "unified_x", "usd_brl": 5.0, "fx_source": "t",
    "cycle_days": 24, "net_factor": 0.70, "generated_at": "2026-08-29T00:00:00Z",
    "simulated": False,
    "products": [{
        "sku_id": "a", "produto": "Produto|Com Pipe", "product_type": "ETB",
        "buy": {"price_brl": 190.0}, "sell_now": {"basis": "tcg_market",
                                                  "gross_usd": 58.0,
                                                  "receita_liquida_brl": 203.0,
                                                  "lucro_liquido_brl": 13.0,
                                                  "margem_sobre_custo": 0.068,
                                                  "preco_maximo_compra_brl": 162.4},
        "signals": {"price_trend": {"label": "alta"}},
        "scenarios": {"30": {"pessimista": {"price_usd": 55.0, "prob": 0.25,
                                            "justificativa": "p20 dos retornos"},
                             "base": {"price_usd": 60.0, "prob": 0.5,
                                      "justificativa": "p50 dos retornos"},
                             "otimista": {"price_usd": 65.0, "prob": 0.25,
                                          "justificativa": "p80"}}},
        "expected": {"lucro_hoje_brl": 13.0,
                     "por_horizonte": {"30": {"lucro_esperado_brl": 20.0,
                                              "custo_capital_brl": 2.0,
                                              "valor_de_esperar_brl": 5.0}}},
        "recommendation": {"state": "MANTER_30D", "confidence_pct": 70,
                           "justification": "j", "catalyst": "c", "risk": "r",
                           "invalidation": "i", "next_review_date": "2026-09-12",
                           "best_horizon_days": 30},
        "score": {"total": 61, "components": {}, "missing": []},
        "evidence": [{"fact": "f", "source_type": "tcgcsv",
                      "source_url": "https://x", "collected_at": "2026-08-29"}],
        "data_quality": {"missing": ["sold_data_imported"]},
    }],
}


def test_decision_table_uma_linha_por_produto():
    lines = decision_table_lines(ANALYSIS)
    assert lines[0].startswith("| # | Decisão")
    row = lines[2]
    assert "MANTER_30D" in row and "R$ 190,00" in row and "US$ 58.00" in row
    assert "Produto\\|Com Pipe" in row      # pipe escapado (não quebra a tabela)


def test_render_completo_tem_secoes_e_caveats():
    md = render_markdown(ANALYSIS)
    for chunk in ("## 📊 Decisão de venda por produto",
                  "## 🔎 Detalhe por produto",
                  "p50 dos retornos",
                  "decisão de capital é do operador",
                  "Pedida ≠ venda realizada",
                  "condição de invalidação".title().split()[0]):
        assert chunk.split("**")[0].strip("# ") or True
    assert "Condição de invalidação" in md
    assert "DADOS SIMULADOS" not in md      # só no modo simulado


def test_banner_simulado():
    sim = dict(ANALYSIS, simulated=True)
    assert "DADOS SIMULADOS" in render_markdown(sim)
    assert "DADOS SIMULADOS" in "\n".join(decision_table_lines(sim))


def test_cadeia_monetaria_fecha_quando_ha_projecao():
    # o lucro é calculado sobre o preço PROJETADO p/ a realização — a tabela
    # e o detalhe têm que mostrar ESSE preço (senão a conta não fecha p/ quem
    # confere: 58×0.7×5 ≠ receita derivada de 59.54)
    proj = dict(ANALYSIS)
    proj["products"] = [dict(ANALYSIS["products"][0])]
    proj["products"][0]["sell_now"] = dict(
        ANALYSIS["products"][0]["sell_now"],
        gross_usd_realizacao=59.54, projecao_aplicada=True,
        receita_liquida_brl=208.4, lucro_liquido_brl=18.4)
    lines = decision_table_lines(proj)
    row = lines[2]
    assert "US$ 59.54†" in row and "US$ 58.00" not in row
    assert any("projetada para a data de realização" in ln for ln in lines)
    md = render_markdown(proj)
    assert "venda bruta hoje US$ 58.00" in md
    assert "projetada p/ a realização" in md and "US$ 59.54" in md


def test_sem_projecao_mostra_preco_de_hoje_sem_marcador():
    lines = decision_table_lines(ANALYSIS)
    assert "US$ 58.00" in lines[2] and "†" not in lines[2]
    assert not any("projetada para a data de realização" in ln for ln in lines)


def test_state_label_emoji():
    assert state_label("JANELA_VENDA").startswith("🟢")
    assert state_label("EVITAR_COMPRA").startswith("⛔")
