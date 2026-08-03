# CHANGELOG — Sealed Arbitrage Scanner

Registro datado de mudanças relevantes. O repo não usa versionamento semântico
(SemVer); as entradas são por data. Fonte única de estado segue o `README.md`.

## 2026-08-03 — Plataforma de colecionáveis: rotas + referência de VENDA (eBay), perfil One Piece e painel local

Evolução pedida pelo operador ("aplicar a ideia da Skip": scanners → plataforma
integrada de arbitragem de selados, informando onde comprar E para onde vender).
Três frentes, todas preservando os invariantes (margem BRUTA fração 0.30, SEM
piso, classificação 100% TCGplayer, nunca inventar preço/URL, entrega via
`scripts/snapshot.py`):

- **Rotas + lado de VENDA (eBay US via Probstein):** `lib/ebay_client.py`
  (Browse API stdlib, category_ids opcional, throttle/retry) +
  `build_ebay_reference.py` (menor anúncio ATIVO plausível por SKU; gate de
  título com os termos do registry + guards não-EN/graded/aberto/lote; lixo
  <50% da ref contado, nunca vencedor; run sem chaves preserva o arquivo
  anterior intacto). Pipeline ganha 5 colunas eBay INFORMATIVAS (CSV 22→27;
  `compute_margin` intocado — margem eBay em função separada;
  `apply_ebay_reference` NUNCA muda classificação, travado em teste). Config
  ganha bloco `route:` (compra → venda, auditável no banner/run_meta.json/
  cabeçalho da entrega). Snapshot: 3º link `[eBay]`, colunas `Ref. eBay (R$)`
  e `Margem vs eBay %`, cabeçalho com Rota + idade/cobertura da referência
  (contrato de `test_snapshot_links` atualizado de propósito). Rótulo duro:
  **pedida, não venda realizada; sem frete; nunca classifica**.
- **Perfil ONE PIECE (expansão de nicho nº 1):** `sku_registry_onepiece.yaml`
  com 83 SKUs 100% de dados reais do tcgcsv cat 68 (gerados por
  `scripts/gen_onepiece_registry.py`, rerunnável; Case/DON!!/Dash/Bonus/lotes
  FORA e contados; autoconsistência 83/83 + anti-contaminação cross-game
  travadas em teste; colisão PRB-01/PRB-02 achada e corrigida). `--game
  {pokemon,onepiece}` nos 2 runners + `run_liga_local` + snapshot; resultados
  em `results/onepiece/`; `config_onepiece.yaml` com `liga.categorias` VAZIO
  de propósito (falha honesta até validar o site OP — `SETUP-VALIDACAO.md §B`);
  `data/us_reference_onepiece.json` commitada (83/83 nas bandas OP novas).
  liga_adapter parametrizado por perfil (base_url/categorias/traduções) com
  defaults Pokémon byte-idênticos.
- **Painel local read-only (`panel.py`, FastAPI :8078):** explorar os deals do
  último scan de cada jogo no navegador (filtros + 3 links por produto), com
  `/api/products` servido pelo MESMO `group_products` da entrega (fonte
  única). Nenhum endpoint de escrita; POST /scan é backlog declarado. Deps:
  fastapi/uvicorn/httpx2.
- Extras: refresh da `us_reference.json` (estava 31d vencida; 202/205),
  fix da bomba-relógio de data no `test_price_guard`, runbook
  `SETUP-VALIDACAO.md` (chaves eBay §A · Liga OP §B/§C · painel §D).
- **Validação ao vivo do §A (chaves eBay, mesmo dia):** o primeiro probe real
  da Browse API revelou uma classe de lixo que o gate não barrava por título —
  **code cards digitais** (códigos do TCG Online/Live a ~US$0,99 citando
  set+tipo, ex. "Surging Sparks Elite Trainer Box Code Card E-Delivery"), que
  em SKU barato ou sem referência TCG escapariam do junk-ratio. Gate ganhou
  `DIGITAL_TOKENS` (code card/online code/digital/e-delivery/ptcgo/ptcgl/tcg
  live…), travado em `test_gate_rejects_digital_code_cards`.
  Suíte: 354 → **436 testes**, 100% offline.
- **Backlog registrado:** PriceCharting (vendas realizadas) como 2ª referência
  de venda; join do score de longo prazo do pokemon-longterm-outlook por
  productId; selados como 5ª fonte do integrated-scanner; pinagem de categoria
  eBay via Taxonomy API; cobertura OP em OLX/ML/Amazon; perfis Dragon Ball/
  Lorcana; POST /scan no painel.

