"""`build_ebay_reference.py` — builder da referência do lado de VENDA (eBay US).

Trava os contratos de honestidade:
  - gate de título estrito (termos do registry + não-EN + graded + aberto/usado
    EN + lote/case) — precisão > cobertura;
  - guard de anúncio-lixo (< 50% da ref TCG): contado, NUNCA vencedor;
  - vencedor = MENOR anúncio plausível; sem plausível = status explícito;
  - run degradado (sem chaves) retorna 0 e PRESERVA o arquivo anterior byte a
    byte (nunca sobrescrever a última referência real com vazio "verde");
  - maioria de erros → aborta SEM gravar (exit 1);
  - schema do JSON de saída (o contrato lido pelo pipeline/snapshot).
100% offline (cliente fake / env limpo).
"""
import json

import build_ebay_reference as B
import sealed_arbitrage_scanner as S

SKU_BOX = S.Sku(
    id="ssp-booster-box-en",
    name="Surging Sparks Booster Box (English)",
    product_type="Booster Box",
    set_name="Surging Sparks",
    language="EN",
    set_terms=["surging sparks"],
    type_terms=["booster box"],
    exclude_terms=["elite trainer", "etb"],
    requires_terms=[],
)


def _item(title, value, url="https://www.ebay.com/itm/123", currency="USD"):
    return {"title": title, "price": {"value": value, "currency": currency}, "itemWebUrl": url}


# ── query ───────────────────────────────────────────────────────────────────
def test_sku_query_strips_english_suffix_and_prefixes_game():
    q = B.sku_query(SKU_BOX, "pokemon")
    assert q == "pokemon Surging Sparks Booster Box"
    assert "(english)" not in q.lower()


# ── gate de título ──────────────────────────────────────────────────────────
def test_gate_accepts_clean_sealed_title():
    assert B.title_passes_gate("Pokemon Surging Sparks Booster Box Factory Sealed", SKU_BOX)


def test_gate_rejects_wrong_set_or_type():
    assert not B.title_passes_gate("Pokemon Stellar Crown Booster Box Sealed", SKU_BOX)
    assert not B.title_passes_gate("Pokemon Surging Sparks Booster Bundle", SKU_BOX)


def test_gate_rejects_exclude_terms():
    assert not B.title_passes_gate("Surging Sparks Elite Trainer Box + Booster Box promo", SKU_BOX)


def test_gate_rejects_non_english_and_graded():
    assert not B.title_passes_gate("Surging Sparks Booster Box Japanese", SKU_BOX)
    assert not B.title_passes_gate("Surging Sparks Booster Box + PSA 10 Pikachu", SKU_BOX)


def test_gate_rejects_opened_used_en():
    assert not B.title_passes_gate("Surging Sparks Booster Box EMPTY box only", SKU_BOX)
    assert not B.title_passes_gate("Surging Sparks Booster Box opened no packs", SKU_BOX)
    assert not B.title_passes_gate("Surging Sparks Booster Box resealed", SKU_BOX)


def test_gate_rejects_lot_case_multiunit():
    assert not B.title_passes_gate("Lot of 4 Surging Sparks Booster Box", SKU_BOX)
    assert not B.title_passes_gate("2x Surging Sparks Booster Box", SKU_BOX)
    assert not B.title_passes_gate("Surging Sparks Booster Box x2 sealed", SKU_BOX)
    assert not B.title_passes_gate("Surging Sparks Booster Box CASE (6 boxes)", SKU_BOX)
    assert not B.title_passes_gate("Set of 3 Surging Sparks Booster Box", SKU_BOX)


def test_lot_regex_does_not_hit_plain_bundle():
    # "Booster Bundle" é produto legítimo — só "bundle of" é lote.
    assert B.LOT_CASE_RE.search("pokemon surging sparks booster bundle") is None
    assert B.LOT_CASE_RE.search("bundle of 3 surging sparks") is not None


def test_gate_rejects_digital_code_cards():
    # Classe observada AO VIVO (validação 2026-08-03): code cards digitais a
    # US$0,99 citam set+tipo no título e NÃO podem virar referência de venda.
    assert not B.title_passes_gate(
        "Pokemon Surging Sparks Booster Box Code Card E-Delivery!", SKU_BOX)
    assert not B.title_passes_gate(
        "Pokemon TCG Online Code Card Surging Sparks Booster Box", SKU_BOX)
    assert not B.title_passes_gate(
        "Surging Sparks Booster Box code cards digital delivery", SKU_BOX)
    assert not B.title_passes_gate(
        "Surging Sparks Booster Box PTCGL online code instant", SKU_BOX)
    # Título físico limpo continua passando (guard não pode custar cobertura).
    assert B.title_passes_gate(
        "Pokemon Surging Sparks Booster Box Factory Sealed", SKU_BOX)


# ── seleção do vencedor ─────────────────────────────────────────────────────
def test_select_lowest_junk_is_counted_never_winner():
    items = [
        _item("Pokemon Surging Sparks Booster Box Sealed", "100.00"),   # < 50% de 300 → lixo
        _item("Pokemon Surging Sparks Booster Box Sealed", "289.99"),
        _item("Pokemon Surging Sparks Booster Box Sealed", "310.00"),
    ]
    entry = B.select_lowest(SKU_BOX, items, ref_usd=300.0)
    assert entry["status"] == "ok"
    assert entry["usd"] == 289.99
    assert entry["junk_skipped"] == 1
    assert entry["url"]


