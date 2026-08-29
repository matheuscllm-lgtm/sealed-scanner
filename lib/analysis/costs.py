"""lib/analysis/costs.py — modelo financeiro SIMPLIFICADO (decisão do operador).

Fator líquido ÚNICO configurável (`analysis.net_factor`, default 0.70 = custos
agregados ~30%: Probstein + PayPal + logística + imposto, definidos POR FORA
pelo operador — o sistema só aplica o fator, sem modelar canal a canal).

Fórmulas (travadas em teste — tests/test_analysis_costs.py):
  receita_liquida     = venda_bruta × net_factor
  lucro_liquido       = receita_liquida_convertida_BRL − preço_compra
  margem_sobre_custo  = lucro_liquido ÷ preço_compra
  preço_max_compra    = receita_liquida_BRL ÷ (1 + min_margin_over_cost)
  custo_capital       = preço_compra × annual_cost_pct × dias_extras/365
  valor_de_esperar    = lucro_futuro_esperado − lucro_hoje − custo_capital

`dias_extras` = dias de espera ALÉM do ciclo operacional (~24d): o custo de
capital do ciclo normal é comum a vender-imediato e a segurar, então cancela
na comparação e não entra.

Funções PURAS: tudo entra por parâmetro (nada lê config/globals aqui).
"""
from __future__ import annotations


def receita_liquida_usd(venda_bruta_usd: float, net_factor: float) -> float:
    """Receita líquida em USD após o fator agregado de custos (ex.: ×0.70)."""
    return round(venda_bruta_usd * net_factor, 2)


def lucro_liquido_brl(receita_liq_usd: float, usd_brl: float,
                      preco_compra_brl: float) -> float:
    """Lucro líquido em R$: receita líquida convertida − preço de compra."""
    return round(receita_liq_usd * usd_brl - preco_compra_brl, 2)


def margem_sobre_custo(lucro_liq_brl: float, preco_compra_brl: float) -> float | None:
    """Fração lucro/custo. None no zero-guard (preço 0/malformado — nunca inventa)."""
    if not preco_compra_brl:
        return None
    return round(lucro_liq_brl / preco_compra_brl, 4)


def preco_maximo_compra_brl(venda_bruta_usd: float, net_factor: float,
                            usd_brl: float, min_margin_over_cost: float) -> float:
    """Preço máximo de compra p/ garantir a margem mínima sobre o custo."""
    receita_brl = receita_liquida_usd(venda_bruta_usd, net_factor) * usd_brl
    return round(receita_brl / (1.0 + min_margin_over_cost), 2)


def custo_capital_brl(preco_compra_brl: float, annual_cost_pct: float,
                      dias_extras: int) -> float:
    """Custo de oportunidade do capital parado pelos dias EXTRAS de hold."""
    return round(preco_compra_brl * annual_cost_pct * dias_extras / 365.0, 2)


def lucro_esperado_brl(cenarios: dict, net_factor: float, usd_brl: float,
                       preco_compra_brl: float) -> float:
    """Σ(probabilidade × lucro líquido do cenário) — FX constante (caveat doc.).

    `cenarios` = {nome: {"price_usd": float, "prob": float, ...}}.
    """
    total = 0.0
    for sc in cenarios.values():
        liq = receita_liquida_usd(sc["price_usd"], net_factor)
        total += sc["prob"] * lucro_liquido_brl(liq, usd_brl, preco_compra_brl)
    return round(total, 2)


def valor_de_esperar_brl(lucro_esperado: float, lucro_hoje: float,
                         custo_capital: float) -> float:
    """valor_de_esperar = lucro_futuro_esperado − lucro_hoje − custo_de_capital."""
    return round(lucro_esperado - lucro_hoje - custo_capital, 2)
