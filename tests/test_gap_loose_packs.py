"""Gap 2026-07-03 — cobertura TOTAL do catálogo de selados da Liga (arquivo do operador).

O operador entregou a lista completa de 127 títulos REAIS das categorias de selados
da Liga ("Booster avulso / loose packs.md", 2026-07-02) com a diretiva "certifique-se
que todos estão inclusos". Este teste fixa o contrato:

1. TODO título do arquivo casa EXATAMENTE 1 SKU (match único, nunca YELLOW por
   ambiguidade) — exceto a lista fechada `FORA_POR_DECISAO` (produtos que NÃO
   existem no tcgcsv; decisão do operador 2026-07-03: ficam fora, documentado).
2. Os SKUs novos desta leva casam seus títulos verbatim e NÃO roubam os vizinhos
   (premium vs comum, enhanced vs box normal, 1-pack vs 3-pack, variante vs genérico).

SKUs novos: 6 blister unitário genéricos (jtg/po/cr/pb/phf/dri — pid = variante mais
barata COM preço, racional de scripts/readd_tins_split.py), 4 Premium Checklane ME05
(pids sem preço no tcgcsv hoje -> RED honesto), 2 POP Series (Vintage Pack; POP6 sem
preço), jtg/meg-enhanced-box (Enhanced Booster Box é produto próprio, ~$278/$329 vs
box normal), split asc-tech-sticker (Charmander 666908 / Gastly 666909) e split
asc-mini-tin em 5 variantes (dispersão 19.5% > 15%; genérico re-apontado p/ Zorua).
Também: termos PT "coleção treinador avançado" e "combo de pacotes" adicionados aos
ETBs/bundles que só tinham os termos EN (mesma classe do bug ME05 do PR #51).
"""
import pathlib

import pytest
import yaml

import sealed_arbitrage_scanner as S

REGISTRY = pathlib.Path(__file__).resolve().parents[1] / "sku_registry.yaml"


@pytest.fixture(scope="module")
def registry():
    return S.build_registry(yaml.safe_load(REGISTRY.read_text(encoding="utf-8")))


def ids(title, reg):
    return sorted(s.id for s in S.match_listing(title, reg))