def test_select_lowest_all_junk_is_explicit_status():
    items = [
        _item("Pokemon Surging Sparks Booster Box Sealed", "10.00"),
        _item("Pokemon Surging Sparks Booster Box Sealed", "20.00"),
    ]
    entry = B.select_lowest(SKU_BOX, items, ref_usd=300.0)
    assert entry["status"] == "só anúncios-lixo (2 < 50% da ref)"
    assert "usd" not in entry


def test_select_lowest_no_plausible_listing():
    items = [_item("Stellar Crown Booster Box", "200.00")]  # set errado → gate barra
    assert B.select_lowest(SKU_BOX, items, ref_usd=300.0)["status"] == "sem anúncio plausível"


def test_select_lowest_without_ref_disables_junk_guard():
    # Sem referência TCG não há como julgar "lixo" — guard desligado, honesto.
    items = [_item("Pokemon Surging Sparks Booster Box Sealed", "100.00")]
    entry = B.select_lowest(SKU_BOX, items, ref_usd=None)
    assert entry["status"] == "ok" and entry["usd"] == 100.0


def test_select_lowest_skips_non_usd_and_bad_price():
    items = [
        _item("Pokemon Surging Sparks Booster Box Sealed", "150.00", currency="EUR"),
        _item("Pokemon Surging Sparks Booster Box Sealed", None),
        _item("Pokemon Surging Sparks Booster Box Sealed", "0"),
    ]
    assert B.select_lowest(SKU_BOX, items, ref_usd=None)["status"] == "sem anúncio plausível"


# ── build_reference (cliente fake) ──────────────────────────────────────────
class _FakeClient:
    configured = True

    def __init__(self, items=None, raise_exc=None):
        self._items = items or []
        self._raise = raise_exc
        self.queries: list[str] = []

    def search(self, query, **kw):
        self.queries.append(query)
        if self._raise:
            raise self._raise
        return self._items


def test_build_reference_ok_and_error_paths():
    ok_client = _FakeClient([_item("Pokemon Surging Sparks Booster Box Sealed", "289.99")])
    entries, counts = B.build_reference([SKU_BOX], {"ssp-booster-box-en": 300.0},
                                        ok_client, "pokemon")
    assert counts == {"ok": 1, "sem_anuncio": 0, "so_lixo": 0, "erro": 0}
    assert entries["ssp-booster-box-en"]["usd"] == 289.99
    assert entries["ssp-booster-box-en"]["query"] == "pokemon Surging Sparks Booster Box"

    err_client = _FakeClient(raise_exc=RuntimeError("boom"))
    entries, counts = B.build_reference([SKU_BOX], {}, err_client, "pokemon")
    assert counts["erro"] == 1
    assert entries["ssp-booster-box-en"]["status"].startswith("erro: RuntimeError")


# ── escrita/schema ──────────────────────────────────────────────────────────
def test_write_reference_schema(tmp_path):
    out = tmp_path / "ebay_reference.json"
    entries = {"ssp-booster-box-en": {"usd": 289.99, "url": "https://www.ebay.com/itm/1",
                                      "status": "ok", "junk_skipped": 0, "query": "q"}}
    counts = {"ok": 1, "sem_anuncio": 0, "so_lixo": 0, "erro": 0}
    B.write_reference(out, entries, counts)
    data = json.loads(out.read_text(encoding="utf-8"))
    for key in ("_comment", "reference", "marketplace", "currency",
                "captured_at", "counts", "entries"):
        assert key in data, key
    assert data["reference"] == "eBay US menor anúncio ativo (Browse API)"
    assert data["marketplace"] == "EBAY_US"
    assert data["currency"] == "USD"
    assert "pedida" in data["_comment"].lower()          # rótulo de honestidade
    assert data["entries"]["ssp-booster-box-en"]["usd"] == 289.99


# ── degradação honesta ──────────────────────────────────────────────────────
def test_degraded_run_without_keys_preserves_previous_file(tmp_path, monkeypatch):
    out = tmp_path / "ebay_reference.json"
    out.write_text('{"previous": true}', encoding="utf-8")
    before = out.read_bytes()
    monkeypatch.setattr(B, "load_dotenv_if_present", lambda *a, **k: None)
    monkeypatch.delenv("EBAY_CLIENT_ID", raising=False)
    monkeypatch.delenv("EBAY_CLIENT_SECRET", raising=False)
    rc = B.main(["--output", str(out)])
    assert rc == 0                          # degradado não é falha do pipeline
    assert out.read_bytes() == before       # arquivo anterior INTOCADO


def test_majority_errors_aborts_without_writing(tmp_path, monkeypatch):
    registry = tmp_path / "reg.yaml"
    registry.write_text(
        "skus:\n"
        "- id: t1\n"
        "  name: Test Box\n"
        "  product_type: Booster Box\n"
        "  set: T\n"
        "  match: {set_terms: [test], type_terms: [booster box], exclude_terms: []}\n",
        encoding="utf-8",
    )
    out = tmp_path / "ebay_reference.json"
    out.write_text('{"previous": true}', encoding="utf-8")
    before = out.read_bytes()
    monkeypatch.setattr(B, "load_dotenv_if_present", lambda *a, **k: None)
    monkeypatch.setattr(B, "EbayClient",
                        lambda *a, **k: _FakeClient(raise_exc=RuntimeError("api caiu")))
    rc = B.main(["--registry", str(registry), "--output", str(out),
                 "--us-reference", str(tmp_path / "nao_existe.json")])
    assert rc == 1                          # maioria de erros = falha real
    assert out.read_bytes() == before       # e NADA foi gravado por cima