## 2026-06-27 — Gap 3ª leva: +4 ETBs por personagem do ME01 (Mega Lucario/Gardevoir)

Mapeamento per-produto no tcgcsv das "collection boxes de personagem" do gap
(handoff §5c). Resultado honesto da varredura:

- **Adicionados (refs limpas no tcgcsv, group 24380 = ME01 Mega Evolution):**
  `meg-etb-lucario` (pid 648394, $123,46), `meg-etb-gardevoir` (644279, $119,44),
  `meg-etb-pc-lucario` (644282, $322,09 — Pokémon Center exclusiva),
  `meg-etb-pc-gardevoir` (648415, $223,41). O Mega Lucario ETB ($123) era
  citado no handoff como gap conhecido. **Não havia meg-etb genérico → sem
  colisão.** Cada um fixado pelo personagem em `requires_terms`; a variante PC
  separa por `requires "pokemon center"` (padrão pre-etb-en vs pre-etb-pc-en).
  Preços dentro da sanity-band ETB (25–950). 122 SKUs (era 118); 201 testes (+5).
- **Confirmado FORA do tcgcsv (não adicionados — `nunca inventar preço`):** as
  caixas de personagem nomeadas no gap (Mewtwo Rocket, Garchomp Cynthia,
  Charizard Especial, Dia de Pokémon 2026, Zacian Lupo, Bellibolt Kissera,
  Salamence/Reshiram) **não existem como produto SELADO no tcgcsv** — só como
  cartas avulsas promo (fora do escopo selado). Sem referência limpa → sem SKU.
- **Cobertos pela SKU genérica (sem novo SKU):** Mega Heroes Mini Tin por
  personagem (Lucario/Gardevoir/Kangaskhan/Latias/Venusaur, ~$20 uniforme) — o
  `meg-mini-tin` genérico já casa e o preço não varia por personagem.
- **Achados mas adiados (ref. existe, faltam títulos reais da Liga p/ confirmar
  match):** Destined Rivals 3-Pack Blister [Kangaskhan] (625683, $45,21);
  Paldean Fates Tin [Charizard ex] (528056, $188,38 / Intl 528063, $132,05 —
  Paldean Fates ainda não tem nenhum SKU). Documentados no handoff §5c.

## 2026-06-27 — Gap de produtos EXISTENTES: nomes PT de set faltando nos `set_terms`

Auditoria de cobertura PT em TODO o registry (a Liga/OLX/ML são marketplaces BR →
muitos títulos usam o nome PT do set; SKU só com nome EN perdia essas ofertas em
silêncio — mesma classe de bug do ME05/"Escuridão Absoluta" e do side-finding
`ah-*` do handoff de 2026-06-26). **Só `set_terms`; nenhum product_id/preço novo
→ `us_reference` intacto.**

- **8 sets que estavam SEM nenhum alias PT (NONE) → agora cobertos:** Surging Sparks
  (`fagulhas impetuosas`), Perfect Order (`equilíbrio perfeito` + `megaevolução 3`),
  Chaos Rising (`caos ascendente` + `megaevolução 4`), Phantasmal Flames
  (`fogo fantasmagórico`), Destined Rivals (`rivais predestinados`), Journey Together
  (`amigos de jornada`), Temporal Forces (`forças temporais`), Twilight Masquerade
  (`máscaras do crepúsculo`).
- **4 sets PARCIAIS → consistência interna:** o alias PT já vivo em alguns SKUs do
  set foi propagado aos irmãos que faltavam — Ascended Heroes (`heróis excelsos`
  + `megaevolução 2.5` nos etb/bundle/pack/mini-tin/megaex/poster), Prismatic
  Evolutions (`evoluções prismáticas`), Stellar Crown (`coroa estelar` no box/pack).
- **Fonte dos nomes PT:** mapa curado de `scripts/expand_registry_modern.py` — a
  MESMA fonte cujos termos de Ascended Heroes/Pitch Black já estavam vivos e
  validados no registry. **Nada deduzido por LLM** (regra anti-alucinação).