# ---------------------------------------------------------------------------
# Lista COMPLETA do arquivo do operador (títulos verbatim, sem os cabeçalhos
# de categoria). Cópia embutida de propósito: o arquivo original mora no
# OneDrive do operador e não viaja pro CI.
# ---------------------------------------------------------------------------
TITULOS_OPERADOR = [
    # Booster avulso / loose packs
    "Booster Avulso - Trick or Trade 2023",
    "Booster Avulso - Trick or Trade 2024",
    "Booster Avulso - Escarlate e Violeta 9 - Amigos de Jornada",
    "Booster Avulso - Megaevolução 3 - Equilíbrio Perfeito",
    "Booster Avulso - Megaevolução 4 - Caos Ascendente",
    "Booster Avulso - Megaevolução 5 - Escuridão Absoluta",
    "Booster Avulso - Megaevolução 1 - Megaevolução",
    "Booster Avulso - Megaevolução 2 - Fogo Fantasmagórico",
    "Booster Avulso - Escarlate e Violeta 8 - Fagulhas Impetuosas",
    "Booster Avulso - Escarlate e Violeta 10.5 - Fogo Branco",
    "Booster Avulso - Máscaras do Crepúsculo",
    "Booster Avulso - Escarlate e Violeta 1 - Escarlate e Violeta",
    "Booster Avulso - Escarlate e Violeta 4 - Fenda Paradoxal",
    "Booster Avulso - Forças Temporais",
    "Booster Avulso - Escarlate e Violeta 10 - Fagulhas Impetuosas",
    "Booster Avulso - Escarlate e Violeta 2 - Evoluções em Paldea",
    "Booster Avulso - Escarlate e Violeta 10 - Rivais Predestinados",
    "Booster Avulso - Megaevolução 2.5 - Heróis Excelsos",
    "Booster Avulso - Espada e Escudo 10 - Estrelas Radiantes",
    "Booster Avulso - Escarlate e Violeta 3 - Obsidiana em Chamas",
    "Booster Avulso - Espada e Escudo 12 - Tempestade Prateada",
    "Booster Avulso - Escarlate e Violeta - 151",
    "Booster Avulso - Pop Series 6",
    "Booster Avulso - Pop Series 1",
    # Blister unitário / checklane
    "Blister Unitário - Escarlate e Violeta 9 - Amigos de Jornada",
    "Blister Unitário - Megaevolução 3 - Equilíbrio Perfeito",
    "Blister Unitário - Megaevolução 4 - Caos Ascendente",
    "Blister Unitário - Megaevolução 5 - Escuridão Absoluta",
    "Blister Unitário Checklane - Megaevolução 4 - Caos Ascendente - Toxel",
    "Blister Unitário - Megaevolução 2 - Fogo Fantasmagórico",
    "Blister Unitário - Escarlate e Violeta 10 - Rivais Predestinados",
    "Blister Unitário Checklane - Megaevolução 5 - Escuridão Absoluta - Slowpoke",
    "Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Luxray",
    "Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Gengar",
    "Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Tyrunt",
    "Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Amaura",
    # Double packs / blister duplo
    "Blister Duplo Enhanced - Vileplume",
    "Blister Duplo - Escarlate e Violeta - Back to School 2024 - Bellibolt",
    "Blister Duplo - Megaevolução 2.5 - Heróis Excelsos - Tangela",
    "Blister Duplo - Megaevolução 2.5 - Heróis Excelsos - Komala",
    # Triple packs / blister triplo
    "Blister Triplo Megaevolução 4 - Caos Ascendente - Charmeleon",
    "Blister Triplo Escarlate e Violeta 9 - Amigos de Jornada - Scrafty",
    "Blister Triplo Megaevolução 5 - Escuridão Absoluta - Binacle",
    "Blister Triplo Megaevolução 3 - Equilíbrio Perfeito - Chikorita",
    "Blister Triplo Escarlate e Violeta 9 - Amigos de Jornada - Yanmega",
    "Blister Triplo Megaevolução 1 - Megaevolução - Golduck",
    "Blister Triplo Megaevolução 1 - Megaevolução - Psyduck",
    "Blister Triplo Escarlate e Violeta 10 - Rivais Predestinados - Zebstrika",
    "Blister Triplo Escarlate e Violeta 10 - Rivais Predestinados - Kangaskhan",
    # Tech sticker
    "Blister Triplo Tech Sticker Escarlate e Violeta 10.5 - Fogo Branco - Gothitelle",
    "Blister Triplo Tech Sticker Escarlate e Violeta 10.5 - Raio Preto - Reuniclus",
    "Blister Triplo Tech Sticker Megaevolução 2.5 - Heróis Excelsos - Gastly",
    "Blister Triplo Tech Sticker Megaevolução 2.5 - Heróis Excelsos - Charmander",
    "Blister Triplo Tech Sticker Escarlate e Violeta 8.5 - Evoluções Prismáticas - Leafeon",
    # Mini tins / mini latas
    "Mini Lata - Lumiose - Emboar",
    "Mini Lata - Lumiose - Gallade",
    "Mini Lata - Lumiose - Meganium",
    "Mini Lata - Lumiose - Salamence",
    "Mini Lata - Lumiose - Feraligatr",
    "Mini Lata - Megaevolução 1 - Mega Heroes - Mega Latios",
    "Mini Lata - Megaevolução 1 - Mega Heroes - Mega Kangaskhan",
    "Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Togepi",
    "Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Zorua",
    "Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Clefairy",
    "Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Pikachu",
    "Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Riolu",
    "Mini Lata - Megaevolução 1 - Mega Heroes - Mega Venusaur",
    # Tins / latas / collector chest
    "Lata Moonlit - Mega Clefable",
    "Lata Slashing Legends - Koraidon EX",
    "Lata Slashing Legends - Zacian EX",
    "Lata Mega Charizard Y ex",
    "Lata Nidoking Ex da Equipe Rocket",
    "Lata Persian Ex da Equipe Rocket",
    "Lata Mega Charizard X ex",
    "Lata Mewtwo Ex da Equipe Rocket",
    "Lata Pokémon - Maleta de Colecionador - Outono 2025",
    "Lata Moonlit - Mega Gengar",
    "Lata Pokémon - Collector Chest - Outono 2024",
    # Booster bundle / combo de pacotes
    "Combo de Pacotes - Megaevolução 3 - Equilíbrio Perfeito",
    "Combo de Pacotes - Megaevolução 4 - Caos Ascendente",
    "Combo de Pacotes - Megaevolução 5 - Escuridão Absoluta",
    "Combo de Pacotes - Megaevolução 1 - Megaevolução",
    "Combo de Pacotes - Escarlate e Violeta 9 - Amigos de Jornada",
    "Combo de Pacotes - Megaevolução 2 - Fogo Fantasmagórico",
    "Combo de Pacotes - Escarlate e Violeta 10.5 - Fogo Branco",
    "Combo de Pacotes - Escarlate e Violeta 10 - Rivais Predestinados",
    "Combo de Pacotes - Megaevolução 2.5 - Heróis Excelsos",
    "Combo de Pacotes - Escarlate e Violeta 10.5 - Raio Preto",
    "Combo de Pacotes - Escarlate e Violeta 8.5 - Evoluções Prismáticas",
    # Booster box / caixa de booster
    "Caixa de Booster - Megaevolução 3 - Equilíbrio Perfeito",
    "Caixa de Booster - Megaevolução 4 - Caos Ascendente",
    "Caixa de Booster - Megaevolução 5 - Escuridão Absoluta",
    "Caixa de Booster - Escarlate e Violeta 9 - Amigos de Jornada",
    "Caixa de Booster - Megaevolução 1 - Megaevolução",
    "Caixa de Booster Enhanced - Escarlate e Violeta 9 - Amigos de Jornada",
    # ETB / coleção treinador avançado
    "Coleção Treinador Avançado - Megaevolução 3 - Equilíbrio Perfeito",
    "Coleção Treinador Avançado - Megaevolução 5 - Escuridão Absoluta",
    "Coleção Treinador Avançado - Megaevolução 4 - Caos Ascendente",
    "Coleção Treinador Avançado - Escarlate e Violeta - Amigos de Jornada",
    "Coleção Treinador Avançado - Megaevolução 2.5 - Heróis Excelsos",
    "Coleção Treinador Avançado - Escarlate e Violeta 10.5 - Fogo Branco",
    "Coleção Treinador Avançado - Megaevolução 2 - Fogo Fantasmagórico",
    "Coleção Treinador Avançado - Escarlate e Violeta - Fábulas Nebulosas",
    # Poster collection / coleção pôster
    "Caixa - Escarlate e Violeta 10.5 - Fogo Branco e Raio Preto - Coleção Pôster",
    "Caixa - Megaevolução - Heróis Excelsos - Coleção Pôster Premium - Mega Lucario",
    "Caixa - Megaevolução - Heróis Excelsos - Coleção Pôster Premium - Mega Gardevoir",
    # Collection boxes / caixas e coleções
    "Box Coleção - Zacian do Lupo Ex",
    "Box Coleção - Mega Latias Ex Box",
    "Box Coleção - Mega Kangaskhan ex",
    "Box Coleção - Dia de Pokémon 2026",
    "Box Coleção - Mewtwo da Equipe Rocket Ex",
    "Box Coleção Premium - Escarlate e Violeta - Bellibolt Ex da Kissera",
    "Box Coleção Ilustração Parceiro Inicial - Serie 2",
    "Box Coleção Especial - Charizard Ex",
    "Box Coleção Premium - Mega Venusaur ex",
    "Box Coleção - Mega Lucario ex Figure Collection",
    "Box Coleção Premium - Mega Zygarde ex",
    "Box Coleção Premium - Escarlate e Violeta - Garchomp da Cíntia Ex",
    "Caixa - Megaevolução - Heróis Excelsos - First Partners Deluxe Pin Collection",
    "Caixa - Megaevolução - Heróis Excelsos - Mega Meganium ex Box",
    "Caixa - Megaevolução - Heróis Excelsos - Mega Emboar ex Box",
    "Caixa - Megaevolução - Heróis Excelsos - Mega Feraligatr ex Box",
    "Coleção Ilustração - Escarlate e Violeta 10.5 - Fogo Branco e Raio Preto - Victini",
    "Box Coleção Premium - Salamence ex e Reshiram ex",
    "Box Coleção Especial - Accessory Pouch Evoluções Prismáticas",
    "Box Coleção Ilustração Parceiro Inicial - Serie 1",
    "Box Coleção Premium - Hydreigon ex e Dragapult ex",
]

