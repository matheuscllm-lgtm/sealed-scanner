"""Regressão de PRECISÃO do matcher (título BR -> SKU selado), em dado REAL.

`tests/fixtures/matcher_cases.json` = 56 casos rotulados extraídos de scans reais
(2026-06): 40 POSITIVOS (HIGH matches reais, cada um -> seu SKU) + 16 REJECTS
(armadilhas de precisão reais: edições JP/PT com palavra de idioma, single/SVP,
tin premium Mega Charizard/Team Rocket, battle decks, acessórios, outro jogo).

Origem (2026-06-21): construído como eval do experimento ASI-Evolve `sealed_match`.
A conclusão (eu + 2 agentes revisores) foi que a LÓGICA do matcher já está no ótimo
(baseline 1.0, sem gradiente) e o headroom estaria em DADO (vocabulário) — com risco
de FP. Em vez de evoluir, fixamos o comportamento ótimo como guarda de regressão:
qualquer mudança futura no `match_listing`/registry que introduza um falso-positivo
(casar o SKU errado = margem fantasma = capital do operador) ou perca um match
conhecido QUEBRA o CI.

Invariante DURO: **precisão = 1.0** (zero falso-positivo). Casar errado é o modo de
falha que custa dinheiro; este teste não deixa regredir.
"""
import json
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sealed_arbitrage_scanner as S  # noqa: E402

CASES = json.loads((ROOT / "tests" / "fixtures" / "matcher_cases.json").read_text(encoding="utf-8"))


def _registry():
    return S.build_registry(yaml.safe_load((ROOT / "sku_registry.yaml").read_text(encoding="utf-8")))


def _score():
    reg = _registry()
    tp = fp = fn = tn = 0
    fp_cases, fn_cases = [], []
    for c in CASES:
        got = {s.id for s in S.match_listing(c["title"], reg)}
        gold = c.get("gold")
        if gold is None:
            if got:
                fp += 1
                fp_cases.append((c["title"], got))
            else:
                tn += 1
        elif got == {gold}:
            tp += 1
        elif gold in got:          # casou o certo + extras -> não resolveu HIGH limpo
            fn += 1
            fn_cases.append((c["title"], got, gold))
        elif got:                  # casou SKU(s) errado(s)
            fp += 1
            fn += 1
            fp_cases.append((c["title"], got))
        else:
            fn += 1
            fn_cases.append((c["title"], got, gold))
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall, fp_cases, fn_cases


def test_matcher_precision_is_perfect_no_false_positive():
    """Invariante DURO: zero falso-positivo nos 56 casos reais. Um FP = casar o
    SKU errado = margem fantasma. Se este teste cair, NÃO mergear sem entender."""
    precision, _, fp_cases, _ = _score()
    assert precision == 1.0, f"FALSO-POSITIVO no matcher: {fp_cases}"


def test_matcher_recall_holds_on_known_good_matches():
    """Recall nos POSITIVOS reais: os matches HIGH conhecidos não podem sumir
    (uma mudança que pare de casar um produto real é regressão de cobertura)."""
    _, recall, _, fn_cases = _score()
    assert recall == 1.0, f"match conhecido perdido (FN): {fn_cases}"


def test_cases_fixture_is_well_formed():
    assert len(CASES) >= 50
    assert sum(1 for c in CASES if c.get("gold") is None) >= 10   # rejects (armadilhas)
    assert sum(1 for c in CASES if c.get("gold")) >= 30           # positivos
