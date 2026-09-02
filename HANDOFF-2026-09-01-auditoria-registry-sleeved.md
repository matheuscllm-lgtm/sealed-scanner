# HANDOFF — 2026-09-01 — Auditoria do registry: productId de Sleeved Booster vs Booster avulso

> **Origem:** análise técnica ad-hoc de um Sleeved Booster do Journey Together
> pediu conferência do preço contra o site do TCGplayer ao vivo — e o valor da
> referência não bateu. A causa não era preço velho: era **productId do
> produto errado**. Auditoria completa dos 205 SKUs Pokémon feita em
> 2026-09-01 contra os nomes reais de produto do tcgcsv (fonte que classifica).
> **Nenhuma mudança foi aplicada** — a direção da correção é decisão do
> operador (ver §3). Registro aqui para a decisão não se perder.

## 1. O achado (exemplo verificado em 2 fontes)

O TCGplayer tem DOIS produtos distintos por set: o **Booster Pack** (avulso,
solto do box) e o **Sleeved Booster Pack** (embalado, mais caro). No grupo
Journey Together (24073), em 2026-09-01:

| productId | Produto (nome real tcgcsv) | Market |
|---|---|---:|
| 610935 | Journey Together Booster Pack (avulso) | US$ 6,80 |
| 610934 | Journey Together Sleeved Booster Pack | US$ 9,35 |

O SKU `jtg-pack-en` declara `product_type: Sleeved Booster` mas aponta para
**610935 (o avulso)** — referência ~27% menor que a do produto que o tipo
declara. Validado contra a página ao vivo do TCGplayer (print do operador,
market US$ 9,35) + nome do produto no tcgcsv.

## 2. Padrão sistemático (auditoria dos 205 SKUs, 32 casos)

Script da auditoria: comparar `product_type` do SKU com o NOME real do
productId no tcgcsv (`/tcgplayer/3/<group>/products`).

- **Todos os 26 SKUs `product_type: Sleeved Booster` apontam para o productId
  do booster AVULSO.** Em 17 sets existe o produto "Sleeved Booster Pack"
  separado no TCGplayer (JTG 610934, SVI 478273, SSP 565602, SCR 557352,
  PO 672412, CR 684448, PB 692957, PHF 654145, TEF 538787, TWM 544170,
  DRI 624684, ME 644354, PAR 517210, OBF 534087, PAL 496927, ASR 265526,
  SIT 283397); em 9 sets NÃO existe produto Sleeved separado (Prismatic, 151,
  Shrouded Fable, Paldean Fates, Black Bolt, White Flare, Ascended Heroes,
  Trick or Trade 2023/2024) — nesses o avulso é o único mapeável.
- **Os 6 SKUs `product_type: Blister` de 1 pack apontam justamente para o
  produto Sleeved Booster** (jtg/po/cr/pb/phf/dri-blister-1pack) — o
  mapeamento parece trocado em bloco entre as duas famílias.

## 3. Decisão em aberto (do operador — NÃO aplicar sem ela)

A correção certa depende do que cada listagem da Liga fisicamente é:

- **Opção A** — se "booster avulso" da Liga = pacote solto: os productIds
  atuais estão CERTOS para o scanner; corrigir só os RÓTULOS
  (`name`/`product_type` honestos). Nenhum preço de referência muda.
- **Opção B** — se a Liga vende o sleeved: trocar os 17 productIds para o
  produto Sleeved real (referências sobem ~30-40% → margens do scan sobem
  nesses SKUs) e revisar os 6 blisters junto.
- **Opção C** — manter como está e tratar caso a caso.

> ✅ **DECIDIDO (operador, 2026-09-01): Opção A.** "A Liga vende pacote avulso
> sim" — os productIds atuais estão corretos; corrigidos apenas os RÓTULOS
> (`product_type: Sleeved Booster` → `Booster Pack` nos 26 SKUs; nomes já eram
> honestos). Nenhum preço de referência mudou. Os 6 blisters de 1 pack ficam
> como estão: o mapeamento blister→"Sleeved Booster Pack" já era decisão
> deliberada do operador (2026-08-15, travada em
> `tests/test_translate_match_roundtrip.py` — o Sleeved Pack do TCGplayer é o
> produto físico do "Blister Unitário"), ou seja, a hipótese de "troca em
> bloco" do §2 estava errada para essa família.

