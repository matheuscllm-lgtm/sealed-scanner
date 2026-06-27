"""Tests para o matcher determinístico — foco na regra `era_umbrella`.

Casos reais pegos no scan 2026-06-03 (Amazon usa "Mega Evolution - <subset>"
como prefixo de era, o que fazia os SKUs meg-* da era casarem junto com o SKU
do sub-set → REVIEW ambíguo + avaliação perdida). A regra umbrella resolve isso
genericamente: quando um SKU umbrella casa junto com um sub-set específico, o
umbrella perde.
"""
import pathlib

import yaml
import pytest

import sealed_arbitrage_scanner as S

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "sku_registry.yaml"


@pytest.fixture(scope="module")
def registry():
    return S.build_registry(yaml.safe_load(REGISTRY.read_text(encoding="utf-8")))


def ids(title, reg):
    return sorted(s.id for s in S.match_listing(title, reg))


# --- a era Mega tem 5 SKUs umbrella (o set-base) -------------------------
def test_meg_skus_flagged_umbrella(registry):
    umbrella = {s.id for s in registry if s.era_umbrella}
    assert umbrella == {
        "meg-booster-box", "meg-sleeved-booster", "meg-booster-bundle",
        "meg-mini-tin", "meg-mini-tin-display",
        # blisters 3-pack do ME01 (gap 2026-06-26) — mesmo set-base da era Mega
        "meg-blister-3pack-golduck", "meg-blister-3pack-psyduck",
        # ETBs por personagem do ME01 (gap 2026-06-27) — base da era Mega
        "meg-etb-lucario", "meg-etb-gardevoir",
        "meg-etb-pc-lucario", "meg-etb-pc-gardevoir",
    }


# --- sub-set prefixado pela era → resolve no sub-set, não no umbrella -----
@pytest.mark.parametrize("title,expected", [
    # Amazon "Mega Evolution - <subset>" (o bug que motivou a regra):
    ("Pokémon TCG: Mega Evolution—Phantasmal Flames Booster Bundle (6 Booster Packs)", "phf-bundle-en"),
    ("Pokémon TCG: Mega Evolution - Ascended Heroes - Booster Bundle - Inglês", "ah-bundle-en"),
    ("Pokemon TCG - Mega Evolution: Ascended Heroes 10-Card Booster Pack (English)", "ah-pack-en"),
    ("Pokémon TCG: Mega Evolution - Phantasmal Flames Booster Pack (10 Cards)", "phf-pack-en"),
    # Os 2 sub-sets que o band-aid antigo cobria seguem certos:
    ("Pokémon TCG: Mega Evolution - Perfect Order - Booster Bundle - Inglês", "po-bundle-en"),
    ("Pokémon TCG: Mega Evolution - Chaos Rising - Booster Bundle", "cr-bundle-en"),
])
def test_subset_beats_era_umbrella(title, expected, registry):
    assert ids(title, registry) == [expected]


# --- set-base puro (sem sub-set) → o umbrella é preservado ----------------
@pytest.mark.parametrize("title,expected", [
    ("Pokemon TCG Mega Evolution Booster Bundle Inglês", "meg-booster-bundle"),
    ("Mega Evolution Booster Box (English)", "meg-booster-box"),
])
def test_pure_base_set_keeps_umbrella(title, expected, registry):
    assert ids(title, registry) == [expected]


# --- ambiguidade legítima continua sendo REVIEW (não engolida pela regra) -
def test_legit_ambiguity_still_review(registry):
    # Anúncio nomeia os dois sets (White Flare / Black Bolt) — sem umbrella envolvido.
    dual = "Booster Avulso Fogo Branco / Raio Preto Pokémon TCG"
    assert len(S.match_listing(dual, registry)) == 2


