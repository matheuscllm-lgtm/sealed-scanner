# HANDOFF — Sealed Scanner — 2026-06-26

> Documento de passagem de contexto. Resume o que foi feito na sessão de 2026-06-26
> e define os próximos passos do objetivo **"revisar a Liga e adicionar os SKUs do
> gap, preço máximo R$1200"**. Linguagem direta para o operador (Matheus, médico,
> não-programador): cada termo técnico vem explicado.

> **✅ EXECUTADO nesta sessão (PR da 1ª leva de SKUs):** Tier 0 + Tier 1 já feitos —
> ver seção 5a. **63 anúncios GREEN recuperados em 8 produtos** que antes eram RED.
> Falta a 2ª leva (Collection Boxes, caixas Mega-X-ex, decisão Battle Decks) —
> seção 5b.

---

## 1. Estado atual do repositório

- **Repo:** `~/sealed-arbitrage-scanner/` (GitHub `matheuscllm-lgtm/Sealed-scanner`).
- **Branch ativo:** `main` @ `9574d95` (após PR #47 mergeado nesta sessão).
- **Testes:** 158 passando (`python -m pytest`).
- **Último scan:** `results/unified_20260626_065125/` (FX USD/BRL 5,1753).
  - Liga 849 anúncios / 66 GREEN · OLX 50 / 2 GREEN · ML 243 / 0 GREEN.
  - Total **68 GREEN / 0 YELLOW / 1074 RED**.
  - Entrega gerada: `snapshots/scan-2026-06-26-0957.md` (15 produtos GREEN).

**Sequência canônica de scan** (do PC, Liga precisa de Chrome com janela):
```
python build_us_reference.py      # refresca preços US (tcgcsv) — roda 1x antes
python run_all_sources.py         # Liga(headful)+OLX+ML — ~15-25 min
python scripts/snapshot.py        # gera a tabela de entrega (Markdown)
```

---

## 2. O que foi feito nesta sessão (PR #47, mergeado, CI verde)

Rodamos o scan completo, entregamos os 15 GREEN e revisamos **produto a produto**.
A auditoria de honestidade de preço deu **100% limpa** (todo preço de referência
bate exato com o TCGplayer via tcgcsv; Stellar Crown Booster Box a US$358 foi
confirmada real, não inflada). Dois defeitos encontrados e corrigidos:

1. **Bug HIGH — uma oferta ruim escondia um produto bom da entrega.**
   O grupo "Ascended Heroes Elite Trainer Box" tinha 3 ofertas GREEN reais
   (R$824,95 a 33% de margem), mas **sumiu da lista entregue**. Motivo: a oferta
   mais barata do grupo era um anúncio de "65 sleeves" (protetores de carta) a
   R$64,50 que se passou pelo ETB e deu margem fantasma de 1600%. O gerador da
   tabela usava "a oferta mais barata" como referência do grupo → herdou o status
   ruim e escondeu as boas.
   **Correção:** a referência do grupo agora vem da oferta mais barata **do melhor
   status disponível** (GREEN antes de RED). Uma oferta ruim nunca mais comanda um
   grupo. (`scripts/snapshot.py`)

2. **Falso-positivo de classificação — pacote de sleeves casava como "box".**
   **Correção:** um título com contador de sleeves ("65 Sleeves") agora é tratado
   como acessório e não casa nenhum produto selado. (`sealed_arbitrage_scanner.py`)

Memórias atualizadas: `sealed_handoff_2026_06_02` e índice `MEMORY.md`.

---

## 3. O gatilho do novo objetivo — avaliação do "Chaos Rising 3-Pack Blister [Charmeleon]"

O operador pediu para avaliar esse produto. Achado:

- **Referência TCGplayer:** US$ 26,23 = **R$ 135,83** (produto 684458, grupo 24655).
- **Ofertas Liga:** 12 anúncios, menor **R$ 83,90** → **margem 61,9%** (mediana
  ~R$89,80 → ~51%). ~115 unidades disponíveis.
- **Problema:** o scanner marcou TODAS essas ofertas como RED — **não por falta de
  margem, mas porque esse produto não está cadastrado no registry** (o catálogo de
  SKUs que o scanner sabe reconhecer). É um **buraco de cobertura**, não um deal
  ruim. Um GREEN forte está passando batido.

Isso expôs que há **muitos** produtos bons na Liga que o scanner ignora por não
estarem cadastrados. Daí o novo objetivo.

> **O que é "registry / SKU":** `sku_registry.yaml` é a lista de produtos que o
> scanner reconhece. Cada entrada (SKU) tem: nome, tipo, id do produto no TCGplayer
> (para puxar o preço de referência) e "termos de match" (palavras que o título do
> anúncio precisa conter para casar). Se um produto não tem SKU, o scanner não sabe
> compará-lo e joga em RED. **Adicionar SKUs = ensinar o scanner a ver mais produtos.**

---

## 4. Análise do GAP (a lista de trabalho)

Minerando o scan de hoje: **519 anúncios da Liga, em inglês, sem SKU, entre R$25 e
R$1200 → 65 produtos distintos**. Os de maior volume (≥2 anúncios), agrupados por
família de produto:

### 4a. EM ESCOPO — provavelmente valem SKU (tipos já aceitos: Blister, ETB, Bundle, Collection Box)

| Família | Exemplos (faixa de preço Liga) |
|---|---|
| **Blisters 3-Pack / Duplo / Checklane** | Chaos Rising Charmeleon R$84-98 (62%!), Perfect Order Chikorita R$85-95, Journey Together (Scrafty/Yanmega) R$85-120, Ascended Heroes Duplo (Komala/Tangela) R$139-175, Escuridão Absoluta Binacle R$90-100, Mega Evolution (Golduck/Psyduck) R$100-200, Phantasmal Flames Weavile R$100-105, blisters "simples" por set R$27-60 |
| **Elite Trainer Box / Bundle (sets novos)** | ETB Escuridão Absoluta (ME05) R$330-360, Booster Bundle Escuridão Absoluta R$168-199 |
| **Collection Boxes** | Mewtwo Rocket Ex R$179-300, Garchomp Cynthia Premium R$259-400, Charizard Ex Especial R$239-370, Mega Zygarde/Venusaur/Kangaskhan/Latias/Lucario, Dia de Pokémon 2026 R$147-200, Zacian Lupo R$99-169, etc. |
| **Caixas "Mega X ex Box" (Ascended Heroes)** | Mega Emboar/Feraligatr/Meganium ex Box R$290-700, Pôster Premium Mega Lucario R$679-999 |

### 4b. PROVÁVEL FORA DE ESCOPO (decisão do operador) — confirmar antes

| Família | Observação |
|---|---|
| **Battle Decks / Baralhos** | Mewtwo Rocket, Mega Diancie, Dragapult, Mega Lucario, Beldum/Metagross, Miraidon, Morpeko/Grimmsnarl — historicamente FORA do escopo (decks ≠ selado de booster). Confirmar se o operador quer incluir. |

> Lista completa dos 65 está reproduzível com o script da seção 6.

---

## 5. NOVO OBJETIVO + PLANO DE EXECUÇÃO

> **Objetivo:** "revisa a Liga e adiciona os produtos / SKUs adicionais que podem
> estar no gap. Com preço máximo R$1200."

### 5a. ✅ JÁ EXECUTADO (1ª leva — Tier 0 + Tier 1)

**Tier 0 — set ME05 recuperado por nome PT:** os SKUs de Pitch Black existiam mas
só casavam "pitch black"; a Liga chama de **"Escuridão Absoluta"**. Adicionado
`escuridao absoluta` + `megaevolucao 5` aos `set_terms` de pb-box/etb/etb-pc/bundle/pack.
→ recupera ETB (14 GREEN @67%), Bundle (14 @131%), Pack (2 @47%), Box.

**Tier 1 — 8 SKUs de Blister 3-Pack** adicionados (cada um fixado pelo nome do
Pokémon em `requires_terms`, para não casar a variante errada):

| SKU novo | pid TCG | US$ | GREEN no scan de hoje |
|---|---|---:|---|
| cr-blister-3pack-charmeleon | 684458 | 26,23 | 12 @62% |
| pb-blister-3pack-binacle | 692938 | 42,82 | 10 @146% |
| meg-blister-3pack-golduck | 644356 | 30,53 | 7 @58% |
| phf-blister-3pack-weavile | 654156 | 40,07 | 3 @107% |
| jtg-blister-3pack-scrafty | 610948 | 23,79 | 1 @45% |
| jtg-blister-3pack-yanmega | 610940 | 23,67 | 0 (29% RED, honesto) |
| meg-blister-3pack-psyduck | 644357 | 41,14 | 0 (15% RED) |
| po-blister-3pack-chikorita | 672393 | 20,72 | 0 (26% RED) |

Também: sanity-band para `Blister` ($3-150) em `build_us_reference.py`; +16 testes
(174 total). **Total: 63 anúncios GREEN recuperados em 8 produtos.** Validação por
reclassificação do scan de hoje (sem re-scan Liga); produção pega no próximo scan.

### 5b. ✅ 2ª leva FEITA (PR #50) — caixas Ascended Heroes

Adicionados 5 SKUs AH (cobertura; todos RED hoje, viram GREEN se BR cair):
`ah-megaex-box-emboar/feraligatr/meganium` (672734/672735/672733),
`ah-poster-lucario/gardevoir` (668536/668537). set_terms cobre EN+PT
("ascended heroes"/"herois excelsos"); fixados pelo personagem em requires_terms.
180 testes.

### 5c. ⏳ FALTA (3ª leva)

- **Collection Boxes de personagem de OUTROS sets** — ⚙️ **MAPEADO em 2026-06-27**
  (varredura tcgcsv categoria 3, grupos recentes). Resultado:
  - ✅ **ADICIONADOS** (refs limpas, group 24380 ME01): `meg-etb-lucario` (648394),
    `meg-etb-gardevoir` (644279), `meg-etb-pc-lucario` (644282), `meg-etb-pc-gardevoir`
    (648415). Fixados por personagem + variante PC separada. Ver CHANGELOG 2026-06-27.
  - ❌ **NÃO existem como SELADO no tcgcsv** (só cartas avulsas promo → fora de
    escopo; `nunca inventar preço`): Mewtwo Rocket, Garchomp Cynthia Premium,
    Charizard Ex Especial, Dia de Pokémon 2026, Zacian Lupo, Bellibolt Kissera,
    Salamence/Reshiram. Re-checar se/quando a TCGplayer publicar o selado.
  - 🟰 **Já cobertos pelo genérico**: Mega Heroes Mini Tin por personagem
    (Lucario/Gardevoir/Kangaskhan/Latias/Venusaur, pids 649394-649401, ~$20
    uniforme) → `meg-mini-tin` já casa; sem SKU novo.
  - ⏳ **Achados, adiados p/ confirmar com título real da Liga**: Destined Rivals
    3-Pack Blister [Kangaskhan] (625683, $45,21); Paldean Fates Tin [Charizard ex]
    (528056, $188,38 / Intl 528063, $132,05 — Paldean Fates sem nenhum SKU ainda).
- **Blister Duplo Ascended Heroes (Komala/Tangela)**: grupo AH (24541) **não tem
  blisters no tcgcsv** → sem referência → RED honesto; não adicionar até haver ref.
- **Decisão pendente do operador:** Battle Decks / Baralhos entram no escopo?
  (default histórico: fora).
- **Blisters genéricos sem Pokémon** ("Blister - <set>") e **Checklane/Single**:
  precisam de variante identificável; pular enquanto ambíguos (precisão primeiro).
- ~~**Side-finding:** os SKUs `ah-*` existentes (etb/bundle/pack) só têm set_term
  "ascended heroes" — listings ML em PT ("Heróis Excelsos") são perdidos.~~
  **✅ RESOLVIDO (2026-06-27) — e generalizado.** Auditoria de cobertura PT em
  TODO o registry: 8 sets estavam SEM nenhum nome PT (Surging Sparks, Perfect
  Order, Chaos Rising, Phantasmal Flames, Destined Rivals, Journey Together,
  Temporal Forces, Twilight Masquerade) e 4 estavam parciais (Ascended Heroes,
  Prismatic Evolutions, Stellar Crown, + SV151 redundante). Adicionados os nomes
  PT (fonte: `scripts/expand_registry_modern.py`, a mesma que já validou AH/Pitch
  Black) a todos eles. Freios de precisão: `megaevolução 2` (PFL) ficou de fora
  (colide com `megaevolução 2.5` de AH no match por palavra-inteira); `unova`/`mega
  heroes` não propagados (branding de mini-tin, não nome de set). 196 testes;
  só `set_terms`, `us_reference` intacto. Ver CHANGELOG 2026-06-27.

### Passos para a próxima sessão (2ª leva)

1. **Triagem (com o operador):** decidir Battle Decks/Baralhos dentro ou fora. O
   resto da seção 4a entra.
2. **Para cada produto em escopo, achar o id no TCGplayer (tcgcsv):**
   - Cada set tem um `group_id` no tcgcsv (ex.: Chaos Rising = 24655, grupo da
     categoria Pokémon = 3). Listar produtos do grupo:
     `https://tcgcsv.com/tcgplayer/3/<group_id>/products` (precisa header
     `User-Agent`, senão 401).
   - Casar o produto certo (atenção a VARIANTE: blister tem Single Pack [Toxel],
     3-Pack [Charmeleon], Premium Checklane [Pawmot/Flygon], Duplo — cada um tem
     id e preço próprios).
3. **Adicionar o SKU ao `sku_registry.yaml`** com:
   - `tcgplayer_product_id` + `tcgplayer_group_id`,
   - `set_terms` (palavras do título PT da Liga, ex.: "chaos rising", "megaevolucao 4"),
   - `type_terms` (ex.: "blister"),
   - **`requires_terms` = o nome do Pokémon** (ex.: "charmeleon") — ISTO É CRÍTICO
     para não casar a variante errada (o blister Charmeleon ≠ blister Toxel).
   - `exclude_terms` se precisar separar de outra variante.
4. **Refrescar referência e validar:** `python build_us_reference.py` →
   `python run_all_sources.py` (ou reusar o CSV de hoje p/ um teste rápido) →
   conferir que cada SKU novo casa **só** seus anúncios e o preço bate.
5. **Testes:** adicionar caso em `tests/test_matching.py` para cada família nova
   (o SKU casa o título certo E NÃO casa a variante vizinha). Rodar `pytest`.
6. **Entregar** a tabela nova (`snapshot.py`) e abrir PR (branch + PR, CI verde
   antes de mergear — convenção do repo).

### Invariantes a respeitar (NÃO violar)

- **Preço máximo R$1200** neste objetivo (corta caixas/cases caras).
- **Precisão antes de cobertura:** cada SKU novo precisa de `requires_terms` que
  fixe a variante. Adição às cegas reabre falso-positivo (foi o erro histórico com
  os tins e com os blisters). Melhor faltar um SKU do que casar o errado.
- **Nunca inventar preço:** se o tcgcsv não tem o produto, o SKU fica sem
  referência (RED honesto), não se chuta número.
- **Guard de margem anômala (>200%) e de variante continuam ligados** — eles são a
  rede de segurança contra match errado.
- **Entrega = 2 links por linha** (oferta + referência TCG), via `snapshot.py`
  verbatim (contrato de entrega da frota).

---

## 6. Script para reproduzir a lista do gap

```bash
cd ~/sealed-arbitrage-scanner
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe - <<'PY'
import csv, re
from pathlib import Path
from collections import defaultdict
d=Path("results/unified_20260626_065125/unified_deals.csv")
def norm(t):
    t=re.sub(r'\(ing\)|\(english\)|ingl[eê]s','',t,flags=re.I)
    return re.sub(r'\s+',' ',t).strip()
gap=defaultdict(list)
for r in csv.DictReader(open(d,encoding="utf-8")):
    if not r["ID Anúncio"].startswith("LIGA"): continue
    if r["SKU"] or r.get("Motivo de rejeição")!="sem_match_no_registry": continue
    try: br=float(r["Preço BR (R$)"])
    except: continue
    if 25<=br<=1200: gap[norm(r["Título (BR)"])].append(br)
for t,brs in sorted(gap.items(), key=lambda kv:-len(kv[1])):
    print(f"n={len(brs):2d}  R${min(brs):.0f}-{max(brs):.0f}  {t}")
PY
```

---

## 7. Pendências menores (de antes desta sessão, ainda abertas)

- Sleeve FP só sai do CSV num próximo scan (a correção é no matcher, à montante).
- OLX segue com bloqueio Cloudflare intermitente (IP flagueado quase toda run) —
  esperado, degrada gracioso.
- Expansão de catálogo (este objetivo) era a pendência #4 do handoff antigo.
