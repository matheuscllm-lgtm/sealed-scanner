# HANDOFF — Expansão do Catálogo (cobrir TODOS os tipos de produto selado)

> **Tarefa TRANSVERSAL** (afeta OLX + Amazon + Liga + Mercado Livre — o catálogo
> é compartilhado). Não é só de uma fonte. A **fonte única de verdade** do
> projeto continua sendo `../README.md`.
>
> ⚠️ **Diagnóstico por inspeção ao vivo 2026-06-06.** Estrutura, ferramenta e
> dados do tcgcsv foram MEDIDOS, não supostos.

- **Repo:** `C:\Users\mathe\sealed-arbitrage-scanner\` (GitHub privado `matheuscllm-lgtm/sealed-arbitrage-scanner`)
- **Branch base:** `main` (working tree limpo)
- **Arquivos a editar:** `scripts/expand_registry_modern.py` (ampliar regras) · `sku_registry.yaml` (receber as novas entradas) · `config.yaml` (`scope.include`) · `olx_adapter.py`/`amazon_adapter.py`/`mercadolivre_adapter.py` (queries por tipo, se aplicável)
- **Infra que JÁ existe (reusar, não reinventar):** `scripts/expand_registry_modern.py` (lê tcgcsv → gera entradas) + `build_us_reference.py` (puxa preço US) + matcher compartilhado
- **Datado:** 2026-06-06
- **Modo:** MANUAL. Criar branch + PR (push direto a `main` é gateado).

---

## RESUMO PARA O OPERADOR (linguagem simples)

Hoje o robô só conhece **9 tipos** de produto (Booster Box, ETB, Bundle, etc.).
Mas o Pokémon lança **muito mais tipos** (Ultra Premium, Super Premium, Build &
Battle, Battle Decks, Poster, Surprise Box, Collector Chest...). Resultado: vários
produtos legítimos aparecem como "fora do catálogo" e são ignorados.

**A boa notícia:** a loja americana de referência (TCGPlayer, via tcgcsv) **já
lista todos esses produtos com preço**. E nós já temos uma ferramenta que lê essa
lista e cadastra automaticamente — ela só precisa **aprender os tipos novos**.

**O trabalho é:** ensinar a ferramenta a reconhecer os ~20 tipos que faltam,
filtrar o lixo (atacado, carta digital, exclusivos de loja americana), e rodar.
O resultado é o catálogo completo, com preço dos EUA já incluso, valendo pras 4
fontes de uma vez.

---

## 1. Estado atual (o que existe hoje)

- **`sku_registry.yaml`:** 105 produtos, **só inglês**, 20 coleções (era Mega
  Evolution + era Scarlet & Violet). Cobertura IRREGULAR — cada coleção tem só
  alguns tipos (ex.: Mega Evolution não tem ETB cadastrado; Surging Sparks tem 4
  tipos; Prismatic tem 9). O TCGPlayer tem ~13-15 selados/coleção → **faltam vários**.
- **`scripts/expand_registry_modern.py`:** lê os produtos de cada coleção no
  tcgcsv (por `group_id`), classifica por `TYPE_RULES` (regex no nome TCGPlayer →
  tipo canônico), pega o preço US, e emite `scripts/registry_additions.yaml` pra
  revisar. **Hoje só conhece 8 tipos** (TYPE_RULES, linhas 48-57). Tem `GROUPS`
  (20 coleções → group_id + termos de set PT/EN) e `SKIP_NAME` (corta case/code
  card/display/pokemon center/sam's club).
- **`build_us_reference.py`:** pra cada SKU com `tcgplayer_product_id`+`group_id`,
  busca o preço Market no tcgcsv → `data/us_reference.json`. **Sem `product_id` não
  há preço US** → o produto entra mas não classifica. (Por isso gerar via tcgcsv é
  o caminho: ele traz o `product_id` junto.)
- **Matcher (`sealed_arbitrage_scanner.py::match_listing`):** casa `set_terms` **E**
  `type_terms`, exclui `exclude_terms`. O adapter só entrega título cru; o matcher
  resolve. Logo, **adicionar tipo = adicionar SKU com os `type_terms` certos**.
- **`config.yaml::scope.include`:** lista dos tipos "no escopo". Tipo que não
  estiver aqui é filtrado fora. **Precisa ganhar os tipos novos.**

### Anatomia de um SKU (o que o gerador produz)
```yaml
- id: ssp-booster-box-en
  name: Surging Sparks Booster Box (English)
  product_type: Booster Box
  set: Surging Sparks
  set_code: SSP
  language: EN
  pack_count: 36
  tcgplayer_group_id: 23651      # coleção no TCGPlayer
  tcgplayer_product_id: 565606   # produto exato → dá o preço US
  match:
    set_terms: [surging sparks]
    type_terms: [booster box, caixa de booster, booster display]
    exclude_terms: [japones, portugues, copag, ... , code card]
