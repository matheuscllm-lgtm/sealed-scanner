"""`build_us_reference.py` multi-jogo (--game / --category-id / --bands).

Trava:
  - o perfil One Piece usa a categoria tcgcsv 68 (catálogo EN — a MESMA do
    op_scanner da frota) e o default continua Pokémon = 3;
  - `SANITY_BANDS_USD` (Pokémon) é o MESMO objeto de sempre (conteúdo já
    travado em test_reference_guards.py) — as bandas OP são um dict NOVO;
  - as bandas OP cobrem preços reais verificados (OP16 Booster Box US$204,70).
100% offline (fetch_json monkeypatchado).
"""
import json

import build_us_reference as B


def _registry(tmp_path, product_type="Booster Box"):
    p = tmp_path / "reg.yaml"
    p.write_text(
        "skus:\n"
        "- id: t1\n"
        "  name: Test Box\n"
        f"  product_type: {product_type}\n"
        "  set: T\n"
        "  tcgplayer_group_id: 555\n"
        "  tcgplayer_product_id: 777\n"
        "  match: {set_terms: [test], type_terms: [booster box], exclude_terms: []}\n",
        encoding="utf-8",
    )
    return p


def _fake_fetch(seen):
    def fetch(url):
        seen.append(url)
        return {"results": [{"productId": 777, "subTypeName": "Normal", "marketPrice": 204.70}]}
    return fetch


def test_default_game_hits_pokemon_category_3(tmp_path, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(B, "fetch_json", _fake_fetch(seen))
    out = tmp_path / "ref.json"
    rc = B.main(["--registry", str(_registry(tmp_path)), "--output", str(out)])
    assert rc == 0
    assert "/tcgplayer/3/555/prices" in seen[0]
    assert json.loads(out.read_text(encoding="utf-8"))["prices"]["t1"] == 204.70


def test_game_onepiece_hits_category_68_and_op_bands(tmp_path, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(B, "fetch_json", _fake_fetch(seen))
    out = tmp_path / "ref_op.json"
    rc = B.main(["--game", "onepiece",
                 "--registry", str(_registry(tmp_path)), "--output", str(out)])
    assert rc == 0
    assert "/tcgplayer/68/555/prices" in seen[0]
    assert json.loads(out.read_text(encoding="utf-8"))["prices"]["t1"] == 204.70


def test_explicit_category_id_overrides_profile(tmp_path, monkeypatch):
    seen: list[str] = []
    monkeypatch.setattr(B, "fetch_json", _fake_fetch(seen))
    rc = B.main(["--category-id", "80",
                 "--registry", str(_registry(tmp_path)),
                 "--output", str(tmp_path / "x.json")])
    assert rc == 0
    assert "/tcgplayer/80/555/prices" in seen[0]


def test_op_bands_guard_excludes_out_of_band(tmp_path, monkeypatch):
    # Booster Box OP a US$5 (fora da banda 40–1500) = pid trocado → EXCLUÍDO.
    def fetch(url):
        return {"results": [{"productId": 777, "subTypeName": "Normal", "marketPrice": 5.0}]}
    monkeypatch.setattr(B, "fetch_json", fetch)
    out = tmp_path / "ref_op.json"
    rc = B.main(["--game", "onepiece",
                 "--registry", str(_registry(tmp_path)), "--output", str(out)])
    assert rc == 0
    assert json.loads(out.read_text(encoding="utf-8"))["prices"] == {}


def test_bands_registry_identity_and_op_coverage():
    # Objeto Pokémon inalterado (conteúdo travado em test_reference_guards).
    assert B.BANDS_BY_GAME["pokemon"] is B.SANITY_BANDS_USD
    assert B.GAME_PROFILES["pokemon"]["category_id"] == 3
    assert B.GAME_PROFILES["onepiece"]["category_id"] == 68
    # Preço real verificado (tcgcsv 2026-08): OP16 box US$204,70 dentro da banda.
    lo, hi = B.SANITY_BANDS_USD_ONEPIECE["Booster Box"]
    assert lo <= 204.70 <= hi
    # Todo tipo do perfil OP tem banda (fail-open zero p/ os tipos do seed).
    for t in ("Booster Pack", "Sleeved Booster Pack", "Double Pack Set",
              "Starter Deck", "Starter Deck Display", "Extra Booster Box"):
        assert t in B.SANITY_BANDS_USD_ONEPIECE
