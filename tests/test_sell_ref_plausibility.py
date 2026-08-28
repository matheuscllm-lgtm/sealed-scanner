"""Guard de plausibilidade da referência de VENDA (modo classification_source=ebay).

Caso real que motivou o guard (operador, 2026-08-24): Illustration Box Vol. 7 —
o TCGplayer desabou de ~US$160 p/ ~US$37 (restock), mas o menor anúncio ATIVO
no eBay seguia US$78,50 (pedida órfã que não repreçou). Como o perfil One Piece
classifica pelo eBay, o scan entregou 94,3% de margem num produto cuja margem
vs TCG era NEGATIVA.

Invariantes travados:
  - guard só roda no modo classification_source=ebay E com a chave
    deal_criteria.max_sell_ref_vs_tcg_ratio setada — Pokémon (tcg) intacto;
  - pedida eBay > ratio × ref TCG:
      * margem vs TCG < min_total  -> GREEN vira RED `ref_venda_descolada_tcg`
        (padrão margem_anomala: auditável, nunca YELLOW);
      * margem vs TCG >= min_total -> continua GREEN (o deal sobrevive à
        referência conservadora), com nota no main_risk;
  - FP-safe: nunca cria deal, nunca toca YELLOW/RED nem linha sem match HIGH;
  - SKU sem preço TCG ou arquivo TCG ausente = no-op honesto (nunca inventa
    preço, nunca crash) — contado nas stats.
"""
import pathlib

import yaml

import sealed_arbitrage_scanner as S

ROOT = pathlib.Path(__file__).resolve().parents[1]
SKU_ID = "ilbox-vol7-en"


def _config_ebay(ratio=1.5):
    config = yaml.safe_load((ROOT / "config_onepiece.yaml").read_text(encoding="utf-8"))
    config["currency"]["usd_brl"] = 5.0
    if ratio is None:
        config["deal_criteria"].pop("max_sell_ref_vs_tcg_ratio", None)
    else:
        config["deal_criteria"]["max_sell_ref_vs_tcg_ratio"] = ratio
    return config


def _config_tcg():
    config = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    config["currency"]["usd_brl"] = 5.0
    config["deal_criteria"]["max_sell_ref_vs_tcg_ratio"] = 1.5
    return config


def _green_row(price_brl=208.0, ebay_usd=78.5):
    """Linha GREEN como sai do classify() no modo eBay: us_price_usd = pedida eBay."""
    ebay_brl = ebay_usd * 5.0
    margin = (ebay_brl - price_brl) / price_brl
    return S.ScanRow(
        listing_id="r1", title_br="(ING) Caixa Colecionável - Illustration Box Vol.7",
        source="liga", seller="v", url="u", price_brl=price_brl,
        sku_id=SKU_ID, sku_name="One Piece Card Game Illustration Box Vol. 7",
        match_confidence="HIGH", deal_confidence="GREEN",
        bucket="real_opportunities", main_risk="risco X",
        recommended_action="ação Y",
        us_price_usd=ebay_usd, us_price_brl=ebay_brl,
        total_margin_pct=round(margin, 4),
    )


# ── caso IB-07: pedida descolada e margem vs TCG reprovada -> RED ────────────
def test_descolada_e_margem_tcg_reprovada_vira_red():
    row = _green_row(price_brl=208.0, ebay_usd=78.5)   # eBay R$392,50 = 88,7%
    stats = S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 38.01}, _config_ebay())
    # 78.5/38.01 = 2.07 > 1.5; vs TCG: R$190,05 vs R$208 = -8,6% < 30%
    assert row.deal_confidence == "RED"
    assert row.bucket == "rejected"
    assert row.reject_reason == "ref_venda_descolada_tcg"
    assert "78.5" in row.main_risk.replace(",", ".")
    assert "38.01" in row.main_risk.replace(",", ".")
    assert stats["downgraded"] == 1


def test_descolada_mas_margem_tcg_aprovada_segue_green_com_nota():
    # eBay 2x o TCG, mas mesmo pelo TCG a margem passa: TCG US$100 -> R$500 vs
    # R$300 = 66,7% >= 30%. Deal sobrevive à referência conservadora.
    row = _green_row(price_brl=300.0, ebay_usd=200.0)
    main_risk_antes = row.main_risk
    stats = S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 100.0}, _config_ebay())
    assert row.deal_confidence == "GREEN"
    assert row.bucket == "real_opportunities"
    assert row.reject_reason == ""
    assert main_risk_antes in row.main_risk          # nota ANEXA, não substitui
    assert "descolada" in row.main_risk.lower()
    assert stats["kept_with_note"] == 1


