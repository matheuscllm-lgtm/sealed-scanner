"""Tests for sealed/lib/shipping.py."""
from sealed.lib.shipping import (
    compute_shipping, weight_for_sku, shipping_for_sku,
    DEFAULT_TABLE, DEFAULT_WEIGHTS,
)


def test_compute_shipping_default_table():
    assert compute_shipping(40) == 22.0       # pack avulso
    assert compute_shipping(500) == 22.0      # boundary inferior
    assert compute_shipping(800) == 35.0      # bundle
    assert compute_shipping(1500) == 45.0     # ETB
    assert compute_shipping(1200) == 45.0     # booster box
    assert compute_shipping(2500) == 60.0     # 2 ETBs
    assert compute_shipping(5000) == 50.0     # fallback


def test_compute_shipping_custom_table():
    table = {"until_500g": 30, "until_1kg": 50, "until_2kg": 70, "until_3kg": 90, "fallback_brl": 120}
    assert compute_shipping(100, table) == 30
    assert compute_shipping(1500, table) == 70
    assert compute_shipping(4000, table) == 120


def test_weight_for_sku_by_type():
    assert weight_for_sku({"product_type": "Booster Pack"}) == 40
    assert weight_for_sku({"product_type": "Booster Box"}) == 1200
    assert weight_for_sku({"product_type": "Elite Trainer Box"}) == 1500
    assert weight_for_sku({"product_type": "Booster Bundle"}) == 500


def test_weight_for_sku_override():
    """peso_g per-SKU sobrescreve lookup por tipo."""
    sku = {"product_type": "Booster Pack", "peso_g": 80}
    assert weight_for_sku(sku) == 80


def test_weight_for_sku_unknown_type_falls_back():
    assert weight_for_sku({"product_type": "Something Unknown"}, default=300) == 300
    assert weight_for_sku({}, default=500) == 500


def test_shipping_for_sku_covers_all_registry_types():
    """Smoke: todos product_types do registry devem retornar frete numérico."""
    types = [
        "Booster Box", "Elite Trainer Box", "Booster Bundle", "Booster Pack",
        "Sleeved Booster", "Collection Box", "Premium Collection",
        "Tin", "Blister", "Blister Pack", "Battle Deck", "Theme Deck", "Kit",
    ]
    for t in types:
        result = shipping_for_sku({"product_type": t})
        assert isinstance(result, float)
        assert result > 0


def test_shipping_for_sku_with_full_config():
    """Sanity: shipping_for_sku integra weights_g_by_type + estimado_brl."""
    cfg = {
        "weights_g_by_type": {"Booster Box": 1500},
        "estimado_brl": {"until_2kg": 100, "until_500g": 10, "until_1kg": 20, "until_3kg": 200},
        "fallback_brl": 999,
    }
    assert shipping_for_sku({"product_type": "Booster Box"}, cfg) == 100