# --- guard de carta avulsa: single NÃO casa box SKU (margem fantasma) ------
def test_single_card_nao_casa_box(registry):
    # Caso real (scan Amazon 2026-06-06): single promo cujo título cita o set E
    # "Elite Trainer Box" casava pre-etb-en → +272% fantasma. Agora: 0 candidatos.
    fantasma = "Pokemon - Eevee SVP 173 – Prismatic Evolutions – Elite Trainer Box Promo - Single Card"
    assert S.match_listing(fantasma, registry) == []


def test_selado_real_ainda_casa(registry):
    # O ETB selado de verdade do mesmo set NÃO pode ser barrado pelo guard.
    real = "Pokémon TCG Prismatic Evolutions Elite Trainer Box (English)"
    assert ids(real, registry) == ["pre-etb-en"]


def test_sealed_single_booster_pack_nao_e_barrado():
    # "single" sozinho é legítimo em selado (Sealed Single Booster Pack) — só
    # 'single card' (e afins) é single de verdade. Não pode disparar o guard.
    assert S.looks_like_single_card("Pokemon 151 - Sealed Single Booster Pack - English") is False


@pytest.mark.parametrize("title,expected", [
    ("Eevee SVP 173 Prismatic Evolutions Single Card", True),   # EN explícito
    ("Charizard SVP 044 Promo", True),                          # código SVP
    ("Pikachu 238/191 Surging Sparks", True),                   # numeração de carta
    ("Carta Avulsa Pikachu Prismatic", True),                   # PT
    ("Prismatic Evolutions Elite Trainer Box", False),          # selado
    ("Mega Evolution Booster Box", False),                      # selado
    ("Sealed Single Booster Pack 151", False),                  # 'single' ok em selado
])
def test_looks_like_single_card(title, expected):
    assert S.looks_like_single_card(title) is expected


# --- guard de acessório PURO: 'Acessórios' não casa box SKU -----------------
def test_acessorio_puro_nao_casa_box(registry):
    # Caso real (scan default 2026-06-06, ML): acessório vendido à parte casava
    # ah-etb-en (ETB real ~R$400) com R$95 → +885% fantasma.
    aces = "Elite Trainer Box - Ascended Heroes - Acessórios Inglês"
    assert S.match_listing(aces, registry) == []


def test_binder_collection_NAO_e_barrado(registry):
    # CRÍTICO: 'binder collection' é o type_term dos 4 Collection Box selados —
    # o guard de acessório NÃO pode barrá-lo (seria falso-negativo de SKU curado).
    # O "Fichário Binder +440%" do scan é bug de PREÇO do registry (mew-collection-box
    # US ref de produto caro vs type_term do binder barato), tratado fora do matcher.
    assert S.looks_like_accessory("Scarlet & Violet 151 Binder Collection") is False
    assert "mew-collection-box" in ids("Scarlet & Violet 151 Binder Collection English", registry)


def test_etb_real_nao_e_barrado_por_acessorio(registry):
    assert "ah-etb-en" in ids("Pokémon Ascended Heroes Elite Trainer Box Inglês", registry)


@pytest.mark.parametrize("title,expected", [
    ("Elite Trainer Box Acessórios", True),
    ("Porta Cartas Pokémon Toploader", True),
    ("Playmat Charizard", True),
    ("Sleeve Dragonite Etb Ascended Heroes (65 Sleeves)", True),  # pacote de sleeves = acessório
    ("Pacote 100 Sleeves Pokémon", True),
    ("Deck Protector Pikachu", True),
    ("Sleeved Booster Pack Surging Sparks", False),   # 'sleeve' é selado — NÃO barrar
    ("Booster Avulso Megaevolução", False),           # Sleeved Booster real (sem contador)
    ("Scarlet & Violet 151 Binder Collection", False),  # binder collection = selado real
    ("Prismatic Evolutions Collection Box", False),   # 'collection box' é selado
    ("Mega Evolution Booster Bundle", False),         # selado
])
def test_looks_like_accessory(title, expected):
    assert S.looks_like_accessory(title) is expected


