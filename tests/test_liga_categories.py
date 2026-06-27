"""Tests para a habilitação da categoria 'Latas' (categ=24) no scraper da Liga.

A categoria Latas/Tins faltava em DEFAULT_CATEGORIES, então o scan NUNCA coletava
latas seladas (ex.: Paldean Fates Tin [Charizard ex]). Número da categoria
confirmado por busca-alvo na Liga 2026-06-27 (breadcrumb: categ=24 -> 'Latas').
"""
import pathlib

import yaml
import pytest

import sealed_arbitrage_scanner as S
import liga_adapter as L

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "sku_registry.yaml"


@pytest.fixture(scope="module")
def registry():
    return S.build_registry(yaml.safe_load(REGISTRY.read_text(encoding="utf-8")))


def test_latas_categoria_no_scan():
    # categ=24 = "Latas" deve estar nas categorias varridas por padrão
    assert 24 in L.DEFAULT_CATEGORIES
    assert L.DEFAULT_CATEGORIES[24] == "Latas"


def test_prerelease_categoria_no_scan():
    # categ=57 = "Pacote Pré-Lançamento" (prerelease/Build & Battle Box)
    assert 57 in L.DEFAULT_CATEGORIES
    assert L.DEFAULT_CATEGORIES[57] == "Pacote Pré-Lançamento"


def test_lata_mapeia_product_type_tin():
    # título "Lata ..." da Liga -> product_type "Tin"
    assert L._name_product_type("(ING) Lata Destinos de Paldea - Charizard Shiny ex") == "Tin"


def test_lata_charizard_coletada_casa_sku(registry):
    # ponta-a-ponta: o título REAL da lata, traduzido como na coleta, casa o SKU
    raw = "(ING) Lata Destinos de Paldea - Charizard Shiny ex"
    title = L._translate_title(raw)
    matched = sorted(s.id for s in S.match_listing(title, registry))
    assert matched == ["paf-tin-charizard"]
