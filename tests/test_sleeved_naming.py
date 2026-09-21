"""Termo "Sleeved" honesto no registry (operador, 2026-09-02, com prints da Liga):

- Liga "Blister Unitário" (cartela Copag)  = TCGplayer "<Set> Sleeved Booster Pack"
- Liga "Booster Avulso"   (pacote solto)   = TCGplayer "<Set> Booster Pack"

Regra travada aqui: o `name` de um SKU de pacote contém "Sleeved" **se e
somente se** o `tcgplayer_product_id` é o produto Sleeved real do tcgcsv.
Antes: os 6 *-blister-1pack apontavam certo (Sleeved) mas se chamavam
"Single Pack Blister"; 8 SKUs chamados "Sleeved Booster" apontavam para o
pacote solto. Ver HANDOFF-2026-09-01-auditoria-registry-sleeved.md §5."""
import pathlib

import yaml

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "sku_registry.yaml"

# productId do "<Set> Sleeved Booster Pack" no tcgcsv (auditoria 2026-09-01/02).
SLEEVED_PIDS = {
    "jtg-blister-1pack": 610934,
    "po-blister-1pack": 672412,
    "cr-blister-1pack": 684448,
    "pb-blister-1pack": 692957,
    "phf-blister-1pack": 654145,
    "dri-blister-1pack": 624684,
}

# SKUs que apontam para o pacote SOLTO ("<Set> Booster Pack") e por isso não
# podem se chamar "Sleeved".
LOOSE_PACK_SKUS = {
    "meg-sleeved-booster": 644352,
    "par-sleeved-booster": 512822,
    "obf-sleeved-booster": 501256,
    "pal-sleeved-booster": 493976,
    "blk-sleeved-booster": 630434,
    "wht-sleeved-booster": 630699,
    "sfa-sleeved-booster": 552997,
    "paf-sleeved-en": 528038,
}

# Sets em que o tcgcsv TEM produto Sleeved separado: o SKU do pacote solto
# não pode absorver "Blister Unitário" (seria referência errada, ~30% baixa).
SETS_WITH_SEPARATE_SLEEVED = {"meg-sleeved-booster", "par-sleeved-booster",
                              "obf-sleeved-booster", "pal-sleeved-booster"}


def _by_id():
    reg = yaml.safe_load(REGISTRY.read_text(encoding="utf-8"))["skus"]
    return {s["id"]: s for s in reg}


def test_sku_com_pid_sleeved_se_chama_sleeved_booster_pack():
    skus = _by_id()
    for sid, pid in SLEEVED_PIDS.items():
        s = skus[sid]
        assert s["tcgplayer_product_id"] == pid, sid
        assert "Sleeved Booster Pack" in s["name"], (sid, s["name"])
        assert "Single Pack Blister" not in s["name"], (sid, s["name"])


def test_sku_do_pacote_solto_nao_se_chama_sleeved():
    skus = _by_id()
    for sid, pid in LOOSE_PACK_SKUS.items():
        s = skus[sid]
        assert s["tcgplayer_product_id"] == pid, sid
        assert "Sleeved" not in s["name"], (sid, s["name"])
        assert s["name"].endswith("Booster Pack (English)"), (sid, s["name"])


def test_pacote_solto_nao_absorve_blister_unitario_quando_existe_sleeved():
    skus = _by_id()
    for sid in SETS_WITH_SEPARATE_SLEEVED:
        terms = [t.lower() for t in skus[sid]["match"]["type_terms"]]
        assert not any("blister unit" in t for t in terms), (sid, terms)