def test_sleeve_pack_nao_casa_etb(registry):
    # Caso real (scan 2026-06-26, ML): "Sleeve Dragonite Etb Ascended Heroes
    # (65 Sleeves)" R$64,50 casava ah-etb-en e dava +1600% (margem_anomala). Pior:
    # virava a oferta de referência do grupo e escondia o ETB GREEN real da entrega.
    # O contador "65 Sleeves" é prova de pacote de protetores avulso = acessório.
    sleeve = "Sleeve Dragonite Etb Ascended Heroes (65 Sleeves)"
    assert S.looks_like_accessory(sleeve) is True
    assert S.match_listing(sleeve, registry) == []


# --- GAP fechado 2026-06-26: set ME05 com nome PT + blisters 3-pack ----------
@pytest.mark.parametrize("title,expected", [
    # ME05 a Liga chama "Escuridão Absoluta" (PT), não "Pitch Black" → estava no gap.
    ("(ING) Elite Trainer Box - Megaevolução 5 - Escuridão Absoluta (English)", "pb-etb-en"),
    ("(ING) Booster Bundle - Megaevolução 5 - Escuridão Absoluta (English)", "pb-bundle-en"),
    ("(ING) Booster Pack - Megaevolução 5 - Escuridão Absoluta (English)", "pb-pack-en"),
    ("(ING) Booster Box - Megaevolução 5 - Escuridão Absoluta (English)", "pb-box-en"),
    # nome EN original segue casando (sem regressão):
    ("(ING) Elite Trainer Box - Pitch Black (English)", "pb-etb-en"),
])
def test_me05_pt_name_escuridao_absoluta(title, expected, registry):
    assert ids(title, registry) == [expected]


@pytest.mark.parametrize("title,expected", [
    ("(ING) Blister Megaevolução 4 - Chaos Rising - Charmeleon (English)", "cr-blister-3pack-charmeleon"),
    ("(ING) Blister Megaevolução 3 - Perfect Order - Chikorita (English)", "po-blister-3pack-chikorita"),
    ("(ING) Blister Escarlate e Violeta 9 - Journey Together - Scrafty (English)", "jtg-blister-3pack-scrafty"),
    ("(ING) Blister Escarlate e Violeta 9 - Journey Together - Yanmega (English)", "jtg-blister-3pack-yanmega"),
    ("(ING) Blister Megaevolução 1 - Megaevolução - Golduck (English)", "meg-blister-3pack-golduck"),
    ("(ING) Blister Megaevolução 1 - Megaevolução - Psyduck (English)", "meg-blister-3pack-psyduck"),
    ("(ING) Blister Megaevolução 2 - Phantasmal Flames - Weavile (English)", "phf-blister-3pack-weavile"),
    ("(ING) Blister Megaevolução 5 - Escuridão Absoluta - Binacle (English)", "pb-blister-3pack-binacle"),
])
def test_blister_3pack_casa_pela_variante(title, expected, registry):
    # Cada blister 3-pack é fixado pelo NOME do Pokémon (requires_terms) — sem isso
    # casaria a variante errada (Single Pack / Premium Checklane do mesmo set).
    assert ids(title, registry) == [expected]


@pytest.mark.parametrize("title", [
    # Variante VIZINHA do mesmo set NÃO pode casar o SKU do 3-pack [Charmeleon]:
    "(ING) Blister Checklane - Megaevolução 4 - Chaos Rising - Toxel (English)",
    "(ING) Blister - Megaevolução 4 - Chaos Rising (English)",   # genérico (sem Pokémon)
    "(ING) Blister Single Pack - Chaos Rising - Toxel (English)",
])
def test_blister_variante_vizinha_nao_casa_3pack(title, registry):
    assert "cr-blister-3pack-charmeleon" not in ids(title, registry)