def test_ratio_dentro_do_limite_nao_toca_na_linha():
    row = _green_row(price_brl=208.0, ebay_usd=50.0)
    stats = S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 38.01}, _config_ebay())
    assert row.deal_confidence == "GREEN"
    assert row.main_risk == "risco X"
    assert stats["downgraded"] == 0


# ── FP-safe: nunca cria deal, nunca toca YELLOW/RED/sem-HIGH ─────────────────
def test_yellow_red_e_sem_match_ficam_intactos():
    yellow = _green_row()
    yellow.deal_confidence, yellow.bucket = "YELLOW", "review_required"
    red = _green_row()
    red.deal_confidence, red.bucket, red.reject_reason = "RED", "rejected", "margem_total_abaixo_do_minimo"
    none_match = _green_row()
    none_match.match_confidence, none_match.sku_id = "NONE", ""
    rows = [yellow, red, none_match]
    S.apply_sell_ref_plausibility_guard(rows, {SKU_ID: 38.01}, _config_ebay())
    assert yellow.deal_confidence == "YELLOW"
    assert red.reject_reason == "margem_total_abaixo_do_minimo"
    assert none_match.deal_confidence == "GREEN"     # sem sku_id -> não avaliado


def test_sku_sem_preco_tcg_fica_intacto_e_contado():
    row = _green_row()
    stats = S.apply_sell_ref_plausibility_guard([row], {"outro-sku": 38.01}, _config_ebay())
    assert row.deal_confidence == "GREEN"
    assert stats["sem_tcg"] == 1


# ── desligado: modo tcg, chave ausente, ou sem preços TCG ────────────────────
def test_guard_inativo_no_modo_tcg():
    row = _green_row()
    stats = S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 38.01}, _config_tcg())
    assert stats is None
    assert row.deal_confidence == "GREEN"


def test_guard_inativo_sem_chave_de_ratio():
    row = _green_row()
    stats = S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 38.01}, _config_ebay(ratio=None))
    assert stats is None
    assert row.deal_confidence == "GREEN"


def test_guard_inativo_sem_precos_tcg():
    row = _green_row()
    assert S.apply_sell_ref_plausibility_guard([row], {}, _config_ebay()) is None
    assert S.apply_sell_ref_plausibility_guard([row], None, _config_ebay()) is None
    assert row.deal_confidence == "GREEN"


# ── ordem: descolada -> RED vence o freshness (stale -> YELLOW) ──────────────
def test_descolada_vira_red_mesmo_com_referencia_velha():
    row = _green_row(price_brl=208.0, ebay_usd=78.5)
    config = _config_ebay()
    S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 38.01}, config)
    # freshness roda DEPOIS e só toca GREEN — o RED do guard permanece.
    S.apply_freshness_downgrade([row], {"captured_at": "2020-01-01T00:00:00Z"}, config)
    assert row.deal_confidence == "RED"
    assert row.reject_reason == "ref_venda_descolada_tcg"


# ── wrapper de produção: carrega o us_file e aplica (caminho dos 2 runners) ──
def test_wrapper_aplica_guard_com_arquivo_presente(tmp_path):
    import json
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "us_ref.json").write_text(
        json.dumps({"captured_at": "2099-01-01T00:00:00Z",
                    "prices": {SKU_ID: 38.01}}), encoding="utf-8")
    config = _config_ebay()
    config["references"]["us_file"] = "data/us_ref.json"
    row = _green_row(price_brl=208.0, ebay_usd=78.5)
    stats = S.load_and_apply_sell_ref_guard([row], config, tmp_path)
    assert stats is not None and stats["downgraded"] == 1
    assert row.reject_reason == "ref_venda_descolada_tcg"