# Produtos SEM produto correspondente no tcgcsv (group ASC 24541 tem ZERO blister
# selado — re-confirmado 2026-07-03). Decisão do operador: FORA do registry,
# documentado; nunca inventar preço. Se um dia o tcgcsv listar, cadastrar.
FORA_POR_DECISAO = {
    "Blister Duplo - Megaevolução 2.5 - Heróis Excelsos - Tangela",
    "Blister Duplo - Megaevolução 2.5 - Heróis Excelsos - Komala",
}


def test_cobertura_total_do_arquivo_do_operador(registry):
    """Toda linha do arquivo do operador casa EXATAMENTE 1 SKU (match único),
    exceto a lista fechada de exclusões documentadas (que casam ZERO)."""
    erros = []
    for titulo in TITULOS_OPERADOR:
        got = ids(titulo, registry)
        if titulo in FORA_POR_DECISAO:
            if got:
                erros.append(f"deveria ficar FORA mas casou: {titulo} -> {got}")
        elif len(got) != 1:
            erros.append(f"{'MULTI' if got else 'ZERO'}: {titulo} -> {got}")
    assert not erros, "\n".join(erros)


def test_fixture_cobre_o_arquivo_inteiro():
    # 139 linhas - 12 cabeçalhos de categoria = 127 produtos
    assert len(TITULOS_OPERADOR) == 127