# --- GAP 2ª leva: caixas Mega-X-ex e Poster Collections de Ascended Heroes ----
@pytest.mark.parametrize("title,expected", [
    ("(ING) Caixa - Megaevolução - Ascended Heroes - Mega Emboar ex Box (English)", "ah-megaex-box-emboar"),
    ("(ING) Caixa - Megaevolução - Ascended Heroes - Mega Feraligatr ex Box (English)", "ah-megaex-box-feraligatr"),
    # ML usa o nome PT do set ("Heróis Excelsos") — set_terms cobre os dois:
    ("Box Pokémon: Coleção Mega Meganium Ex Heróis Excelsos (novo)", "ah-megaex-box-meganium"),
    ("(ING) Caixa - Megaevolução - Ascended Heroes - Coleção Pôster Premium - Mega Lucario (English)", "ah-poster-lucario"),
    ("Pokémon Box Ascended Heroes Mega Lucario Ex Poster Inglês", "ah-poster-lucario"),
])
def test_ah_megaex_box_e_poster_casam_pela_variante(title, expected, registry):
    # Fixados pelo personagem (requires) + set_terms PT/EN. O Mega Lucario ETB do
    # ME01 (set diferente) NÃO colide porque o set_term é "ascended heroes".
    assert ids(title, registry) == [expected]


def test_ah_box_e_poster_nao_quebram_etb_bundle(registry):
    # Caixas/posters novos (type 'box'/'caixa'/'poster' + requires personagem) não
    # podem roubar o ETB/Bundle/Pack genéricos do mesmo set (sem nome de personagem).
    assert ids("(ING) Elite Trainer Box - Megaevolução 2.5 - Ascended Heroes (English)", registry) == ["ah-etb-en"]
    assert ids("(ING) Booster Bundle - Megaevolução 2.5 - Ascended Heroes (English)", registry) == ["ah-bundle-en"]


# --- GAP de produtos EXISTENTES: nomes PT de set faltando nos set_terms --------
# A Liga/OLX/ML são marketplaces BR → muitos títulos usam o nome PT do set. SKUs
# que só tinham o nome EN perdiam silenciosamente essas ofertas (mesma classe de
# bug do ME05/"Escuridão Absoluta"). Os nomes PT vêm do mapa curado de
# scripts/expand_registry_modern.py (mesma fonte que já casava p/ AH/Pitch Black).
@pytest.mark.parametrize("title,expected", [
    # sets que estavam SEM nenhum nome PT (NONE) — recuperados:
    ("(ING) Booster Box - Fagulhas Impetuosas (English)", "ssp-booster-box-en"),       # Surging Sparks
    ("(ING) Booster Box - Equilíbrio Perfeito (English)", "po-box-en"),                 # Perfect Order
    ("(ING) Booster Box - Caos Ascendente (English)", "cr-box-en"),                     # Chaos Rising
    ("(ING) Booster Box - Fogo Fantasmagórico (English)", "phf-box-en"),                # Phantasmal Flames
    ("(ING) Booster Box - Forças Temporais (English)", "tef-box-en"),                   # Temporal Forces
    ("(ING) Booster Box - Máscaras do Crepúsculo (English)", "twm-box-en"),             # Twilight Masquerade
    ("(ING) Booster Box - Rivais Predestinados (English)", "dri-box-en"),               # Destined Rivals
    ("(ING) Booster Box - Amigos de Jornada (English)", "jtg-box-en"),                  # Journey Together
    # sets PARCIALMENTE cobertos — propagado o nome PT já vivo p/ os SKUs que faltavam:
    ("(ING) Booster Box - Coroa Estelar (English)", "scr-booster-box-en"),              # Stellar Crown
    ("(ING) Booster Bundle - Evoluções Prismáticas (English)", "pre-booster-bundle-en"),  # Prismatic Evolutions
    # forma "Megaevolução N" (numeração da era na Liga) — só onde NÃO colide:
    ("(ING) Booster Box - Megaevolução 3 - Equilíbrio Perfeito (English)", "po-box-en"),
    ("(ING) Booster Box - Megaevolução 4 - Caos Ascendente (English)", "cr-box-en"),
])
def test_pt_set_name_recupera_oferta(title, expected, registry):
    assert ids(title, registry) == [expected]


