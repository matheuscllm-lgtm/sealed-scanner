"""Fix 2026-07-03 — ETBs de Forças Temporais: MULTI em título genérico + PT invisível.

Bug (achado em auditoria sistemática de pares (set, product_type)): os dois ETBs
do TEF distinguiam a variante por type_terms ("walking wake"/"iron leaves" como
type_term é OR, não AND) → título SEM variante ("Elite Trainer Box - Forças
Temporais") casava AMBOS = YELLOW ambíguo; e faltava o termo PT "coleção
treinador avançado" (mesma classe do bug ME05/PR #51) → título PT invisível.

Fix (padrão auditado da frota, mesmo do asc-mini-tin): variante fixada por
`requires_terms` + fallback genérico `tef-etb-en` apontando pra variante mais
barata COM preço (Iron Leaves 532848, $131.24 vs WW $132.36 — dispersão 0.9%)
com excludes fechados das 2 variantes. A auditoria confirmou que TEF era o
ÚNICO par do registry com esse defeito.
"""
import pathlib

import pytest
import yaml

import sealed_arbitrage_scanner as S

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "sku_registry.yaml"


@pytest.fixture(scope="module")
def registry():
    return S.build_registry(yaml.safe_load(REGISTRY.read_text(encoding="utf-8")))


def ids(title, reg):
    return sorted(s.id for s in S.match_listing(title, reg))


@pytest.mark.parametrize("titulo,esperado", [
    # variante nomeada -> SKU da variante (nunca o genérico, nunca MULTI)
    ("Elite Trainer Box - Forças Temporais - Walking Wake", ["tef-etb-ww-en"]),
    ("Elite Trainer Box - Forças Temporais - Iron Leaves", ["tef-etb-il-en"]),
    ("Temporal Forces Elite Trainer Box [Walking Wake] (English)", ["tef-etb-ww-en"]),
    ("Coleção Treinador Avançado - Forças Temporais - Walking Wake", ["tef-etb-ww-en"]),
    # título SEM variante -> fallback genérico (antes: MULTI = YELLOW ambíguo)
    ("Elite Trainer Box - Forças Temporais", ["tef-etb-en"]),
    ("Temporal Forces Elite Trainer Box (English)", ["tef-etb-en"]),
    # título PT recuperado (antes: invisível, sem_match)
    ("Coleção Treinador Avançado - Forças Temporais", ["tef-etb-en"]),
    # vizinhos intactos
    ("Booster Bundle - Forças Temporais", ["tef-bundle-en"]),
    ("Booster Avulso - Forças Temporais", ["tef-pack-en"]),
    # idioma barrado
    ("Elite Trainer Box - Forças Temporais Japonês", []),
])
def test_tef_etb_resolve_unico(registry, titulo, esperado):
    assert ids(titulo, registry) == esperado


def test_nenhum_par_do_registry_multi_em_titulo_generico(registry):
    """Auditoria travada em teste: para todo grupo (set, product_type) com >1 SKU,
    um título sintético '<type_term> - <set_term>' (sem variante) casa no máximo
    1 SKU. Era exatamente o defeito dos ETBs do TEF."""
    from collections import defaultdict
    data = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))
    groups = defaultdict(list)
    for s in data["skus"]:
        groups[(s["set"], s["product_type"])].append(s)
    erros = []
    for (_, _), skus in sorted(groups.items()):
        if len(skus) < 2:
            continue
        for sku in skus:
            for setterm in sku["match"]["set_terms"][:2]:
                for typeterm in sku["match"]["type_terms"][:3]:
                    title = f"{typeterm} - {setterm}"
                    got = ids(title, registry)
                    if len(got) > 1:
                        erros.append(f"{title!r} -> {got}")
    assert not erros, "\n".join(sorted(set(erros)))