```

---

## 2. O trabalho: ampliar `TYPE_RULES` + filtros + escopo

### 2.1 Tabela mestre de tipos (dicionário PT→EN do operador → regra do gerador)

`TYPE_RULES` casa **regex no nome do produto no TCGPlayer (em inglês)**. Os
`type_terms` são em PT+EN (pra casar o título cru das fontes BR). Status: ✅ já
existe · ➕ adicionar · ⭐ decisão do operador (nicho/ambíguo — ver §3).

| Produto (PT operador) | `product_type` canônico (EN) | regex no nome TCGPlayer | type_terms (PT/EN) | Status |
|---|---|---|---|---|
| Caixa de Booster | Booster Box | `booster box$` | caixa de booster, booster box, booster display | ✅ |
| Caixa de Booster Enhanced | Enhanced Booster Box | `enhanced booster box` | caixa de booster enhanced, enhanced booster box | ➕ |
| Coleção Treinador Avançado | Elite Trainer Box | `elite trainer box$` | coleção treinador avançado, elite trainer box | ✅ |
| ETB Pokémon Center | Pokémon Center Elite Trainer Box | `pokemon center elite trainer box` | treinador avançado pokémon center, pokemon center elite trainer box | ⭐ |
| Combo de Pacotes | Booster Bundle | `booster bundle$` | combo de pacotes, booster bundle | ✅ |
| Booster Avulso (solto) | Booster Pack | `\bbooster pack$` | booster avulso, booster pack | ⭐ (ver §3.1) |
| Blister Unitário | Sleeved Booster | `sleeved booster pack` | blister unitário, sleeved booster | ✅ |
| Blister Unitário Checklane | Checklane Blister | `checklane blister` | blister checklane, checklane blister | ➕ |
| Blister Triplo / Duplo | Blister | `\d-pack blister` | blister triplo, blister duplo, 3-pack blister, 2-pack blister | ➕ |
| Mini Lata | Mini Tin | `mini tin` | mini lata, mini tin | ✅ |
| Lata | Tin | `(?<!mini )\btin$` | lata, tin | ➕ |
| Tech Sticker | Tech Sticker | `tech sticker collection` | blister triplo tech sticker, tech sticker | ✅ |
| Box Coleção (ex Box) | Collection Box | `ex box$` ou `collection box$` | box coleção, ex box, collection box | ⭐ |
| Box Coleção Premium | Premium Collection | `premium collection` | box coleção premium, premium collection | ✅ |
| Box Coleção Especial | Special Collection | `special collection` | box coleção especial, special collection | ➕ |
| Box Ultra Premium | Ultra-Premium Collection | `ultra-?premium collection` | box ultra premium, ultra premium collection | ➕ |
| Box Super Premium | Super-Premium Collection | `super-?premium collection` | box super premium, super premium collection | ➕ |
| Desafio Estratégico | Build & Battle Box | `build & battle box` | desafio estratégico, build battle box | ➕ |
| Baralho Pré Construído (Liga) | League Battle Deck | `league battle deck` | baralho pré construído, league battle deck | ➕ |
| Baralho Batalha ex | ex Battle Deck | `ex battle deck` | baralho batalha ex, ex battle deck | ➕ |
| Baralho Campeonato Mundial | World Championship Deck | `world championship deck` | campeonato mundial, world championship deck | ➕ |
| Ferramentas de Treinador | Trainer's Toolkit | `trainer'?s toolkit` | ferramentas de treinador, trainers toolkit | ➕ |
| Coleção Ilustração | Illustration Collection | `illustration collection` | coleção ilustração, illustration collection | ➕ |
| Box Ilustração Parceiro Inicial | First Partner Illustration Collection | `first partner.*illustration` | parceiro inicial, first partner illustration | ➕ |
| Coleção Pôster | Poster Collection | `poster collection` | coleção pôster, poster collection | ➕ |
| Coleção Pôster Premium | Premium Poster Collection | `premium poster collection` | pôster premium, premium poster collection | ➕ |
| Kit Colecionável Binder | Binder Collection | `binder collection` | binder collection, kit colecionável | ✅ (hoje vira Collection Box — ver §3.3) |
| Caixa Surpresa | Surprise Box | `surprise box$` | caixa surpresa, surprise box | ➕ |
| Maleta de Colecionador | Collector Chest | `collector chest` | maleta colecionador, collector chest | ➕ |
| Accessory Pouch | Accessory Pouch Special Collection | `accessory pouch` | accessory pouch | ⭐ (nicho) |
| Figure Collection | Figure Collection | `figure collection` | figure collection | ⭐ (nicho) |
| Deluxe Pin Collection | Deluxe Pin Collection | `pin collection` | deluxe pin collection, pin collection | ⭐ (nicho) |