@pytest.mark.parametrize("title,expected", [
    # nome EN segue casando (sem regressão ao adicionar os aliases PT):
    ("Surging Sparks Booster Box (English)", "ssp-booster-box-en"),
    ("Temporal Forces Booster Box (English)", "tef-box-en"),
    ("Coroa Estelar Booster Pack (English)", "scr-pack-en"),
])
def test_en_set_name_ainda_casa(title, expected, registry):
    assert ids(title, registry) == [expected]


def test_phantasmal_me2_nao_rouba_ascended_heroes_2_5(registry):
    # DECISÃO de precisão: "megaevolução 2" (Phantasmal Flames) NÃO foi adicionado
    # como set_term porque, no match por palavra-inteira, " megaevolução 2 " é
    # sub-string de um título "Megaevolução 2.5" (Ascended Heroes) → roubaria a
    # oferta AH. PFL casa pelo nome PT ("Fogo Fantasmagórico"); a numeração ME2
    # fica de fora até o matcher distinguir 2 de 2.5. Este teste trava a decisão.
    ah_25 = "(ING) Booster Bundle - Megaevolução 2.5 - Ascended Heroes (English)"
    got = ids(ah_25, registry)
    assert got == ["ah-bundle-en"]
    assert not any(s.startswith("phf") for s in got)


# --- GAP 3ª leva (2026-06-27): ETBs por personagem do ME01 (Mega Evolution) ---
# Produtos selados reais no tcgcsv (group 24380): Mega Lucario/Gardevoir ETB +
# variante Pokémon Center exclusiva. Não havia meg-etb genérico → sem colisão.
# Cada um é fixado pelo personagem em requires_terms; a variante PC se separa por
# requires "pokemon center" (padrão pre-etb-en vs pre-etb-pc-en).
@pytest.mark.parametrize("title,expected", [
    ("(ING) Elite Trainer Box - Megaevolução 1 - Mega Lucario (English)", "meg-etb-lucario"),
    ("Mega Evolution Elite Trainer Box Mega Gardevoir (English)", "meg-etb-gardevoir"),
    # variante Pokémon Center exclusiva (preço de ref. diferente) → SKU próprio:
    ("Mega Evolution Pokemon Center Elite Trainer Box Mega Lucario (English)", "meg-etb-pc-lucario"),
    ("Mega Evolution Pokémon Center Elite Trainer Box Mega Gardevoir (English)", "meg-etb-pc-gardevoir"),
])
def test_meg_character_etb_casa_pela_variante(title, expected, registry):
    assert ids(title, registry) == [expected]


def test_meg_etb_nao_colide_com_poster_nem_variante_errada(registry):
    # O pôster Mega Lucario (set Ascended Heroes) NÃO pode ser roubado pelo ETB
    # (set Mega Evolution) — set_terms diferentes.
    assert ids("(ING) Caixa - Megaevolução - Ascended Heroes - Coleção Pôster Premium - Mega Lucario (English)",
               registry) == ["ah-poster-lucario"]
    # ETB do personagem ERRADO (sem SKU) e o booster box não devem casar meg-etb-*:
    assert not any(s.startswith("meg-etb") for s in
                   S.match_listing("Mega Evolution Elite Trainer Box Mega Charizard (English)", registry))
    assert "meg-etb-lucario" not in ids("Mega Evolution Booster Box (English)", registry)
    # ETB regular (sem "pokemon center") não casa o SKU PC e vice-versa:
    assert ids("Mega Evolution Elite Trainer Box Mega Lucario (English)", registry) == ["meg-etb-lucario"]
