# HANDOFF — Sealed Scanner — 2026-06-27 (cobertura EN ≤R$1200)

> Documento de passagem de contexto para **assumir este trabalho em outra sessão**
> (inclusive uma sessão da nuvem que só clonou o GitHub e não tem memória local).
> Linguagem direta para o operador (Matheus, médico, não-programador): cada termo
> técnico vem explicado. **Supersede `HANDOFF-2026-06-27-gap-skus.md`** (aquele vira
> histórico). Estado atual = `main` @ `c43e549`, **180 SKUs, 282 testes**.

---

## 0. TL;DR — onde paramos

Duas linhas de trabalho fechadas hoje:

1. **Paldean Fates** (set "Destinos de Paldea") — 7 SKUs cadastrados (#54). O set
   estava 100% invisível porque a Liga lista pelo nome PT. **Mas hoje não há
   estoque EN ao vivo na Liga** (só PT-BR), então não aparece em scan — os SKUs
   ficam prontos pra quando aparecer.
2. **Cobertura EN ≤R$1200** (meta `/goal`) — minerei os produtos que a Liga oferta
   em inglês até R$1200 e **cadastrei +50 SKUs** cobrindo latas, boxes de coleção,
   boosters antigos, blisters e prerelease. Habilitei 2 categorias novas no scan
   (**Latas** e **Pacote Pré-Lançamento**) que antes nem eram coletadas.

**A cobertura EN ≤R$1200 está COMPLETA** para tudo que é (a) TCG selado, (b) acima
do piso R$50, (c) com referência de preço real no tcgcsv, (d) variante não-ambígua,
(e) não é deck. O que sobrou está **legitimamente fora** (§4) — não é pendência.

**A única coisa não-feita é rodar um SCAN DE PRODUÇÃO completo** (no PC) pra ver as
margens ao vivo dos 50 produtos novos — as tentativas de scan hoje foram longas e
acabaram interrompidas (§5). A cobertura já está **provada** pelo match contra os
títulos reais da Liga; o scan só confirma e calcula margem.

---

## 1. Estado do repositório

- `main` @ `c43e549`. **180 SKUs** no `sku_registry.yaml`. **282 testes** (`python -m pytest`).
- `data/us_reference.json`: 179 de 180 SKUs com preço. O único sem preço é o
  **pré-existente** `sfa-mini-tin` (Shrouded Fable Mini Tin — tcgcsv não precifica).
- **Categorias varridas no scan** (`config.liga.categorias`): `[10, 14, 21, 24, 25,
  26, 27, 28, 38, 57]` — agora inclui **24 Latas** e **57 Pacote Pré-Lançamento**.
- Working tree limpo. Sem branches WIP pendentes.

### PRs desta sessão (todos mergeados)
| PR | O que entrou |
|---|---|
| #51 | Nomes PT de set faltando (12 sets existentes) |
| #52 | +4 ETBs por personagem do ME01 (Mega Lucario/Gardevoir) |
| #53 | Blister Destined Rivals [Kangaskhan] |
| #54 | Set Paldean Fates EN inteiro (7 SKUs `paf-*`) |
| #55 + #56 | Categoria **Latas (categ=24)** habilitada (DEFAULT_CATEGORIES + config) |
| #57 | Categoria **Pacote Pré-Lançamento (categ=57)** habilitada |
| #58 | **16 LATAS**: Slashing Legends, Mega Moonlit, Mega Charizard X/Y, Team Rocket (Nidoking/Persian/Mewtwo), Collector Chest 2024/2025, Lumiose Mini Tin ×5 |
| #59 | **19 BOXES**: Mega-ex (Latias/Kangaskhan/Hop Zacian/TR Mewtwo), Premium (Bellibolt/Garchomp/Venusaur/Zygarde/Salamence+Reshiram/Hydreigon+Dragapult), Special (Charizard ex/Prismatic Pouch), Illustration (First Partner S1/S2/Victini), Poster (Unova), Figure (Lucario), Pin (AH), Pokémon Day 2026 |
| #60 | 2 boosters SWSH (Astral Radiance, Silver Tempest) + 2 blisters 3-pack (Sneasel, Zebstrika) |
| #61 | 9 prerelease Build&Battle + Vileplume 2-pack + Back-to-School Bellibolt |

---

## 2. ⏳ PENDÊNCIAS (ordem de prioridade)

### P0 — Rodar o SCAN DE PRODUÇÃO no PC (única coisa que falta de verdade)
Não roda na nuvem (IP de datacenter + Cloudflare + Chrome headful). No seu PC:
```powershell
cd C:\Users\mathe\sealed-arbitrage-scanner
git checkout main; git pull
.venv\Scripts\python.exe build_us_reference.py        # refresca preços US (1x)
.venv\Scripts\python.exe run_all_sources.py            # Liga (abre Chrome — NÃO feche) + OLX + ML, ~20 min
.venv\Scripts\python.exe scripts\snapshot.py           # gera a tabela de entrega (Markdown)
```
Isso traz os 50 produtos novos com **margem ao vivo** e a tabela GREEN final.
⚠️ Os scans hoje foram interrompidos 2× (longos). Se travar com erro de navegação
("interrupted by another navigation"), é flakiness transitória — feche o Chrome,
confirme que não há `python`/`chrome` órfão segurando o perfil
`~/.pw_profile_liga_sealed`, e rode de novo.

### P1 — Cadastrar SKUs de prerelease/latas que aparecerem NOVOS no scan
As categorias 24 e 57 agora coletam produtos que antes nem entravam. Um scan fresco
pode trazer latas/prerelease de sets que não estavam na lista de hoje (ex.: estoque
novo). Minerar os "sem SKU" EN ≤R$1200 e cadastrar pelo método da §6.

### P2 — Paldean Fates: cobrir quando aparecer estoque EN
Os 7 `paf-*` estão prontos e validados. Hoje a Liga só tem o set em PT-BR (3 ofertas)
— o scanner ignora (só EN). Quando aparecer oferta EN, casa automático.

### P2 — Itens fora de escopo HOJE (reavaliar se o operador pedir) — ver §4.

---

## 3. Decisões do operador NESTA sessão (FIXAS — não reverter)

- **Battle Decks / Baralhos = FORA.** Diretriz explícita: "manter decks de batalha e
  itens que não sejam do TCG Pokémon fora". Não cadastrar `Baralho Inicial`, `Battle
  Deck`, `Baralho Batalha`. (São 9 produtos no work-list, deixados de propósito.)
- **Lata Mega Charizard ex (Paldean): referência = mercado US doméstico.** Para o tin
  do Charizard a referência é a versão **US** ($188,38), não a International ($132,05)
  — porque a revenda é no mercado interno dos EUA. (Aplica a lógica de "ref fiel ao
  cenário de venda" para latas com 2 variantes US/International.)

---

## 4. O que ficou FORA (legitimamente — NÃO é esquecimento)

Do work-list de 65 produtos EN ≤R$1200, **41 foram cobertos**. Os 24 restantes são
inelegíveis pelas regras da frota:

- **9 Battle Decks/Baralhos** — diretriz do operador (§3).
- **~12 abaixo do piso R$50** — singles blisters genéricos (Journey Together/Perfect
  Order/Chaos Rising/Pitch Black/Phantasmal Flames a R$24-35), checklanes (Toxel/
  Slowpoke), Trick or Trade 2023/2024 (R$15/20), McDonald's Match Battle (R$35). O
  piso de relevância é R$50 (`feedback_min_price_50_brl`).
- **3 sem referência de preço real no tcgcsv** (não cadastrar = "nunca inventar preço"):
  - AH Blister Duplo **Komala** e **Tangela** (R$149) — Ascended Heroes não tem
    NENHUM blister no tcgcsv.
  - Blister Checklane Premium **Amaura** (R$60) — `marketPrice` = `None`
    (Target-exclusive, sem vendas recentes). O **Gengar** (R$49,90) idem + abaixo do piso.
- **Singles blisters ambíguos**: vários títulos da Liga ("Blister - <Set>" sem nome de
  Pokémon) podem ser 2-4 produtos tcgcsv distintos com preços diferentes → não dá pra
  fixar 1 referência sem chutar a variante. Ficam fora por precisão.

---

## 5. ⚠️ Por que os scans foram interrompidos / como rodar bem

- Scan completo = **~15-20 min**, headful (abre Chrome real, perfil
  `~/.pw_profile_liga_sealed`, IP residencial fura o Cloudflare). **Não feche a janela.**
- Hoje 2 scans foram interrompidos (1 morto cedo; 1 deu "navigation interrupted" em
  cascata e veio incompleto). O scan limpo das 15:25 (`results/unified_20260627_152503/`)
  é a base de mineração usada — **ele NÃO tinha as categorias 24/57** (vieram depois),
  então um scan fresco trará latas/prerelease que ele não tinha.
- O **probe de página de produto** (pra preço ao vivo de 1 produto específico) PRECISA
  de `wait_for_selector=".new-price"` — os preços carregam via JS; sem esperar dá falso
  "0 ofertas". (Lição cara desta sessão.)

---

## 6. Como cadastrar um SKU novo com PRECISÃO (o método que usei)

Regra dura da frota: **precisão antes de cobertura** — melhor faltar um SKU do que
casar o errado; **nunca inventar preço**; **nunca deduzir nome por LLM** (só de fonte
real). Passo a passo:

1. **Ache a ref tcgcsv real** (a fonte do preço US). API pública, sem auth:
   - Grupos (sets): `https://tcgcsv.com/tcgplayer/3/groups`
   - Produtos: `https://tcgcsv.com/tcgplayer/3/<groupId>/products` (selado = SEM campo
     `Number` no `extendedData`; cartas têm `Number`)
   - Preços: `https://tcgcsv.com/tcgplayer/3/<groupId>/prices` (`marketPrice`)
   - Header `User-Agent: x` (sem ele alguns endpoints dão 403).
   - **Latas, mini-tins, collector chests, e muitas collection boxes modernas vivem no
     grupo `2374` "Miscellaneous Cards & Products"** (não num grupo de set). First
     Partner Collection = grupo `24584`. SV10.5 White Flare/Black Bolt = `24325`.
2. **Pegue o TÍTULO REAL da Liga** (não invente): mine do CSV do scan, ou faça
   busca-alvo na Liga (`?view=cards/search&card=<termo>%20searchprod%3D1`, headful).
3. **Escreva o SKU** com `set_terms` (PT **e** EN), `type_terms`, `requires_terms` (o
   que fixa a variante: nome do Pokémon, ano, "premium"/"especial", etc.) e
   `exclude_terms` (idiomas + tipos vizinhos pra não casar o produto errado).
   - **NÃO use set_term que seja sub-palavra de outro set** (ex.: `prismatic` é
     sub-palavra de `prismatic evolutions`; `charizard` de `mega charizard`). Use o
     nome completo. A varredura de colisão (§7) pega isso.
   - O scanner casa por **palavra inteira**, acento removido, minúsculas. Guards globais
     já barram carta avulsa / acessório / "Vazia"/usado. ⚠️ **"Shield" (sleeve da Liga)
     NÃO é barrado pelos guards** — exclua `shield` em SKU de box/ETB.
4. **VALIDE contra o título real**: rode `match_listing(titulo, registry)` e confira
   que casa EXATO o SKU certo, e que negativos adversariais (ETB/booster/tin/deck do
   mesmo set, variante vizinha) NÃO casam. Eu fiz isso com um gerador+validador por
   família (ver `scratchpad` da sessão; o padrão está nos `tests/test_gap_*.py`).
5. **Edite o YAML por APPEND de texto cru** (não re-serialize o arquivo todo — ele tem
   anchors `&id001`/`*id002` que `yaml.safe_dump` destrói). Inserir blocos novos no fim
   ou entre 2 `- id:` preserva os anchors.
6. **`build_us_reference.py`** pega o preço; pra **diff mínimo**, injete só os pids
   novos (não deixe o refresh global causar drift nos preços existentes).
7. **Varredura de colisão (§7) + `pytest`** antes de commitar. Branch + PR + CI verde.

---

## 7. Scripts úteis

**Varredura de colisão cross-set** (rodar antes de todo commit no registry):
```python
import yaml, unicodedata
from collections import defaultdict
def n(t):
    d=unicodedata.normalize("NFKD",str(t)); s="".join(c for c in d if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in s.lower()).split())
def contains(h,t): return f" {n(t)} " in f" {n(h)} "
st=defaultdict(set)
for s in yaml.safe_load(open("sku_registry.yaml",encoding="utf-8"))["skus"]:
    for t in s["match"]["set_terms"]: st[str(s.get("set"))].add(t)
col=[(A,x,B,y) for A,ta in st.items() for B,tb in st.items() if A<B
     for x in ta for y in tb if n(x)!=n(y) and (contains(y,x) or contains(x,y))]
print("colisões:", col or "LIMPO")
```

**Minerar produtos EN ≤R$1200 sem SKU de um scan** (acha o próximo gap):
```python
import csv, collections, re, yaml, sealed_arbitrage_scanner as S
reg=S.build_registry(yaml.safe_load(open("sku_registry.yaml",encoding="utf-8")))
rows=list(csv.DictReader(open("results/unified_AAAAMMDD_HHMMSS/unified_deals.csv",encoding="utf-8")))
def fl(x):
    try: return float(str(x).replace(",","."))
    except: return None
seen=collections.defaultdict(lambda:1e9)
for r in rows:
    if r["Fonte"]!="liga" or r["SKU"]: continue
    t=re.sub(r"\s+"," ",r["Título (BR)"].strip())
    if not t.lower().startswith("(ing)"): continue
    p=fl(r["Preço BR (R$)"])
    if p is not None and p<seen[t]: seen[t]=p
gap=[t for t,mn in seen.items() if mn<=1200 and not S.match_listing(t,reg)]
print(len(gap),"produtos EN <=R$1200 ainda sem SKU"); [print(" ",t) for t in sorted(gap)]
```

**Listar produtos selados de um grupo tcgcsv** (achar pid+preço):
```python
import urllib.request, json
gid=2374  # ex.: Misc (tins/boxes modernas)
req=urllib.request.Request(f"https://tcgcsv.com/tcgplayer/3/{gid}/products", headers={"User-Agent":"x"})
for p in json.load(urllib.request.urlopen(req)).get("results",[]):
    ext={d['name']:d['value'] for d in (p.get('extendedData') or [])}
    if not ext.get('Number'): print(p['productId'], p['name'])
# preços: https://tcgcsv.com/tcgplayer/3/<gid>/prices (marketPrice por productId)
```

---

## 8. Mapa de arquivos relevantes

```
sku_registry.yaml            catálogo de 180 SKUs (anchors YAML — edite por append cru)
sealed_arbitrage_scanner.py  matcher (match_listing aplica guards: single-card/acessório/usado)
liga_adapter.py              scraper Liga; DEFAULT_CATEGORIES, CATEGORY_PRODUCT_TYPE,
                             SET_TRANSLATE_PT_TO_EN, _LocalChromeFetcher, parse_product_page
config.yaml                  config.liga.categorias = lista OPERANTE (precede DEFAULT_CATEGORIES)
build_us_reference.py        puxa preço tcgcsv -> data/us_reference.json; SANITY_BANDS_USD
data/us_reference.json       cache de preço US (Market TCGplayer via tcgcsv)
run_all_sources.py           orquestrador Liga(headful)+OLX+ML -> results/unified_*/unified_deals.csv
scripts/snapshot.py          gerador CANÔNICO da tabela de entrega (Markdown)
tests/test_gap_*.py          testes por família (tins/boxes/boosters_blisters/prerelease) — padrão de validação
tests/test_liga_categories.py  testes das categorias 24/57
```

---

## 9. Invariantes da frota (NÃO violar)

- **Nunca inventar preço.** Sem ref tcgcsv → sem SKU (RED honesto).
- **Precisão antes de cobertura.** Cada variante fixada por `requires_terms`.
- **Nunca deduzir nome por LLM.** Nome PT/EN só de fonte real (título da Liga / tcgcsv).
- **Piso R$50** de relevância; **margem BRUTA** (sem taxa); **só EN/NM**.
- **Entrega = tabela markdown no chat**, gerada pelo `scripts/snapshot.py` (verbatim),
  2 links por linha (`[oferta] · [TCG]`), todas as linhas.
- **Git:** branch + PR; CI verde antes de mergear; nunca empilhar PRs.