# ---------------------------------------------------------------------------
# Positivos dirigidos — cada SKU novo casa seu título verbatim
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("titulo,esperado", [
    # blisters unitários genéricos (1 por set)
    ("Blister Unitário - Escarlate e Violeta 9 - Amigos de Jornada", "jtg-blister-1pack"),
    ("Blister Unitário - Megaevolução 3 - Equilíbrio Perfeito", "po-blister-1pack"),
    ("Blister Unitário - Megaevolução 4 - Caos Ascendente", "cr-blister-1pack"),
    ("Blister Unitário - Megaevolução 5 - Escuridão Absoluta", "pb-blister-1pack"),
    ("Blister Unitário - Megaevolução 2 - Fogo Fantasmagórico", "phf-blister-1pack"),
    ("Blister Unitário - Escarlate e Violeta 10 - Rivais Predestinados", "dri-blister-1pack"),
    # checklane com Pokémon cai no genérico do set (e o pid É o do Pokémon citado)
    ("Blister Unitário Checklane - Megaevolução 4 - Caos Ascendente - Toxel", "cr-blister-1pack"),
    ("Blister Unitário Checklane - Megaevolução 5 - Escuridão Absoluta - Slowpoke", "pb-blister-1pack"),
    # premium checklane = produto próprio (~2x o preço), nunca o genérico
    ("Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Luxray", "pb-checklane-premium-luxray"),
    ("Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Gengar", "pb-checklane-premium-gengar"),
    ("Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Tyrunt", "pb-checklane-premium-tyrunt"),
    ("Blister Unitário Checklane Premium - Megaevolução 5 - Escuridão Absoluta - Amaura", "pb-checklane-premium-amaura"),
    # POP Series (Vintage Pack)
    ("Booster Avulso - Pop Series 1", "pop1-pack"),
    ("Booster Avulso - Pop Series 6", "pop6-pack"),
    # Enhanced Booster Box é produto próprio ($278.72 vs box normal)
    ("Caixa de Booster Enhanced - Escarlate e Violeta 9 - Amigos de Jornada", "jtg-enhanced-box-en"),
    # tech sticker AH: split por Pokémon (pids/preços próprios)
    ("Blister Triplo Tech Sticker Megaevolução 2.5 - Heróis Excelsos - Gastly", "asc-tech-sticker-gastly"),
    ("Blister Triplo Tech Sticker Megaevolução 2.5 - Heróis Excelsos - Charmander", "asc-tech-sticker-charmander"),
    # mini tin AH: split por Pokémon (dispersão 19.5%)
    ("Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Togepi", "asc-mini-tin-togepi"),
    ("Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Zorua", "asc-mini-tin-zorua"),
    ("Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Clefairy", "asc-mini-tin-clefairy"),
    ("Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Pikachu", "asc-mini-tin-pikachu"),
    ("Mini Lata - Megaevolução 2.5 - Heróis Excelsos - Riolu", "asc-mini-tin-riolu"),
    # termos PT recuperados (mesma classe do bug ME05 do PR #51)
    ("Combo de Pacotes - Megaevolução 3 - Equilíbrio Perfeito", "po-bundle-en"),
    ("Combo de Pacotes - Escarlate e Violeta 8.5 - Evoluções Prismáticas", "pre-booster-bundle-en"),
    ("Coleção Treinador Avançado - Escarlate e Violeta - Amigos de Jornada", "jtg-etb-en"),
    ("Coleção Treinador Avançado - Megaevolução 2 - Fogo Fantasmagórico", "phf-etb-en"),
])
def test_novos_skus_casam_titulo_real(registry, titulo, esperado):
    assert ids(titulo, registry) == [esperado]


