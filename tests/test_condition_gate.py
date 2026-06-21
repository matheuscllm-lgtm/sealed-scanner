"""Gate de CONDIÇÃO (selado vs aberto/usado) — guard FP-safe (parecer revisor 2026-06-21).

Até 2026-06-21 o scanner NÃO distinguia selado de aberto/usado — só funcionava
porque Liga/OLX/ML são "new-first". Um box aberto/sem cartas casado a um SKU selado
= margem fantasma. Dois níveis:

1. GLOBAL (todas as fontes): título com sinal explícito de aberto/usado/incompleto
   ("aberto", "sem cartas", "só a caixa", "vazio"...) -> 0 candidatos. Validado
   zero-regressão (0 de 818 matches reais têm esses tokens).
2. POR-FONTE (`sealed_only`, ex.: Enjoei secondhand): exige PROVA de lacre
   ("lacrado"/"selado"/"sealed") — "usado até provar lacre". Fontes new-first não
   exigem (default inalterado).
"""
import pathlib
import sys

import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import sealed_arbitrage_scanner as S  # noqa: E402


def _registry():
    return S.build_registry(yaml.safe_load((ROOT / "sku_registry.yaml").read_text(encoding="utf-8")))


# ── guards isolados ────────────────────────────────────────────────────────
def test_looks_used_flags_open_used_incomplete():
    for t in [
        "Booster Box Stellar Crown ABERTO sem cartas",
        "ETB Journey Together usado",
        "Mini Tin Mega Evolution vazia só a caixa",
        "Booster Box Chaos Rising incompleto sem boosters",
    ]:
        assert S.looks_used(t), t


def test_looks_used_does_not_flag_sealed_or_neutral():
    for t in [
        "(ING) Booster Box - Megaevolução 4 - Chaos Rising (English)",
        "Booster Box Stellar Crown lacrado",
        "Elite Trainer Box Journey Together English",
    ]:
        assert not S.looks_used(t), t


def test_looks_sealed_requires_explicit_proof():
    assert S.looks_sealed("Booster Box Chaos Rising LACRADO")
    assert S.looks_sealed("Booster Box 151 sealed")
    assert not S.looks_sealed("Booster Box Chaos Rising")   # neutro != provado


# ── gate GLOBAL: aberto/usado nunca casa (qualquer fonte) ──────────────────
def test_open_used_listing_never_matches_any_source():
    reg = _registry()
    # título que SEM o sinal de usado casaria cr-box-en:
    assert S.match_listing("(ING) Booster Box - Chaos Rising (English)", reg)  # controle: casa
    # com sinal de aberto/usado -> 0 candidatos
    assert S.match_listing("(ING) Booster Box - Chaos Rising (English) ABERTO sem cartas", reg) == []
    assert S.match_listing("Booster Box Chaos Rising inglês usado", reg) == []


# ── gate POR-FONTE: sealed_only exige prova de lacre ───────────────────────
def test_sealed_only_source_requires_sealed_token():
    reg = _registry()
    title = "Booster Box Chaos Rising inglês"   # casaria new-first, mas sem prova de lacre
    assert S.match_listing(title, reg, sealed_only=False)             # new-first: casa
    assert S.match_listing(title, reg, sealed_only=True) == []         # secondhand: barra
    # com prova de lacre, casa também na fonte sealed_only
    assert S.match_listing(title + " lacrado", reg, sealed_only=True)


def test_sealed_only_still_rejects_used_even_with_sealed_word():
    reg = _registry()
    # contradição: diz "lacrado" mas também "sem cartas" -> usado vence, rejeita
    assert S.match_listing("Booster Box Chaos Rising lacrado porém aberto sem cartas",
                           reg, sealed_only=True) == []


def test_classify_routes_sealed_only_by_config_source():
    reg = _registry()
    cfg = yaml.safe_load((ROOT / "config.yaml").read_text(encoding="utf-8"))
    assert "enjoei" in [s.lower() for s in cfg["scope"]["sealed_only_sources"]]
    # uma fonte sealed_only sem prova de lacre -> NONE com motivo lacre_nao_confirmado
    row = S.ScanRow(listing_id="x", title_br="Booster Box Chaos Rising inglês",
                    source="enjoei", seller="v", url="u", price_brl=900.0)
    out = S.classify(row, reg, {}, cfg)
    assert out.match_confidence == "NONE"
    assert out.reject_reason == "lacre_nao_confirmado"
    # mesma listagem numa fonte new-first casa (não é NONE por lacre)
    row2 = S.ScanRow(listing_id="y", title_br="Booster Box Chaos Rising inglês",
                     source="olx", seller="v", url="u", price_brl=900.0)
    out2 = S.classify(row2, reg, {}, cfg)
    assert out2.reject_reason != "lacre_nao_confirmado"