> **Ordem importa em `TYPE_RULES`** (mais específico antes do genérico). Ex.:
> `super-?premium` e `ultra-?premium` ANTES de `premium collection`; `pokemon
> center elite trainer box` ANTES de `elite trainer box$`. Senão o genérico
> "rouba" o match.

### 2.2 Filtros (manter/expandir o `SKIP_NAME` e `EXCLUDE_BASE`)
Continuar cortando, e reforçar:
- **`\bcase\b`** — caixa-master de atacado ("ETB Case" = 10 unidades). NUNCA é unidade.
- **`code card`** — carta de código DIGITAL, não é produto físico.
- **`display`** — caixa de displays (atacado), salvo "Mini Tin Display" que JÁ é
  um SKU legítimo (cuidado: não cortar Mini Tin Display).
- **Exclusivos de loja US** — `dollar general`, `sam's club`, `target`, `walmart`,
  `costco`, `gamestop` (irrelevantes no Brasil).
- **`\bset of \d`** — lotes ("Set of 3/4").
- Manter `EXCLUDE_BASE` (idiomas não-inglês + acessório acrílico/capa).

### 2.3 `scope.include` (config.yaml)
Adicionar TODOS os `product_type` canônicos novos. Tipo fora do `scope.include` é
filtrado pelo scanner mesmo se casar. Lista canônica = a coluna "product_type" da §2.1.