# ---------------------------------------------------------------------------
# Negativos adversariais — os novos SKUs não roubam os vizinhos
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("titulo,esperado", [
    # 3-pack continua no SKU de 3-pack, não no blister unitário novo
    ("Blister Triplo Megaevolução 4 - Caos Ascendente - Charmeleon", ["cr-blister-3pack-charmeleon"]),
    ("Blister Triplo Megaevolução 5 - Escuridão Absoluta - Binacle", ["pb-blister-3pack-binacle"]),
    # box normal continua no SKU normal (não vira enhanced)
    ("Caixa de Booster - Escarlate e Violeta 9 - Amigos de Jornada", ["jtg-box-en"]),
    ("Caixa de Booster - Megaevolução 1 - Megaevolução", ["meg-booster-box"]),
    # tech sticker SEM Pokémon no título -> fallback genérico (não vira MULTI)
    ("Blister Triplo Tech Sticker Megaevolução 2.5 - Heróis Excelsos", ["asc-tech-sticker"]),
    # mini lata SEM Pokémon -> fallback genérico; display continua no display
    ("Mini Lata - Megaevolução 2.5 - Heróis Excelsos", ["asc-mini-tin"]),
    ("Mini Lata Display - Megaevolução 2.5 - Heróis Excelsos", ["asc-mini-tin-display"]),
    # blister duplo Vileplume continua no SKU próprio (tem "enhanced" no título!)
    ("Blister Duplo Enhanced - Vileplume", ["vileplume-2pack-blister"]),
    # idioma barrado
    ("Blister Unitário - Escarlate e Violeta 9 - Amigos de Jornada (Japonês)", []),
    ("Booster Avulso - Pop Series 1 Japanese", []),
    # POP display/box não casa o pack avulso
    ("Booster Box Display - Pop Series 1", []),
    # exclusões documentadas (sem produto no tcgcsv) seguem sem match
    ("Blister Duplo - Megaevolução 2.5 - Heróis Excelsos - Tangela", []),
    ("Blister Duplo - Megaevolução 2.5 - Heróis Excelsos - Komala", []),
])
def test_negativos_adversariais(registry, titulo, esperado):
    assert ids(titulo, registry) == esperado