- **Precisão > cobertura, decisões de freio:**
  - `megaevolução 2` (Phantasmal Flames) **NÃO** entrou: no match por palavra-inteira
    `megaevolução 2` é sub-string de um título `Megaevolução 2.5` (Ascended Heroes)
    → roubaria a oferta AH. PFL casa pelo nome PT; a numeração ME2 fica pra quando o
    matcher distinguir 2 de 2.5. Travado em teste.
  - SV 151 **não** ganhou `escarlate e violeta 151`: o set_term `151` já casa todo
    título do set (o número está sempre presente) → zero ganho de cobertura.
  - `unova` (Black Bolt) / `mega heroes` (Mega Evolution) **não** propagados: são
    branding de PRODUTO ("Unova Mini Tin"/"Mega Heroes Mini Tin"), não nome de set —
    propagá-los a box/bundle casaria errado.
- **Garantias:** varredura de colisão cross-set em TODO o registry = limpa (nenhum
  set_term é sub-string de palavra-inteira de outro set). +16 testes
  (`tests/test_matching.py`): cada nome PT recupera o SKU certo, nome EN sem
  regressão, e o guard AH-2.5 × PFL. **196 testes** (era 180).

## 2026-06-21 — Gate de CONDIÇÃO (selado vs aberto/usado) + análise de fontes BR

Fecha uma lacuna LATENTE achada na auditoria das fontes BR (eu + agente revisor):
o scanner **não distinguia selado de aberto/usado** — só rejeitava single/acessório/
idioma. Funcionava por sorte (Liga/OLX/ML são "new-first"); um box aberto/sem cartas
casado a um SKU selado = margem fantasma.

- **Gate GLOBAL (todas as fontes):** `looks_used()` — título com sinal explícito de
  aberto/usado/incompleto ("aberto", "sem cartas", "só a caixa", "vazio", "incompleto"...)
  → 0 candidatos. Validado **zero-regressão**: 0 de 818 matches reais têm esses tokens.
- **Gate POR-FONTE (`sealed_only`):** `looks_sealed()` + `config.scope.sealed_only_sources`.
  Fonte secondhand-first (ex.: **Enjoei**) exige PROVA de lacre ("lacrado"/"selado"/
  "sealed") — default "usado até provar lacre". Fontes new-first (liga/olx/ml/amazon)
  ficam inalteradas (não exigem token de lacre). Enjoei já listado p/ quando o adapter
  for construído (inócuo enquanto não é fonte).
- Motivos de rejeição novos: `produto_aberto_usado`, `lacre_nao_confirmado`.
- +7 testes (`tests/test_condition_gate.py`); 150 no total. **0 matches reais perdidos.**

**Análise de fontes BR (decisão conjunta, não implementado além do gate):** Liga =
motor (64 GREEN/scan, imports EN); OLX = gemas de vendedor casual (a Stellar Crown
93,6% foi OLX); ML = precificado a mercado (mediana −18%, ~0 GREEN — realidade, não
bug; MANTER como control group barato $0); Amazon = opt-in retail (~0 yield esperado).
**Enjoei probado ao vivo:** scrapável ($0 browser) mas pende PT-Copag + ruído (busca
"ingles" traz cursos de inglês) → baixo valor EN; só vale COM o gate de condição (feito).
ASI-Evolve = ferramenta errada (matcher já no ótimo, ver test_matcher_regression).

## 2026-06-21 — Guards FP-safe da referência US (parecer de revisor)

Defendem o modo de falha histórico — referência US errada/velha inflando margem
em GREEN falso (o caso dos tins premium, generalizado) — SEM tocar na precisão do
match. Ambos só REDUZEM falsos positivos; nunca criam um deal.

- **Sanity-band por tipo (`build_us_reference.py`):** preço fora da faixa
  plausível do `product_type` (ex.: um SKU "Mini Tin" pegando um bundle de US$230
  num refresh, ou um booster avulso pegando US$0,50 de code-card) é EXCLUÍDO —
  o SKU fica sem referência → o scanner classifica `sem_referencia_us` (RED
  honesto), nunca um deal fabricado. Faixas generosas (`SANITY_BANDS_USD`): só
  pegam erro grosseiro, validado contra os preços reais 2026-06 (0 exclusões
  legítimas; 104/105 seguem precificados).
- **Freshness guard (`run()` + `reference_age_days`):** referência US além da
  validade (`deal_criteria.max_reference_age_days`, default 14d) rebaixa GREEN →
  YELLOW (revisão manual) com motivo auditável. O fluxo canônico refresca antes
  do scan (tcgcsv diário), então só dispara em scan sem refresh.