### 2.4 Queries por tipo nos adapters (cobertura de busca)
OLX/Amazon/ML buscam por tipo de produto. Pra um tipo novo ser ENCONTRADO (não só
reconhecido), as queries precisam mirá-lo:
- **OLX** (`olx_adapter.TYPE_TO_QUERY`) e **ML** (`mercadolivre_adapter`): adicionar
  buscas pros tipos de maior volume (ex.: "ultra premium pokemon ingles", "build &
  battle pokemon"). NÃO precisa 1 query por tipo nicho (custo Firecrawl) — priorizar.
- **Amazon** (`_derive_query` por SKU): já cobre, pois deriva do registry.
- ⚠️ Custo: cada query nova = +N scrapes/scan. Priorizar tipos com inventário real
  no BR; deixar nicho (Pin/Figure/Pouch) sem query dedicada (entram só se caírem
  numa busca ampla).

---

## 3. Decisões do operador (⭐ marcados na tabela)

1. **§3.1 "Booster Pack" (solto) vs "Sleeved Booster":** no TCGPlayer existem os
   dois — `Booster Pack` (avulso solto) e `Sleeved Booster Pack` (avulso com
   blister). Hoje só temos "Sleeved Booster". **Decidir:** tratar como UM tipo
   ("Sleeved Booster", englobando os dois) ou DOIS tipos distintos? Recomendação:
   UM só (o BR raramente distingue), evitando inflar o catálogo.
2. **Pokémon Center ETB:** hoje é PULADO (`SKIP_NAME` corta "pokemon center").
   É produto legítimo e caro (exclusivo). **Decidir:** incluir como tipo próprio?
   Recomendação: incluir (você listou) — preço bem diferente do ETB normal, então
   precisa ser SKU separado, não colapsar com ETB.
3. **§3.3 Binder/Collection Box:** hoje "Binder Collection" vira `Collection Box`.
   Sua lista trata Binder como tipo próprio. **Decidir:** manter colapsado em
   Collection Box, ou separar Binder/Poster/Illustration/ex Box como tipos
   distintos? Recomendação: separar (preços e liquidez bem diferentes).
4. **Nicho (Pin/Figure/Accessory Pouch/Collector Chest):** selados, mas de baixa
   liquidez e volume no BR. **Decidir:** cadastrar (cobertura total) ou deixar de
   fora da v1 (foco no que gira)? Recomendação: cadastrar no registry (custo zero,
   o gerador já pega), mas SEM query dedicada nos adapters.
5. **Variantes por Pokémon:** o gerador hoje colapsa variantes (8 Mini Tins de
   Eevee → 1 SKU "Mini Tin", pega o 1º preço). OK pro matching (o tipo importa),
   mas o preço US é de UMA variante. **Decidir:** aceitar (simples) ou usar preço
   médio/mediano das variantes? Recomendação: mediana das variantes do mesmo tipo
   (mais justo) — pequeno ajuste no gerador.

---

## 4. Passo a passo de execução

1. **Ampliar `TYPE_RULES`** em `expand_registry_modern.py` com as linhas ➕ da §2.1
   (ordem: específico → genérico). Resolver os ⭐ da §3 com o operador antes.
2. **Reforçar `SKIP_NAME`/`EXCLUDE_BASE`** (§2.2): adicionar exclusivos de loja US,
   `set of \d`. Garantir que "Mini Tin Display" NÃO seja cortado por `display`.
3. **(opcional) preço mediano** das variantes no gerador (§3.5).
4. **Rodar** `python scripts/expand_registry_modern.py` → gera
   `scripts/registry_additions.yaml`. **Revisar à mão** (conferir nomes/preços
   estranhos, duplicatas, falsos selados).
5. **Mesclar** as entradas revisadas no `sku_registry.yaml` (sem duplicar IDs
   existentes — o gerador já deduplica por set+type).
6. **Atualizar `scope.include`** (§2.3) com os tipos novos.
7. **Atualizar queries** dos adapters (§2.4) pros tipos prioritários.
8. **Rodar `python build_us_reference.py`** → atualiza `data/us_reference.json`
   (preços US de todos os SKUs, incl. os novos).
9. **Testes:** `python -m pytest -q` (não regredir). Adicionar caso de matcher pros
   tipos novos (ex.: "Box Ultra Premium" PT casa o SKU UPC; não casa ETB).

---

## 5. Validação / critério de aceite

- `expand_registry_modern.py` gera entradas pros tipos novos COM `tcgplayer_product_id`
  e preço US presente (sem isso, o SKU é inútil).
- Um scan de teste (ex.: OLX) que antes jogava "Box Ultra Premium" em
  `sem_match_no_registry` agora **casa** e classifica por margem.
- Catálogo cresce de 105 pra ~N SKUs; **nenhum** com nome contendo "Case"/"Code
  Card"/exclusivo de loja US (rodar um grep de sanidade).
- `python -m pytest -q` verde.
- `data/us_reference.json` tem preço pra todos os SKUs novos (ou o SKU é removido).

---

## 6. Armadilhas conhecidas

- **Sem `product_id`/preço US, o SKU é morto** — o gerador já pula quem não tem
  preço; manter essa regra.
- **Ordem das `TYPE_RULES`** — específico antes de genérico (super/ultra-premium
  antes de premium; pokémon center ETB antes de ETB). Erro aqui = match errado.
- **"Display" é ambíguo** — cortar displays de atacado MAS preservar "Mini Tin
  Display" (que é um SKU real do nosso catálogo).
- **Nem todo tipo existe em todo set** — normal; o gerador só emite o que o tcgcsv
  tem. Não forçar set×tipo inexistente.
- **Custo Firecrawl** (OLX/ML) — não criar query dedicada pra cada um dos ~30
  tipos; priorizar os de volume real no BR (§2.4).
- **PT-BR/exclusão** — o registry já exclui idiomas; manter `EXCLUDE_BASE`. (Há um
  problema correlato: muito selado PT-BR escapa pro `sem_match` porque usa só o
  nome do set traduzido — melhoria separada do filtro de idioma, fora deste escopo.)
- **Não inflar com nicho sem liquidez** — cadastrar é barato, mas avaliar antes de
  dar query dedicada (custo de scrape vs. raridade do produto no BR).

---

## 7. Entrega

- **Branch:** `feat/catalog-expansion` (do `main`; não empilhar).
- **PR** contra `main`. Tocar: `scripts/expand_registry_modern.py`,
  `sku_registry.yaml`, `config.yaml` (`scope.include` + queries), adapters
  (queries por tipo), `tests/`. Mencionar no corpo do PR a contagem antes/depois
  de SKUs e a lista de tipos novos.
- **Não toca README** (invariante). Não commitar `data/us_reference.json` se ele
  for gerado/gitignorado (conferir).
- ⚠️ **Transversal:** rodar e validar um scan de CADA fonte impactada, ou ao menos
  o mock + OLX, antes de mergear.

---

## 8. Objetivos (ordem)

1. Decidir os ⭐ da §3 com o operador.
2. Ampliar `TYPE_RULES` + filtros, rodar o gerador, revisar a saída.
3. Mesclar no registry + `scope.include` + queries + `build_us_reference`.
4. Validar (scan de teste + pytest) e abrir o PR.
5. (depois) Avaliar a melhoria correlata do filtro de idioma (PT-BR escapando pro
   `sem_match`) — escopo SEPARADO.