⚠️ Consequência enquanto não decidido: análises técnicas/margens de SKUs
"Sleeved Booster" usam a referência do avulso (mais barata → margens
CONSERVADORAS, nunca infladas — o erro atual é no sentido seguro). Para
análise ad-hoc de um produto Sleeved específico, usar o productId do
Sleeved diretamente (foi o que a análise de 2026-09-01 fez).

## 4. Nota de inteligência de mercado (JTG, 2026-09-01 — candidatos a evento)

Busca dirigida (runbook da camada de análise) achou dois sinais em direções
opostas — **nenhum promovido a evento** (`data/events_pokemon.yaml` segue
vazio; promoção é curadoria manual via `scripts/import_events.py`):

- Daily Card Show aponta o JTG como candidato mais claro a fim de impressão
  em 2026 (sem lista oficial — classe máxima `SINAL_DE_MERCADO`):
  https://dailycardshow.com/content/pokemon/pokemon-sets-out-of-print-2026
- TCG Drop Radar marca o SV09 como "Restocking" (reposições ainda fluindo;
  promover como `restock` elevaria o risco de reprint a ALTO):
  https://tcgdropradar.com/sets/

Coletados em 2026-09-01. Sem anúncio oficial de reprint nem de fim de
impressão — estado `SEM_EVIDENCIA` correto até segunda ordem.

## 5. Fechamento 2026-09-02 — o que cada anúncio da Liga É (prints do operador)

Operador mandou os dois prints da Liga lado a lado (mesmo set, JTG):

| Anúncio Liga | Categoria Liga | Fabricante | Foto | Produto TCGplayer |
|---|---|---|---|---|
| **Blister Unitário** - Escarlate e Violeta 9 - Amigos de Jornada (pcode 133279) | Blisters | Copag | booster dentro de cartela pendurável | **Sleeved Booster Pack** (610934, US$ 9,35) |
| **Booster Avulso** - Escarlate e Violeta 9 - Amigos de Jornada (pcode 133171) | Boosters Avulsos | The Pokémon Company | pacote solto | **Booster Pack** (610935, US$ 6,82) |

Ou seja: a Opção A (§3) e o re-apontamento dos blisters de 2026-08-15 estavam
**os dois certos** — o registry já mapeava JTG corretamente. O que estava
errado era outra coisa:

1. **O Blister Unitário do JTG nunca entrou em scan nenhum** (0 ocorrências em
   todos os `results/unified_*`). Causa: `config.liga.max_products_per_category: 30`
   e a categoria 25 (Blisters) tem 37 produtos EN — o JTG é o 31º da lista
   (sondagem ao vivo 2026-09-02). Corte silencioso, sem aviso no log.
   **Fix:** teto 200 (modo local é grátis) + `[aviso] ... acima do teto ...
   ficaram FORA do scan` no `fetch_listings`. Teste: `tests/test_liga_cap_warning.py`.
2. **Rótulos trocados**: os 6 `*-blister-1pack` (pid Sleeved real) se chamavam
   "Single Pack Blister"; 8 SKUs chamados "Sleeved Booster" apontavam para o
   pacote solto. **Fix:** nome honesto — "Sleeved Booster Pack" só onde o pid é
   o Sleeved; os 8 viram "<Set> Booster Pack". Nenhum productId mudou.
   Teste: `tests/test_sleeved_naming.py`.
3. **Colapso de dois produtos num pid**: meg/par/obf/pal (sets COM Sleeved
   separado no tcgcsv) tinham `blister unitário` nos `type_terms` do pacote
   solto — um Blister Unitário desses sets cairia na referência errada (~30%
   baixa). **Fix:** termo removido nesses 4 (âncora `loose_pack_type`);
   blk/wht/sfa/paf mantêm (sem Sleeved separado, o solto é o único mapeável).

**Backlog (decisão futura):** criar SKU Sleeved para ME/PAR/OBF/PAL/SVI/SSP/
SCR/TEF/TWM/ASR/SIT (pids no §2) **quando** a Liga listar "Blister Unitário"
desses sets — hoje (2026-09-02) só lista para CR/PHF/DRI/JTG/PO/PB, todos já
cobertos.
