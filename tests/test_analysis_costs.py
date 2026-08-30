"""Fórmulas financeiras da análise (modelo SIMPLIFICADO do operador) — travadas.

receita_liquida = venda_bruta × net_factor (0.70 inicial, configurável);
lucro_liquido = receita_liquida_BRL − preço_compra; preço_max = líq/1.25;
custo de capital só dos dias EXTRAS; valor_de_esperar = esperado − hoje − capital.
"""
import pytest

from lib.analysis import costs


def test_receita_liquida_fator_070():
    assert costs.receita_liquida_usd(100.0, 0.70) == 70.0


def test_receita_liquida_fator_e_configuravel_nao_hardcoded():
    assert costs.receita_liquida_usd(100.0, 0.85) == 85.0


def test_lucro_liquido_brl():
    # 70 USD líquidos × 5.0 = R$350 − compra R$300 = R$50
    assert costs.lucro_liquido_brl(70.0, 5.0, 300.0) == 50.0


def test_lucro_liquido_pode_ser_negativo():
    assert costs.lucro_liquido_brl(70.0, 5.0, 400.0) == -50.0


def test_margem_sobre_custo():
    assert costs.margem_sobre_custo(50.0, 200.0) == 0.25


def test_margem_sobre_custo_zero_guard():
    # preço 0/malformado → None (nunca inventa; nunca ZeroDivisionError)
    assert costs.margem_sobre_custo(50.0, 0.0) is None


def test_preco_maximo_compra():
    # venda 100 → líq 70 USD → R$350 / 1.25 = R$280
    assert costs.preco_maximo_compra_brl(100.0, 0.70, 5.0, 0.25) == 280.0


def test_custo_capital_so_dias_extras():
    # 15% a.a. sobre R$365 por 30 dias extras = R$4.50
    assert costs.custo_capital_brl(365.0, 0.15, 30) == 4.5
    assert costs.custo_capital_brl(365.0, 0.15, 0) == 0.0


def test_lucro_esperado_soma_ponderada():
    cen = {"pessimista": {"price_usd": 50.0, "prob": 0.25},
           "base": {"price_usd": 60.0, "prob": 0.50},
           "otimista": {"price_usd": 70.0, "prob": 0.25}}
    # lucro(p) = p×0.7×5 − 100 → 75/110/145; esperado = 0.25·75+0.5·110+0.25·145
    assert costs.lucro_esperado_brl(cen, 0.70, 5.0, 100.0) == pytest.approx(110.0)


def test_valor_de_esperar():
    assert costs.valor_de_esperar_brl(110.0, 80.0, 10.0) == 20.0
    assert costs.valor_de_esperar_brl(80.0, 110.0, 10.0) == -40.0