- Contexto: o mapeamento de tins foi AUDITADO (eu + agente revisor) e está
  correto/conservador — cada set aponta pra variante de mini-tin mais barata;
  NENHUM remap necessário. Loosening do termo "mini" foi REJEITADO (reabre o FP).
  Estes guards foram a melhoria FP-safe que o revisor recomendou no lugar.
- +6 testes (`tests/test_reference_guards.py`); 140 no total.

## 2026-06-20 — Entrega AGRUPADA POR PRODUTO (modelo MYP) com unidades e dupla referência

- **`scripts/snapshot.py`**: a entrega deixa de ser uma lista plana de anúncios e
  passa a ser **consolidada por produto** (SKU canônico). Numa run real, 399
  anúncios → 45 produtos (o mesmo Booster Bundle aparecia em 18 linhas).
- Cada produto traz, no estilo da tabela do MYP:
  - **Ref. Nacional (R$)** = menor preço BR disponível agora (melhor entrada) +
    `mediana BR` no detalhamento (contexto do mercado nacional);
  - **Ref. TCG (R$)** = preço TCGPlayer Market (US$→R$), a referência internacional;
  - **Margem bruta %** e **Δ R$/unid** recalculados na Ref. Nacional vs Ref. TCG;
  - **Qtd total disp.** (soma do estoque de todas as ofertas) + **Nº de ofertas**;
  - coluna `Links` combinada `[oferta](BR mais barato) · [TCG](TCGplayer)`.
- Novo bloco **"Quantidades e preços disponíveis por unidade"**: por produto
  acionável, a escada de ofertas — cada anúncio com vendedor, fonte, **quantidade
  disponível** e **preço BR**, da unidade mais barata pra mais cara. O operador
  importa em LOTE e quer ver cada unidade e seu preço.
- **Ranking completo** também agrupado por produto (antes ~334 linhas de anúncio →
  agora 45 linhas de produto).
- Status do produto = melhor bucket entre suas ofertas (GREEN > YELLOW > RED);
  flag ⚠️ se qualquer oferta exigir conferência manual.
- Helpers preservados (`links_cell`, `fmt_*`, `tcg_link`) → testes de links seguem
  verdes; novos testes em `tests/test_snapshot_grouping.py` (131 no total).
- _Nota:_ a referência US de selados segue em **tcgcsv.com** (TCGPlayer Market).
  A API `pokemontcg.io` cobre só **singles**, não produtos selados — por isso não
  entra aqui (usá-la pra selado daria preço de carta avulsa, não da caixa).

## 2026-06-17 — Entrega via `snapshot.py` vira convenção OBRIGATÓRIA

- **`scripts/snapshot.py` reescrito** pra ser o gerador canônico da entrega:
  - Passa a ler o **`unified_deals.csv`** (saída de `run_all_sources.py`), que é
    o que o orquestrador realmente produz — antes lia só os CSV por bucket
    (`real_opportunities.csv` etc.) que o `run_all_sources.py` **não** escreve,
    forçando tabela montada à mão. Modo legado por-bucket preservado via `--all`.
  - **Adiciona a coluna `Qtd disponível`** (invariante #2) na tabela de entrega —
    estava ausente.
  - Mantém os **dois links clicáveis verificáveis** por linha: anúncio BR (`URL`)
    + página TCGPlayer de referência (`tcgplayer_product_id` do registry).
  - Nova seção **🟢🟡 Deals acionáveis** com **todos** os GREEN/YELLOW (sem curar)
    + **flag ⚠️** e motivo nos deals que precisam de conferência manual (match
    ambíguo YELLOW / margem-variante anômala).
  - `--scan-dir` aponta uma run específica; default = `results/unified_*` mais recente.
- **README invariante #7 reescrito**: entrega = tabela no chat **gerada via
  `snapshot.py`, NUNCA à mão**; nova seção "Entrega da tabela no chat (OBRIGATÓRIO
  via snapshot.py)" com comando literal, colunas, links e regra de XLSX-sob-demanda.
  `snapshot.py` entra como passo 3 da sequência canônica; XLSX vira passo 4 opcional.
- **RUNBOOK** atualizado: entrega padrão = tabela no chat via `snapshot.py`; XLSX
  condensado/Drive passam a ser explicitamente "só quando o operador pedir o arquivo".
- XLSX sob demanda (`build_delivery_xlsx.py`) **preservado** — o selado é o caso de
  uso real em que o operador pede o arquivo pra importar em lote.
