# HANDOFF — Sealed Scanner — 2026-06-27

> Documento de passagem de contexto para **assumir este trabalho em outra sessão**
> (inclusive uma sessão da nuvem que só clonou o GitHub e não tem memória local).
> Linguagem direta para o operador (Matheus, médico, não-programador): cada termo
> técnico vem explicado. **Supersede o `HANDOFF-2026-06-26-gap-skus.md`** (aquele
> continua válido como histórico das levas #49/#50; este traz o estado atual).

---

## 0. TL;DR — onde paramos

Objetivo da linha de trabalho: **fechar os "gaps" de cobertura do scanner** — ou
seja, ensinar o scanner a reconhecer produtos selados de Pokémon que ele estava
ignorando (jogando em RED por "não tenho esse SKU cadastrado"), sem nunca casar o
produto errado nem inventar preço.

Nesta sessão (2026-06-27) fechei **duas frentes**:

1. **Gap de PRODUTOS EXISTENTES (nomes PT de set)** → **PR #51, JÁ MERGEADO** no `main`.
2. **3ª leva — collection boxes de personagem** → **PR #52, ABERTO (draft), CI verde** —
   aguarda sua decisão de merge.

**Estado do repo agora:**
- `main` @ `40eeb79` (após #51). Branch de trabalho: **`claude/gap-skus-handoff-5fjsn2`**
  (= head do PR #52, 1 commit à frente do `main`, árvore limpa).
- **122 SKUs** no `sku_registry.yaml` (era 118 no começo da sessão).
- **201 testes** passando (`python -m pytest`). Era 180.
- `data/us_reference.json`: **121 de 122** SKUs com preço (o único sem preço é
  `sfa-mini-tin` / Shrouded Fable Mini Tin — **pré-existente**, o tcgcsv não
  precifica; NÃO é desta sessão).

**A única coisa que destrava o resto continua sendo um SCAN LOCAL DA LIGA** (no
seu PC — não roda na nuvem; ver §6). Ele valida tudo isto em produção e gera a
lista nova de anúncios sem-SKU pra próxima leva.

---

## 1. O que foi feito nesta sessão (2026-06-27)

### 1a. PR #51 — Gap de produtos EXISTENTES: nomes PT de set (✅ MERGEADO, main @ 40eeb79)

**O problema (classe de bug recorrente):** Liga/OLX/ML são marketplaces
**brasileiros**; muitos anúncios escrevem o nome do set **em português**. Vários
SKUs que JÁ existiam no registry tinham só o nome **inglês** nos `set_terms` →
perdiam em silêncio toda oferta com título PT. É a **mesma falha** que escondia o
set inteiro ME05 ("Escuridão Absoluta" = Pitch Black, corrigida no #49) e o
side-finding `ah-*` ("Heróis Excelsos") do handoff de 26/06.

**O que fiz:** auditei a cobertura PT de **TODO** o registry (script em §7) →
12 sets tinham gap. Adicionei o nome PT (e a numeração ME quando segura):

| Categoria | Sets | Alias(es) PT adicionados |
|---|---|---|
| **8 sets SEM nenhum PT (NONE)** | Surging Sparks | `fagulhas impetuosas` |
| | Perfect Order | `equilíbrio perfeito` + `megaevolução 3` |
| | Chaos Rising | `caos ascendente` + `megaevolução 4` |
| | Phantasmal Flames | `fogo fantasmagórico` |
| | Destined Rivals | `rivais predestinados` |
| | Journey Together | `amigos de jornada` |
| | Temporal Forces | `forças temporais` |
| | Twilight Masquerade | `máscaras do crepúsculo` |
| **4 sets PARCIAIS** (alias já vivo em alguns SKUs → propagado aos irmãos) | Ascended Heroes | `heróis excelsos` + `megaevolução 2.5` |
| | Prismatic Evolutions | `evoluções prismáticas` |
| | Stellar Crown | `coroa estelar` |
| | (Scarlet & Violet 151) | **pulado de propósito** — ver §3 |

**Fonte dos nomes PT:** o mapa curado **que já existe no repo**,
`scripts/expand_registry_modern.py` (dicionário `GROUPS`) — a MESMA fonte cujos
termos de Ascended Heroes/Pitch Black já estavam vivos e validados. **Nada
deduzido por LLM** (regra anti-alucinação da frota; lição do ASI-Evolve).

`+16` testes → **196**. Só `set_terms` foi tocado; nenhum preço/pid → `us_reference`
intacto.

### 1b. Demonstração de recuperação (sem commit — prova end-to-end)

Como não dá pra rodar a Liga ao vivo na nuvem (§6), provei a recuperação rodando
o **pipeline real** (`sealed_arbitrage_scanner.py --source mock` →
`scripts/snapshot.py`) sobre títulos **PT sintéticos, rotulados como DEMO**, dos
sets recuperados. Resultado na tabela de entrega canônica: **10 GREEN** (todos os
boxes PT casaram o SKU) **+ 1 RED honesto** (Journey Together a 5,7% — casou/
recuperou, mas classificado RED por margem baixa: prova de que o classificador
não está viciado). Preços marcados como ilustrativos. Nada commitado (era demo).

### 1c. PR #52 — 3ª leva: ETBs por personagem do ME01 (⏳ ABERTO, draft, CI verde)

Fiz o **mapeamento per-produto no tcgcsv** das "collection boxes de personagem"
que o handoff de 26/06 deixou pendente (§5c de lá). Resultado **honesto**:

- ✅ **+4 SKUs adicionados** (refs SELADAS limpas no tcgcsv, group **24380** = ME01
  Mega Evolution):

  | SKU | pid | US$ | Obs |
  |---|---|---:|---|
  | `meg-etb-lucario` | 648394 | 123,46 | citado no handoff 26/06 como gap conhecido |
  | `meg-etb-gardevoir` | 644279 | 119,44 | |
  | `meg-etb-pc-lucario` | 644282 | 322,09 | Pokémon Center exclusiva |
  | `meg-etb-pc-gardevoir` | 648415 | 223,41 | Pokémon Center exclusiva |

  **Não existia `meg-etb` genérico → zero colisão.** Cada um fixado pelo personagem
  em `requires_terms` (`mega lucario`/`mega gardevoir`); a variante Pokémon Center
  separa por `requires "pokemon center"` (mesmo padrão `pre-etb-en` vs `pre-etb-pc-en`).
  São base ME01 → `era_umbrella: true`. Preços dentro da sanity-band ETB (25–950).
  `+5` testes → **201**. `us_reference` refrescado (+4 pids, diff mínimo).

---

## 2. ⏳ PENDÊNCIAS (o que falta — ordem de prioridade)

### P0 — Decidir o merge do PR #52
Draft, CI verde. Mesmos critérios do #51. Mergear quando quiser (ou validar com
scan local antes). Link: https://github.com/matheuscllm-lgtm/sealed-scanner/pull/52

### P0 — Rodar o SCAN LOCAL DA LIGA (destrava tudo)
Não roda na nuvem (§6). No seu PC valida em produção: (a) os GREEN reais dos 12
sets do #51, (b) o match dos 4 ETBs do #52, (c) gera a lista atualizada de
anúncios sem-SKU pra fechar os itens adiados abaixo com **título real**.

### P1 — Worklist da 3ª leva ainda aberto (ref. tcgcsv ACHADA, falta título real)
Já tenho o pid e o preço; só não cadastrei porque **sem um título real da Liga**
não dá pra escrever `set_terms`/`requires` com segurança (precisão > cobertura):

| Produto | group | pid | US$ | Por que adiado |
|---|---|---|---:|---|
| Destined Rivals 3-Pack Blister **[Kangaskhan]** | 24269 | 625683 | 45,21 | mesmo padrão dos 8 blisters do #49; falta confirmar que a Liga lista (e o título) |
| Paldean Fates Tin **[Charizard ex]** | 23353 | 528056 | 188,38 | **Paldean Fates não tem NENHUM SKU** ainda → precisa do set inteiro + nome PT (não está no `expand_registry_modern.py`) |
| Paldean Fates **International** Tin [Charizard ex] | 23353 | 528063 | 132,05 | idem |

### P1 — Caixas de personagem NOMEADAS no gap → NÃO existem como SELADO no tcgcsv
Varri os grupos recentes do tcgcsv: **Mewtwo Rocket, Garchomp Cynthia Premium,
Charizard Ex Especial, Dia de Pokémon 2026, Zacian Lupo, Bellibolt Kissera,
Salamence/Reshiram** só aparecem como **cartas avulsas promo** (fora do escopo
selado), não como box/coleção selada. **`nunca inventar preço` → não cadastrar.**
Re-checar se/quando a TCGplayer publicar o produto selado.
> 🟰 Já cobertos pelo genérico (NÃO precisam de SKU): Mega Heroes Mini Tin por
> personagem (Lucario/Gardevoir/Kangaskhan/Latias/Venusaur, pids 649394-649401,
> ~$20 uniforme) — o `meg-mini-tin` já casa e o preço não varia por personagem.

### P2 — Decisão do operador pendente: Battle Decks / Baralhos entram no escopo?
(Mewtwo Rocket, Mega Diancie, Dragapult, Mega Lucario, etc.) Default histórico:
**fora** (deck ≠ selado de booster). Confirme se quer incluir.

### P2 — Melhoria opcional do matcher (destrava `megaevolução 2` p/ Phantasmal Flames)
Hoje o match é por **palavra inteira** (`contains_term`), e `megaevolução 2` é
sub-string de um título `megaevolução 2.5` (Ascended Heroes) → por isso o número
ME2 ficou **de fora** do PFL (ver §3). Se o matcher passar a distinguir `2` de
`2.5` (ex.: tratar o número do set como token atômico, ou exclude-guard dedicado),
o PFL pode ganhar a forma numérica. Hoje PFL casa pelo nome PT (`fogo fantasmagórico`),
então não é urgente.

### Menores (de antes, ainda abertas)
- `sfa-mini-tin` (Shrouded Fable Mini Tin) sem preço no `us_reference` — o tcgcsv
  não precifica esse pid. Pré-existente, não-bloqueante (cai em RED honesto).
- OLX com bloqueio Cloudflare intermitente — esperado, degrada gracioso.

---

## 3. Decisões de PRECISÃO desta sessão (NÃO reverter sem motivo)

A regra dura da frota é **precisão antes de cobertura**: "melhor faltar um SKU do
que casar o errado". Três freios deliberados, **travados em teste**:

1. **`megaevolução 2` (Phantasmal Flames) NÃO entrou.** No match por palavra
   inteira, ` megaevolução 2 ` é sub-string de um título `Megaevolução 2.5`
   (Ascended Heroes) → roubaria a oferta de AH. Teste:
   `test_phantasmal_me2_nao_rouba_ascended_heroes_2_5`. (ME3/ME4 são livres de
   colisão e ENTRARAM; ME2 não.)
2. **SV 151 não ganhou `escarlate e violeta 151`.** O `set_term` `151` já casa
   todo título do set (o número está sempre presente) → alias PT daria **zero**
   ganho de cobertura. Pulado de propósito, não é esquecimento.
3. **`unova` (Black Bolt) e `mega heroes` (Mega Evolution) NÃO foram propagados.**
   O git prova que são **branding de PRODUTO** ("Unova Mini Tin" / "Mega Heroes
   Mini Tin"), não nome de set — espalhá-los a box/bundle casaria errado. Por
   isso ficam só nos mini-tins onde já estavam.

Garantia geral: rodei uma **varredura de colisão cross-set em TODO o registry**
(nenhum `set_term` é sub-string de palavra-inteira de outro set) → **limpa**,
inclusive após os 4 ETBs novos. Script em §7.

---

## 4. Como o scanner casa um produto (resumo p/ quem vai mexer no registry)

`sealed_arbitrage_scanner.py::match_listing` casa um anúncio a um SKU quando:
`set_terms` casa (qualquer um) **E** `type_terms` casa (qualquer um) **E** TODOS
os `requires_terms` casam **E** nenhum `exclude_terms` casa. Tudo por **palavra
inteira** (`contains_term`), com acento removido e minúsculas (`normalize`).
Guards antes do match: single-card (`looks_like_single_card`), acessório
(`looks_like_accessory`), usado/aberto (`looks_used`). Regra `era_umbrella`: um
SKU "guarda-chuva de era" (set = nome de era, ex. "Mega Evolution") perde quando
um sub-set específico também casa.

**Para adicionar/editar um SKU com segurança:**
- **Edite o YAML com `ruamel.yaml`, NUNCA com `pyyaml`.** O registry usa **anchors/
  aliases YAML** (`&id001`/`*id001`, set_terms/exclude compartilhados) + comentários
  inline; `yaml.safe_dump` DESTRÓI tudo isso. O `ruamel` faz round-trip fiel —
  confirmei **byte-idêntico** num no-op antes de editar. (`pip install ruamel.yaml`
  só pra editar; o runtime/CI continua em pyyaml. Não adicionar ao `requirements`.)
- Nome PT de set: **só** do `scripts/expand_registry_modern.py` (`GROUPS`). Não inventar.
- Variante (blister/box/tin por personagem): **`requires_terms` = nome do Pokémon**
  pra fixar a variante; variante Pokémon Center separa por `requires "pokemon center"`
  + o irmão regular **exclui** "pokemon center".
- Produto novo com pid novo: rode `python build_us_reference.py` p/ puxar o preço
  do tcgcsv; confira que o `product_type` tem **sanity-band** (`SANITY_BANDS_USD`
  em `build_us_reference.py`) e que o preço cai dentro (senão é excluído com aviso).
- **Sempre** rode a varredura de colisão (§7) + `pytest` antes de commitar.

---

## 5. Mapa de arquivos relevantes

```
sku_registry.yaml            catálogo de SKUs (122). Campos: id/name/product_type/set/
                             language/tcgplayer_group_id/tcgplayer_product_id/bulk_qty/
                             era_umbrella + match{set_terms,type_terms,requires_terms,exclude_terms}
sealed_arbitrage_scanner.py  pipeline + matcher (match_listing, normalize, contains_term, guards)
build_us_reference.py        puxa preço do tcgcsv p/ cada pid -> data/us_reference.json; SANITY_BANDS_USD
data/us_reference.json       cache de preço US (Market TCGplayer via tcgcsv). 121/122 com preço
scripts/expand_registry_modern.py  FONTE CURADA dos nomes PT/EN + ME-number por set (dict GROUPS)
scripts/snapshot.py          gerador CANÔNICO da tabela de entrega (lê unified_deals.csv)
run_all_sources.py           orquestrador Liga(headful)+OLX+ML -> results/unified_*/unified_deals.csv
tests/test_matching.py       testes do matcher (201 total) — onde travamos cada decisão
HANDOFF-2026-06-26-gap-skus.md   handoff anterior (levas #49/#50 + análise do gap original)
CHANGELOG.md                 entradas datadas (as duas de 2026-06-27 descrevem esta sessão)
```

---

## 6. ⚠️ Por que o scan da Liga NÃO roda na nuvem (e como rodar no PC)

Verificado nesta sessão — três bloqueios independentes na nuvem:
- **IP de datacenter** → o Cloudflare da Liga bloqueia (o coletor foi feito pra
  **IP residencial**).
- **Sem `DISPLAY`** → o coletor precisa de **Chrome com janela** (headful; headless
  é barrado pelo Cloudflare).
- **`patchright` não instalado** e **`SCRAPERAPI_KEY` não setada** (a rota paga
  alternativa). (tcgcsv.com, por outro lado, **é** acessível na nuvem — foi como
  mapeei os pids.)

**Rodar no SEU PC (Windows), já com os SKUs novos:**
```powershell
cd C:\Users\mathe\sealed-arbitrage-scanner
git checkout main && git pull           # pega o #51 (e o #52 se você mergear)
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\python.exe build_us_reference.py   # refresca preços US (tcgcsv) — 1x antes
.venv\Scripts\python.exe run_all_sources.py      # Liga (abre Chrome — NÃO feche) + OLX + ML, ~15-25 min
.venv\Scripts\python.exe scripts\snapshot.py     # gera a tabela de entrega (Markdown)
```
A **entrega** é a tabela markdown que o `snapshot.py` imprime (cole no chat). Os
itens P1 adiados (§2) se resolvem rapidinho quando esse scan trouxer os títulos reais.

---

## 7. Scripts úteis (reproduzir auditoria/colisão)

**Auditoria de cobertura PT por set** (acha o próximo gap de nome PT):
```python
import yaml, unicodedata
from collections import defaultdict
def n(t):
    d=unicodedata.normalize("NFKD",str(t)); s="".join(c for c in d if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in s.lower()).split())
# fonte curada dos nomes PT: scripts/expand_registry_modern.py GROUPS
reg=yaml.safe_load(open("sku_registry.yaml")); by=defaultdict(list)
for s in reg["skus"]: by[str(s.get("set"))].append([n(t) for t in s["match"]["set_terms"]])
for setn,members in sorted(by.items()):
    union=set().union(*members); incon={t for t in union if not all(t in m for m in members)}
    if incon: print(setn, "INCONSISTENTE:", incon)
```

**Varredura de colisão cross-set** (rodar antes de todo commit no registry):
```python
import yaml, unicodedata
from collections import defaultdict
def n(t):
    d=unicodedata.normalize("NFKD",str(t)); s="".join(c for c in d if not unicodedata.combining(c))
    return " ".join("".join(c if c.isalnum() else " " for c in s.lower()).split())
def contains(h,t): return f" {n(t)} " in f" {n(h)} "
st=defaultdict(set)
for s in yaml.safe_load(open("sku_registry.yaml"))["skus"]:
    for t in s["match"]["set_terms"]: st[str(s.get("set"))].add(t)
col=[(A,x,B,y) for A,ta in st.items() for B,tb in st.items() if A<B
     for x in ta for y in tb if n(x)!=n(y) and (contains(y,x) or contains(x,y))]
print("colisões:", col or "LIMPO")
```

**Listar produtos selados de um grupo no tcgcsv** (achar pid + preço, com `User-Agent`):
```python
import urllib.request, json
gid=24380  # ex.: ME01 Mega Evolution
req=urllib.request.Request(f"https://tcgcsv.com/tcgplayer/3/{gid}/products", headers={"User-Agent":"x"})
for p in json.load(urllib.request.urlopen(req)).get("results",[]):
    ext={d['name']:d['value'] for d in (p.get('extendedData') or [])}
    if not ext.get('Number'):  # pula cartas avulsas (têm Number)
        print(p['productId'], p['name'])
# preços: https://tcgcsv.com/tcgplayer/3/<gid>/prices  (campo marketPrice por productId)
```

---

## 8. Histórico das levas do gap (contexto)

| PR | Estado | O que entrou |
|---|---|---|
| #49 | merged | Tier 0 (ME05 "Escuridão Absoluta" nome-PT) + 8 blisters 3-pack. 63 GREEN recuperados. |
| #50 | merged | 5 SKUs Ascended Heroes (Mega-X-ex boxes + 2 Premium Poster Collections). |
| #51 | **merged (esta sessão)** | Nomes PT de set faltando — 12 sets (8 NONE + 4 PARCIAIS). |
| #52 | **open/draft, CI verde (esta sessão)** | +4 ETBs por personagem do ME01 (Mega Lucario/Gardevoir + PC). |

---

## 9. Invariantes da frota a respeitar (NÃO violar)

- **Nunca inventar preço.** Fonte falhou / produto não está no tcgcsv → sem SKU
  (RED honesto), não se chuta número.
- **Precisão antes de cobertura.** Cada variante (blister/box/tin por personagem)
  precisa de `requires_terms` que a fixe. Adição às cegas reabre falso-positivo.
- **Nunca deduzir alias por LLM.** Nome PT só do `expand_registry_modern.py` (ou
  de título REAL da Liga num scan). Lição do ASI-Evolve.
- **Entrega = tabela markdown no chat**, gerada pelo `scripts/snapshot.py`
  (nunca montada à mão), 2 links por linha (`[oferta] · [TCG]`), todas as linhas.
- **Git:** desenvolver no branch `claude/gap-skus-handoff-5fjsn2`; branch + PR;
  CI verde antes de mergear. Margem é **bruta** (sem taxa), piso R$50.
