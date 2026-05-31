"""shipping.py — frete doméstico BR estimado.

Pool fill amortiza frete sobre qty comprada de cada vendedor. Sem isso,
vendedor com qty=1 a R$ 30 + frete R$ 30 vira preço efetivo R$ 60/unid —
o algoritmo greedy descarta esse vendedor naturalmente, mas só se o frete
estiver no modelo.

Valores default são estimativa PAC genérica (SP↔BR). Calibração real via
cotação Correios pro CEP destino do operador (Fase 5 do POOL-FILL-PLAN.md).
"""
from __future__ import annotations

__all__ = ["compute_shipping", "weight_for_sku", "DEFAULT_TABLE", "DEFAULT_WEIGHTS"]


DEFAULT_TABLE = {
    "until_500g": 22.0,
    "until_1kg":  35.0,
    "until_2kg":  45.0,
    "until_3kg":  60.0,
    "fallback_brl": 50.0,
}

DEFAULT_WEIGHTS = {
    "Booster Pack":        40,
    "Sleeved Booster":     40,
    "Booster Bundle":      500,
    "Elite Trainer Box":   1500,
    "Booster Box":         1200,
    "Collection Box":      1100,
    "Premium Collection":  800,
    "Tin":                 300,
    "Blister":             80,
    "Blister Pack":        80,
    "Battle Deck":         100,
    "Theme Deck":          100,
    "Kit":                 200,
}


def compute_shipping(weight_g: int, table: dict | None = None) -> float:
    """Devolve frete em BRL para um pacote de `weight_g` gramas.

    Tabela em faixas (default = PAC genérico). Acima de 3kg cai no fallback.
    """
    t = table or DEFAULT_TABLE
    if weight_g <= 500:
        return float(t.get("until_500g", DEFAULT_TABLE["until_500g"]))
    if weight_g <= 1000:
        return float(t.get("until_1kg", DEFAULT_TABLE["until_1kg"]))
    if weight_g <= 2000:
        return float(t.get("until_2kg", DEFAULT_TABLE["until_2kg"]))
    if weight_g <= 3000:
        return float(t.get("until_3kg", DEFAULT_TABLE["until_3kg"]))
    return float(t.get("fallback_brl", DEFAULT_TABLE["fallback_brl"]))


def weight_for_sku(sku: dict, weights_by_type: dict | None = None,
                   default: int = 500) -> int:
    """Resolve peso do SKU. Hierarquia (1ª que matar):
      1) sku['peso_g']                    — override per-SKU (raro)
      2) weights_by_type[product_type]    — lookup por tipo (caminho normal)
      3) default                          — fallback pra tipos não mapeados
    """
    if "peso_g" in sku and sku["peso_g"]:
        return int(sku["peso_g"])
    w = weights_by_type or DEFAULT_WEIGHTS
    return int(w.get(sku.get("product_type", ""), default))


def shipping_for_sku(sku: dict, config_frete: dict | None = None) -> float:
    """Conveniência: peso → frete pra um SKU usando a config completa."""
    cfg = config_frete or {}
    weights = cfg.get("weights_g_by_type") or DEFAULT_WEIGHTS
    table = cfg.get("estimado_brl") or DEFAULT_TABLE
    # Inclui fallback_brl se config tiver
    if "fallback_brl" in cfg:
        table = {**table, "fallback_brl": cfg["fallback_brl"]}
    weight = weight_for_sku(sku, weights)
    return compute_shipping(weight, table)
