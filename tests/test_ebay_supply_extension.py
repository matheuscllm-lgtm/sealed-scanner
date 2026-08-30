"""Extensão ADITIVA do build_ebay_reference: campos de oferta (active_count/
sellers/ladder_usd) quando o cliente expõe search_page; fakes antigos (só
`search`) continuam funcionando SEM os campos — nada do contrato muda."""
from types import SimpleNamespace

import build_ebay_reference as B


def _sku():
    return SimpleNamespace(id="ssp-etb-en", name="Surging Sparks Elite Trainer Box",
                           product_type="Elite Trainer Box",
                           set_terms=["surging sparks"], type_terms=["elite trainer"],
                           exclude_terms=[], requires_terms=[])


ITEMS = [
    {"title": "Pokemon Surging Sparks Elite Trainer Box Sealed",
     "itemWebUrl": "https://www.ebay.com/itm/1", "price": {"value": "45.0", "currency": "USD"},
     "seller": {"username": "loja1"}},
    {"title": "Pokemon Surging Sparks Elite Trainer Box New",
     "itemWebUrl": "https://www.ebay.com/itm/2", "price": {"value": "49.0", "currency": "USD"},
     "seller": {"username": "loja2"}},
    {"title": "Japanese Surging Sparks Elite Trainer Box",   # barrado pelo gate
     "itemWebUrl": "https://www.ebay.com/itm/3", "price": {"value": "30.0", "currency": "USD"},
     "seller": {"username": "loja3"}},
]


class NewClient:
    def search_page(self, query, **kw):
        return {"itemSummaries": ITEMS, "total": 37}


class OldClient:
    def search(self, query, **kw):
        return ITEMS


def test_client_novo_ganha_campos_de_oferta():
    entries, counts = B.build_reference([_sku()], {"ssp-etb-en": 60.0},
                                        NewClient(), "pokemon")
    e = entries["ssp-etb-en"]
    assert e["status"] == "ok" and e["usd"] == 45.0     # contrato original intacto
    assert e["active_count"] == 37
    assert e["ladder_usd"] == [45.0, 49.0]
    assert e["sellers"] == 2


def test_fake_antigo_continua_valido_sem_campos():
    entries, counts = B.build_reference([_sku()], {"ssp-etb-en": 60.0},
                                        OldClient(), "pokemon")
    e = entries["ssp-etb-en"]
    assert e["status"] == "ok" and e["usd"] == 45.0
    assert "active_count" not in e                       # aditivo: só com search_page


def test_append_supply_history_por_entries(tmp_path, monkeypatch):
    from lib.analysis import history_store as store
    monkeypatch.setattr(B, "SCRIPT_DIR", B.SCRIPT_DIR)   # paths reais do config
    # roteia o arquivo de supply pro tmp monkeypatchando o resolve_path usado
    import lib.analysis.profiles as prof
    real_resolve = prof.resolve_path

    def fake_resolve(root, rel):
        if "supply" in str(rel):
            return tmp_path / "supply.jsonl"
        return real_resolve(root, rel)

    monkeypatch.setattr("lib.analysis.profiles.resolve_path", fake_resolve)
    entries = {"ssp-etb-en": {"status": "ok", "usd": 45.0, "query": "q",
                              "active_count": 37, "sellers": 2,
                              "ladder_usd": [45.0, 49.0]},
               "sem-oferta": {"status": "sem anúncio plausível", "query": "q2"}}
    B._append_supply_history("pokemon", entries)
    recs, bad = store.read_records(tmp_path / "supply.jsonl")
    assert bad == 0 and len(recs) == 1
    assert recs[0]["sku_id"] == "ssp-etb-en" and recs[0]["active_count"] == 37