def test_wrapper_arquivo_ausente_e_noop_honesto_sem_crash(tmp_path):
    config = _config_ebay()
    config["references"]["us_file"] = "data/nao_existe.json"
    row = _green_row(price_brl=208.0, ebay_usd=78.5)
    stats = S.load_and_apply_sell_ref_guard([row], config, tmp_path)
    assert stats is None                      # guard pulado, nunca crash
    assert row.deal_confidence == "GREEN"     # linha intacta (nunca inventa preço)


def test_wrapper_inativo_no_modo_tcg(tmp_path):
    row = _green_row()
    assert S.load_and_apply_sell_ref_guard([row], _config_tcg(), tmp_path) is None
    assert row.deal_confidence == "GREEN"


# ── fronteiras exatas (review 2026-08-28: travar o <= e o >= em teste) ───────
def test_fronteira_pedida_exatamente_no_ratio_nao_toca():
    # us_price_usd == ratio × tcg (78.0 == 1.5 × 52.0): condição usa <= — linha
    # intacta, mas CONTADA em checked (semântica: checked = todas avaliadas).
    row = _green_row(price_brl=208.0, ebay_usd=78.0)
    stats = S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 52.0}, _config_ebay())
    assert row.deal_confidence == "GREEN"
    assert row.main_risk == "risco X"
    assert stats == {"checked": 1, "downgraded": 0, "kept_with_note": 0, "sem_tcg": 0}


def test_fronteira_margem_tcg_exatamente_no_minimo_segue_green():
    # margem vs TCG == min_total (0.30 exato: R$100 -> TCG US$26×5 = R$130):
    # branch usa >= — GREEN sobrevive com nota, nunca RED.
    row = _green_row(price_brl=100.0, ebay_usd=60.0)   # 60 > 1.5×26 = 39
    stats = S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 26.0}, _config_ebay())
    assert row.deal_confidence == "GREEN"
    assert "descolada" in row.main_risk.lower()
    assert stats["kept_with_note"] == 1 and stats["downgraded"] == 0


def test_tcg_preco_zero_tratado_como_sem_preco():
    # Preço 0 no snapshot TCG = dado inválido, não referência: cai em sem_tcg
    # e a linha fica intacta (nunca divide por zero, nunca rebaixa).
    row = _green_row()
    stats = S.apply_sell_ref_plausibility_guard([row], {SKU_ID: 0}, _config_ebay())
    assert row.deal_confidence == "GREEN"
    assert stats["sem_tcg"] == 1 and stats["checked"] == 0


# ── frescor do próprio us_file (review 2026-08-28, finding MEDIUM) ───────────
def test_wrapper_us_file_defasado_pula_guard_sem_rebaixar(tmp_path):
    import json
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "us_ref.json").write_text(
        json.dumps({"captured_at": "2020-01-01T00:00:00Z",
                    "prices": {SKU_ID: 38.01}}), encoding="utf-8")
    config = _config_ebay()                      # OP: max_reference_age_days = 1
    config["references"]["us_file"] = "data/us_ref.json"
    row = _green_row(price_brl=208.0, ebay_usd=78.5)
    stats = S.load_and_apply_sell_ref_guard([row], config, tmp_path)
    assert stats is None                         # guard PULADO (ref de sanidade velha)
    assert row.deal_confidence == "GREEN"        # nunca rebaixa com snapshot velho


def test_wrapper_us_file_sem_captured_at_ainda_aplica(tmp_path):
    # Idade desconhecida (sem captured_at) segue a leniência do freshness
    # downgrade: não bloqueia — o guard aplica normalmente.
    import json
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "us_ref.json").write_text(
        json.dumps({"prices": {SKU_ID: 38.01}}), encoding="utf-8")
    config = _config_ebay()
    config["references"]["us_file"] = "data/us_ref.json"
    row = _green_row(price_brl=208.0, ebay_usd=78.5)
    stats = S.load_and_apply_sell_ref_guard([row], config, tmp_path)
    assert stats is not None and stats["downgraded"] == 1
    assert row.reject_reason == "ref_venda_descolada_tcg"


# ── config do perfil OP já vem com o guard ligado ────────────────────────────
def test_config_onepiece_tem_ratio_default():
    config = yaml.safe_load((ROOT / "config_onepiece.yaml").read_text(encoding="utf-8"))
    ratio = config["deal_criteria"].get("max_sell_ref_vs_tcg_ratio")
    assert ratio is not None and 1.0 < float(ratio) <= 3.0
