# CLAUDE.md — sealed-scanner

Instruções para qualquer sessão Claude Code (local ou nuvem) que trabalhe neste repo.

**Plataforma de arbitragem de produtos SELADOS de colecionáveis** (booster box,
ETB, fat pack, lata, blister, kit, pré-lançamento…): compara ofertas em
marketplaces BR (Liga, OLX, MercadoLivre, Amazon BR) com a referência US do
TCGplayer, classifica por margem bruta e — desde 2026-08-03 — mostra também a
**referência do lado de VENDA** (menor anúncio ativo no eBay US, onde o operador
vende via Probstein) e a **ROTA** (onde comprar → para onde vender) de cada run.
Suporta **perfis por JOGO** (`--game`): **Pokémon** (default, comportamento
histórico) e **One Piece TCG** (primeira expansão de nicho). Repo GitHub:
`matheuscllm-lgtm/sealed-scanner`; pasta local no PC do operador:
`C:\Users\mathe\sealed-arbitrage-scanner`.

## 🛰️ Convenções da frota (cross-scanner)

> **Manual completo** (repo privado): https://github.com/matheuscllm-lgtm/scanners-commons — erros comuns, referências de preço, chaves, GitHub Actions e modelo de entrega de TODOS os scanners. Cópia-mestra local (PC do operador): `C:\Users\mathe\scanners-commons\`.

Invariantes que valem para TODOS os scanners:

- **Margem BRUTA, mínimo 30%** — só `(revenda − compra)/compra`, sem nenhuma taxa embutida (frete, cartão, IOF — o operador calcula por fora).
- **Piso de relevância R$50 (~US$10) — SÓ para cartas avulsas (singles).** Produtos SELADOS não têm piso (decisão do operador, 2026-06-27); lá o único critério é a margem ≥30%.
- **Só Near Mint** — condição por match EXATO `== "NM"`, nunca substring (já vazou SP).
- **Nunca inventar preço** — fonte falhou → marca fallback/erro e segue; jamais fabrica número.
- **Nunca recomendar compra** — o scanner reporta margem, flags e fontes; a decisão de capital é do operador.
- **Entrega = tabela markdown no chat** (nunca XLSX/CSV por padrão), gerada pela ferramenta do repo — nunca montada à mão —, mostrando TODAS as linhas (aprovadas + rejeitadas). Coluna `Carta` = nome + número; coluna `Links` combinada = `[oferta](url) · [TCG/referência](url)`.
- ⚠️ **Convenção de threshold:** percentual inteiro (`30`) = MYP, Liga, eBay; fração (`0.30`) = CardTrader, COMC, Selados.

Erros recorrentes (3 famílias — detalhe no manual):

1. **Segredo/ambiente:** BOM/zero-width numa chave → crash latin-1 no header → scan "verde mas vazio". Setar sem BOM (`printf '%s' 'KEY' | gh secret set`) **e** sanitizar ao ler no código (`.strip()` NÃO tira BOM).
2. **Git:** branch ou `main` local defasado por squash-merge PARECE pendência. O teste real de "já mergeado" é `git diff --stat origin/main <branch>` estar vazio (não `git merge-base`).
3. **Honestidade de preço:** inflação de referência, fallback tratado como real, NM frouxo → sempre validar versão/condição e rotular fallback.

**Este scanner (SELADOS):** referência de preço que CLASSIFICA = TCGplayer US (preço Market do selado, via espelho `tcgcsv.com`; Pokémon = categoria 3, One Piece = categoria 68); referência de VENDA informativa = eBay US Browse API (menor anúncio ativo — pedida, nunca classifica); chaves = `FIRECRAWL_API_KEY` (no PC; rota Firecrawl fura o WAF da OLX) e `EBAY_CLIENT_ID`/`EBAY_CLIENT_SECRET` (opcionais — só p/ a referência de venda; sem elas nada quebra).

> **Como os invariantes de SINGLES se traduzem para SELADOS** (o bloco acima é o
> texto canônico da frota; dois bullets dele são específicos de cartas avulsas e
> têm equivalente próprio aqui — não é contradição):
>
> - **"Só Near Mint"** → selado não tem condição NM. O equivalente deste repo é o
>   **gate de CONDIÇÃO selado-vs-aberto/usado** (auditoria com o agente revisor, 2026-06-21;
>   travado em `tests/test_condition_gate.py`): título com sinal explícito de
>   aberto/usado/incompleto ("aberto", "sem cartas", "só a caixa", "vazio"…)
>   nunca casa SKU selado, em nenhuma fonte.
> - **"Coluna `Carta` = nome + número"** → a entrega deste scanner é **agrupada
>   por produto/SKU canônico** (nome do produto + tipo), não por carta com número
>   de coleção. A coluna `Links` combinada (`[oferta](url) · [TCG](url)`) vale
>   igual. Ver seção 📤 abaixo.

## Regras invioláveis deste repo

1. **SEM PISO DE PREÇO** (`config.yaml: filters.min_brazil_price_brl: 0`, decisão
   do operador 2026-06-27): selado não tem piso; o único critério de GREEN é
   margem bruta ≥30% (`deal_criteria.min_total_margin_pct`, **fração** `0.30`).
   **NÃO reintroduzir** o piso R$50 das cartas avulsas aqui — ele vale só para
   singles. Não re-perguntar. Preço 0/malformado continua RED via o zero-guard de
   `compute_margin` (margem 0% < 30%), nunca GREEN.
2. **Margem bruta pura, threshold em FRAÇÃO** (`0.30` = 30%) — convenção
   Selados/CardTrader/COMC; MYP/Liga/eBay usam percentual inteiro. Nenhuma taxa
   embutida: custos operacionais/frete foram REMOVIDOS do scanner por decisão do
   operador (só margem bruta, sem margem líquida; taxas por fora, na mão).
3. **Teto de plausibilidade: margem > 200% → RED `margem_anomala`**
   (`deal_criteria.review_above_margin_pct: 2.0`). Margem alta demais em selado
   quase sempre é artefato de match (ex.: fichário/álbum avulso ~R$230 casando o
   SKU "151 Binder Collection" US$240 = 432% fantasma). Match HIGH acima do teto
   NÃO vira GREEN — cai em RED auditável para verificação manual.
4. **Referência US velha rebaixa GREEN → YELLOW**
   (`deal_criteria.max_reference_age_days: 14`). O fluxo canônico refresca a
   referência antes do scan (tcgcsv atualiza diário), então só dispara em scan
   sem refresh.
5. **YELLOW nunca é faixa de margem** — vem de match ambíguo (1 anúncio casa
   2+ SKUs) ou do rebaixamento GREEN→YELLOW por referência velha (regra 4).
   A classificação por margem é só GREEN/RED.
6. **Exclusões documentadas do registry** (decisões do operador, não re-perguntar):
   - **Blister Duplo Heróis Excelsos [Tangela] e [Komala]** ficam FORA (decisão
     2026-07-03) — o set ASC (group tcgcsv 24541) não tem NENHUM blister selado
     no TCGplayer, logo não há referência US possível e o invariante "nunca
     inventar preço" ganha. Se o tcgcsv um dia listar, cadastrar.
   - **Battle Decks/Baralhos** também seguem fora (decisão 2026-07-02).
   - A cobertura do catálogo de selados da Liga é travada por
     `tests/test_gap_loose_packs.py` (**127 títulos reais do operador** → match
     único, exceto essa lista fechada).
7. **A referência eBay é INFORMATIVA e NUNCA classifica** (2026-08-03): as
   colunas `Ref. eBay (R$)`/`Margem vs eBay %` e o link `[eBay]` vêm do menor
   anúncio ATIVO no eBay US (**pedida, não venda realizada**; sem frete) e
   jamais mudam GREEN/YELLOW/RED, margem oficial, bucket ou risco — travado em
   teste (`test_ebay_enrichment.py`: vereditos byte-idênticos com e sem ela).
   `compute_margin` segue retornando exatamente as 4 chaves de sempre.
8. **Run degradado nunca sobrescreve referência anterior** (2026-08-03):
   `build_ebay_reference.py` sem `EBAY_CLIENT_ID/SECRET` avisa alto, retorna 0
   e NÃO TOCA no arquivo anterior; maioria de erros → aborta sem gravar
   (espelho do PR #19 do ebay-arbitrage-scanner; travado em teste).

## Como rodar (skill `sealed-scan` — MANDATÓRIO)

> Caminho único, detalhado na skill do repo `.claude/skills/sealed-scan/SKILL.md`
> (canônica; espelhada em `~/.claude/skills/sealed-scan/` no PC do operador pra
> disparar fora do repo — se editar uma, sincronize a outra). Resumo:

- **Pergunte a fonte primeiro** (menu na skill): Liga ($0, default recomendado) /
  Liga+OLX+ML / Amazon (opt-in, ~51 créditos Firecrawl — avisar custo) / todas.
- **Rodar (Liga é local-only, PC do operador, janela do Chrome VISÍVEL — CF dá
  0 produtos em headless):**

  ```bash
  python run_liga_local.py            # só Liga; roda via run_all_sources.py --sources liga
  python run_all_sources.py --sources liga,olx,mercadolivre   # multi-fonte (default)
  python run_all_sources.py --sources amazon,liga             # Amazon é opt-in
  python run_liga_local.py --game onepiece                    # perfil One Piece (ver 🎴)
  ```

  `run_liga_local.py` usa a saída canônica `results/[<jogo>/]unified_*` (a que o
  snapshot lê) e já gera as notas markdown no fim (snapshot é default;
  `--no-snapshot` / `--no-janela` só para debug do coletor). Flags úteis:
  `--game {pokemon,onepiece}` (default pokemon — define config/registry/
  referências/raiz de resultados), `--categorias 10,27`, `--max-por-categoria N`,
  `--skip-check`. O orquestrador aceita `--game`, `--config`, `--registry` e
  `--mock` (fixture JSON de `mock_data/`; a de OP é `onepiece_listings.json`).
  Refresh opcional da referência de VENDA: `python build_ebay_reference.py`
  (exige chaves eBay — `SETUP-VALIDACAO.md §A`; sem elas nada quebra).
- **Setup 1ª vez:** `pip install -r requirements.txt` (+ `patchright` e Google
  Chrome instalado para o modo local da Liga). Guia passo a passo do PC do
  operador: `SETUP-WINDOWS.md`. Nuvem/servidor: a Liga bloqueia IP de datacenter
  no Cloudflare — só via `liga.mode: scraperapi` no `config.yaml`
  (`SCRAPERAPI_KEY` em `.env`/env var; domínio "protected" = ~25–50 créditos por
  render JS — dose com cuidado). Coleta ao vivo canônica é LOCAL, no PC do
  operador.
- Extras do repo: `.claude/commands/auto.md` e `.claude/commands/goal.md`
  (skills de execução autônoma/metas) e `.claude/agents/sealed-reviewer.md`
  (agente revisor). Sondas manuais: `probe_liga_sealed.py`, `probe_olx_local.py`.

## 📤 Entrega de resultados (MANDATÓRIO)

- **Entrega = colar VERBATIM o markdown do `scripts/snapshot.py` no chat.**
  NUNCA montar tabela à mão, nunca XLSX/CSV por padrão (arquivo só se o operador
  pedir explicitamente), mostrar TODAS as linhas (acionáveis GREEN+YELLOW **e** o
  ranking completo com os RED).
- Formato = modelo MYP cross-scanner (padrão do operador, 2026-06-20) **adaptado
  a selados**: tabela **agrupada por produto/SKU canônico** (não lista plana de
  anúncios), com status 🟢 GREEN / 🟡 YELLOW / 🔴 RED, Ref. Nacional (R$),
  Ref. TCG (US$→R$), **Ref. eBay (R$) + Margem vs eBay % (informativas, lado de
  venda)** e Margem bruta % por linha; coluna `Links` =
  `[oferta](url) · [TCG](url) · [eBay](url)` (o `[eBay]` só quando a referência
  de venda cobriu o SKU). Cabeçalho traz a **Rota** e a idade/cobertura da
  referência de venda. Formato travado em `tests/test_snapshot_*` (contrato dos
  3 links atualizado de propósito em 2026-08-03).
- O `scripts/snapshot.py` roda sobre o `unified_deals.csv` da run
  (`results/[<jogo>/]unified_*/`); o `run_liga_local.py` já o dispara por
  default. **Scan de One Piece exige `--game onepiece` TAMBÉM no snapshot**
  (senão a entrega sai do último scan Pokémon). `scripts/build_delivery_xlsx.py`
  gera o XLSX de apoio — só sob pedido.
- Lembrete: selado **não tem piso de preço** (regra inviolável nº 1 acima).

## 🧭 Rotas e referência de VENDA (eBay) — 2026-08-03

> **Em uma frase:** cada scan agora declara a **rota** (onde comprar → para
> onde vender) e mostra, ao lado da referência TCGplayer, **quanto o produto
> está pedindo no eBay US** — o mercado onde o operador de fato vende, via
> Probstein (consignação = uma empresa vende por você no eBay).

- **Rota** = bloco `route:` do config (labels auditáveis; ex.: "BR (Liga) →
  venda eBay US via Probstein · classificação vs TCGplayer"). É DADO, não
  comportamento: aparece no banner, no sidecar `run_meta.json` do run e no
  cabeçalho da entrega — nada de matching/margem/classificação muda por rota.
- **Referência de venda** = `data/ebay_reference.json` (gitignored), gerada por
  `build_ebay_reference.py`: menor anúncio **ATIVO** plausível por SKU no eBay
  US (Buy It Now, item nos EUA, sem frete), via Browse API oficial (grátis,
  5.000 chamadas/dia; cliente stdlib em `lib/ebay_client.py`). Gate de título
  estrito (termos do PRÓPRIO registry + não-EN + graded + aberto/usado +
  lote/case) e guard de anúncio-lixo (<50% da ref TCG = contado, nunca
  vencedor). SEM filtro de categoria eBay de propósito (a categoria de singles
  183454 é errada p/ selado e não chutamos outra — pinagem via Taxonomy API é
  backlog).
- **Vocabulário honesto (não confundir):** anúncio ativo é **PEDIDA** (o que
  vendedores estão pedindo), não **venda realizada** (o que compradores
  pagaram — a API de vendidos do eBay é restrita). Colunas/link eBay são
  informativos; ver regras invioláveis nº 7 e 8.
- Validade: `max_age_days: 7` no config — vencida só AVISA (nunca rebaixa).
- Setup das chaves (uma vez, ~5 min, grátis): `SETUP-VALIDACAO.md §A`.

## 🎴 Perfis por jogo (Pokémon / One Piece) — 2026-08-03

> **Em uma frase:** o MESMO pipeline roda mais de um jogo — o que muda por
> jogo são só os DADOS (config + registry + referências + raiz de resultados),
> nunca a lógica (zero condicional de jogo em matcher/margem/classificação).

| — | Pokémon (default) | One Piece |
|---|---|---|
| Config | `config.yaml` | `config_onepiece.yaml` |
| Registry | `sku_registry.yaml` (205 SKUs) | `sku_registry_onepiece.yaml` (83 SKUs seed) |
| Referência US | `data/us_reference.json` (tcgcsv **cat 3**) | `data/us_reference_onepiece.json` (tcgcsv **cat 68**) |
| Referência venda | `data/ebay_reference.json` | `data/ebay_reference_onepiece.json` |
| Resultados | `results/` (histórico) | `results/onepiece/` |
| Fontes default | liga, olx, mercadolivre | **só liga** (OLX/ML/Amazon têm queries Pokémon — backlog) |
| Site da Liga | ligapokemon.com.br | ligaonepiece.com.br (mesma plataforma LigaMagic) |

- Seleção: `--game {pokemon,onepiece}` nos 2 runners, no `run_liga_local.py` e
  no `scripts/snapshot.py` (mesma flag nos DOIS passos do fluxo!). Sem a flag,
  vale `game:` do config; sem nada, Pokémon.
- **Registry OP = 100% dados reais do tcgcsv** (gerado/ampliável por
  `scripts/gen_onepiece_registry.py`): escopo seed = PRB-01 (2024-11) → OP17;
  Case/DON!!/Dash/Bonus/lotes ficam FORA e contados. **ZERO alias PT de set**
  (a Bandai não localiza nomes; aliases PT só entram com títulos reais da Liga
  OP — nunca deduzidos, lição ASI-Evolve). Autoconsistência 83/83 + anti-
  contaminação cross-game travadas em `tests/test_onepiece_registry.py`.
- ✅ **Coletor OP VALIDADO no PC do operador (2026-08-03, §B):** categorias do
  site OP = `10` Caixas de Pacotes (Booster Box/EB Box), `21` Pacotes Avulsos,
  `28` Caixas Colecionáveis (é onde vivem os **Double Pack DP-xx**, junto de
  Illustration Box/Gift Collection que ficam sem match de propósito), `36`
  Decks Iniciais; `38` Kits Colecionáveis e `24` Latas ficaram FORA (nenhum SKU
  no registry). Lembrete permanente: o namespace `categ=N` é POR SITE (no site
  Pokémon 27=ETB; no tcgcsv 27=Dragon Ball Masters — nunca confundir). Os
  templates de preço do site Pokémon funcionaram inalterados no site OP, e
  `type_translate` ganhou `"Deck Inicial" → "Starter Deck"`. Smoke offline:
  `python run_all_sources.py --game onepiece --sources mock --mock
  mock_data/onepiece_listings.json`.

## 📈 Análise técnica US (hold vs sell) — 2026-08-29

> **Em uma frase:** depois do scan da Liga, `python analyze_sealed.py` olha o
> mercado AMERICANO de cada SKU casado e responde — com números, fontes e
> datas — **vender ao chegar, segurar 30/60/90 dias além do ciclo (~24d),
> evitar a compra, ou dados insuficientes**. Motivação do operador: evitar
> venda prematura. Doc canônica: `ANALISE-TECNICA.md`.

Regras duras (travadas em teste — `tests/test_analysis_*`):

- **Camada INFORMATIVA e pós-scan**: NÃO toca `classify`/`compute_margin`/
  `CSV_COLUMNS` nem GREEN/YELLOW/RED; o `unified_deals.csv` sai byte-idêntico
  com ou sem análise (`test_analysis_noninterference.py`). Falha da análise
  nunca derruba o scan (hook do `run_liga_local.py` só avisa; `--no-analise`
  desliga; `analysis.enabled` no config).
- **Rótulos NEUTROS** (classificação técnica): 🟢 `JANELA_VENDA` ·
  🔵 `MANTER_30/60/90D` · ⛔ `EVITAR_COMPRA` · ⚪ `DADOS_INSUFICIENTES` —
  decisão de capital é do operador, sempre.
- **Nunca estima no chute**: cenários/probabilidades derivam de COMPARÁVEIS
  reais (arquivo diário do tcgcsv desde 2024-02-08, por `tcgplayer_product_id`
  — port `lib/tcgcsv_history.py` do pokemon-longterm-outlook) + regras
  documentadas; coorte < mínimo → DADOS_INSUFICIENTES. Ausência de dado nunca
  vira evidência favorável; `SEM_EVIDENCIA` de reprint ≠ risco baixo;
  "esgotado" ≠ descontinuado.
- **Financeiro simplificado** (operador 2026-08-29): `receita_liquida =
  venda × net_factor` (0,70 configurável — custos agregados por fora);
  `valor_de_esperar = lucro_esperado − lucro_hoje − custo_capital(dias extras)`.
  MANTER só com valor de esperar positivo.
- **5 sinais SEPARADOS** (cada um com fonte+data+confiança): tendência de
  preço (tcgcsv + Terapeak) · volume/liquidez (SÓ vendas — Market Price nunca
  mede volume) · evolução da oferta (snapshots de ativos eBay; <2 pontos =
  `HISTORICO_INSUFICIENTE`) · reprint/restock (eventos curados
  `data/events_*.yaml` + estrutural) · chases (indicador auxiliar).
- **eBay Sold**: sem API (restrita). Caminho oficial validado pelo operador
  (2026-08-29): `scripts/terapeak_scrape.js` (console da aba Sold do Product
  Research — a UI NÃO tem export nem seller) → `scripts/import_terapeak.py`
  (seller via Browse `getItem` + cache; encerrado >90d fica sem seller →
  captura mensal). **Sales sheets da Probstein NÃO são usadas** (decisão
  2026-08-29).
- **Entrega**: a MESMA de sempre — o `scripts/snapshot.py` ganha a **3ª tabela
  "Decisão de venda"** quando existe análise do MESMO scan (sem artefato =
  saída idêntica à histórica). Detalhe/reimpressão:
  `scripts/analysis_report.py`; painel ganhou a aba "Análise" (`/api/analysis`).
- **Previsão-vs-realidade**: toda análise loga previsões
  (`data/forecasts/*.jsonl`); `scripts/evaluate_forecasts.py` compara com o
  preço realizado do arquivo (retroativo) — hit-rate/erro calibram os
  percentis no config.
- Dados novos: `data/set_meta*.json` (publishedOn REAL por group_id —
  `build_set_meta.py`; versionado) e `data/events_*.yaml` (curadoria com fonte
  obrigatória; versionado); séries/imports/caches em `data/history|forecasts|
  cache|terapeak` são gitignored. Config: bloco `analysis:` (Pokémon ligado;
  **One Piece nasce `enabled: false`** até calibrar). `--mock` roda um exemplo
  completo com DADOS SIMULADOS rotulados.

## 🖥️ Painel local (somente leitura) — 2026-08-03

```bash
python -m uvicorn panel:app --host 127.0.0.1 --port 8078   # abra http://127.0.0.1:8078
```

Uma "tomada" HTTP local (padrão do api.py do integrated-scanner) para explorar
os deals do último scan de cada jogo no navegador: filtros por status/margem/
busca, agrupado por produto, 3 links por linha e faixa de status com idade das
referências. `/api/products` é servido pelo MESMO `group_products` da entrega —
números idênticos por construção. **Só leitura** (nenhum endpoint escreve;
disparar scan pelo painel é backlog de propósito — a Liga é headful/local). A
entrega oficial continua sendo a tabela do `scripts/snapshot.py` no chat; o
painel nunca recomenda compra. Endpoints: `/` (página), `/health`, `/api/deals`,
`/api/products`, `/api/status`, `/api/routes`, `/docs` (Swagger).

## Testes

```bash
python -m pytest -q     # 597 testes (verificado 2026-08-30), 100% offline
```

- A suíte roda inteira sem rede/credencial/browser: adapters testados contra
  fixtures HTML fixas em `tests/fixtures/` (versionadas de propósito para travar
  seletores). `pytest.ini` restringe a coleta a `tests/` (os `probe_*.py` /
  `run_*.py` da raiz são run-scripts, não testes); `conftest.py` põe a raiz no
  `sys.path`.
- **CI:** `.github/workflows/tests.yml` (job `pytest`, Python 3.12,
  ubuntu-latest) roda em push na `main`, em todo PR e via dispatch. É CI de repo
  público: **sem secrets, sem rede, sem browser — manter assim** (não adicionar
  steps que exijam credencial ou acesso externo).

## Arquitetura

```
sealed_arbitrage_scanner.py  pipeline: match título↔SKU + gate de condição + compute_margin (zero-guard) +
                             classificação GREEN/YELLOW/RED + enriquecimento eBay pós-classify (informativo)
                             + GAME_PROFILES/resolve_game (perfis por jogo)
run_all_sources.py           orquestrador multi-fonte (--game; default_sources do perfil; amazon opt-in)
                             → results/[<jogo>/]unified_*/ + sidecar run_meta.json (rota + referências)
run_liga_local.py            atalho canônico do scan Liga local (--game; Chrome headful + snapshot no fim)
liga_adapter.py              plataforma LigaMagic (patchright + Chrome headful; modo scraperapi p/ servidor);
                             parametrizado por PERFIL (base_url/categorias/traduções; defaults = Liga Pokémon)
olx_adapter.py               OLX (rota Firecrawl fura o WAF) — queries Pokémon (cobertura OP = backlog)
mercadolivre_adapter.py      MercadoLivre — idem
amazon_adapter.py            Amazon BR (urllib + fallback browser $0 default desde 2026-06-10; Firecrawl legado opt-in pago)
build_us_reference.py        referência US que CLASSIFICA (tcgcsv; --game/--category-id/--bands;
                             SANITY_BANDS_USD Pokémon + SANITY_BANDS_USD_ONEPIECE)
build_ebay_reference.py      referência de VENDA informativa (eBay Browse API; menor anúncio ATIVO por SKU;
                             degradação honesta sem chaves — nunca sobrescreve a anterior)
panel.py                     🖥️ painel web LOCAL read-only (FastAPI :8078; /api/* + página única embutida;
                             aba "Análise" via /api/analysis)
analyze_sealed.py            📈 análise técnica US (hold vs sell) — INFORMATIVA, pós-scan (ver seção própria)
build_set_meta.py            datas de lançamento REAIS por group_id (tcgcsv publishedOn) → data/set_meta*.json
lib/tcgcsv_history.py        histórico diário REAL do TCGplayer (arquivo tcgcsv, port do outlook; py7zr lazy)
lib/analysis/                sinais/custos/cenários/decisão/score/stores/importadores/render da análise
scripts/terapeak_scrape.js   captura da tabela Sold do Product Research (console; a UI não tem export)
scripts/import_terapeak.py   importa a captura + seller via getItem (cache); import_events / import_trends
scripts/collect_supply_snapshot.py / collect_market_intel.py   série de oferta eBay · candidatos a evento (feeds)
scripts/evaluate_forecasts.py / analysis_report.py             previsão-vs-realidade · reimpressão da entrega
data/set_meta*.json          versionados (referência); data/events_*.yaml (curadoria com fonte obrigatória)
sku_registry.yaml            catálogo Pokémon (205 SKUs: product_id tcgcsv, set_terms EN+PT, requires_terms)
sku_registry_onepiece.yaml   catálogo One Piece (83 SKUs seed, 100% dados reais tcgcsv cat 68)
config.yaml                  perfil Pokémon: câmbio, filtros (SEM piso), deal_criteria, ROTA (route:), referências
config_onepiece.yaml         perfil One Piece (categorias 10/21/28/36 validadas no site OP — 2026-08-03, §B)
lib/                         browser.py (patchright), console.py, env.py, errors.py, firecrawl.py,
                             ebay_client.py (Browse API stdlib, copiado/adaptado da frota)
scripts/snapshot.py          ⭐ GERADOR CANÔNICO da entrega (--game; tabela agrupada por produto, 3 links)
scripts/snapshot_friendly.py variante de leitura; build_delivery_xlsx.py (XLSX de apoio sob pedido)
scripts/gen_onepiece_registry.py  gera/amplia o registry OP a partir do tcgcsv (rerunnável)
scripts/expand_registry_modern.py / readd_tins_split.py   manutenção do registry Pokémon
watchdog.py, register_task.ps1                            apoio de execução no PC do operador
probe_liga_sealed.py / probe_olx_local.py                 sondas manuais de coleta
SETUP-VALIDACAO.md           runbook das validações que exigem o PC/chaves do operador (§A–§D)
mock_data/                   fixtures de listing p/ rodar sem rede (--mock; onepiece_listings.json p/ OP)
tests/                       597 testes offline (gaps, matcher, gates, snapshot, adapters, eBay, perfis, painel, análise)
```

Todas as premissas do scan (câmbio + fonte usada, filtros, critérios) ficam no
`config.yaml` e são impressas no relatório — nunca escondidas.

## Armadilhas conhecidas

- **Cloudflare da Liga NÃO clareia em headless** (validado 2026-05-29: headless =
  0 produtos em todas as categorias; headful = produtos normais). Coleta Liga é
  **local, com janela do Chrome visível**, no PC do operador (IP residencial).
  Não "otimize" para headless.
- **Amazon BR serve 503 anti-bot intermitente ao urllib puro** (~50% medido
  2026-06-05). O fallback **browser real ($0)** é o default desde 2026-06-10
  (perfil próprio `~/.pw_profile_amazon_sealed`, abre lazy no 1º SKU bloqueado);
  Firecrawl virou fallback LEGADO opt-in (pago, ~51 créditos/run sob block
  pesado).
- **Match de acessório infla margem**: item avulso barato (fichário/álbum) pode
  casar SKU selado caro — por isso o teto `margem_anomala` (>200% → RED). Nunca
  remover o teto para "destravar" um deal.
- **Títulos PT do set**: Liga/OLX/ML são marketplaces BR — SKU só com nome EN
  perde ofertas em silêncio. Todo SKU precisa dos aliases PT em `set_terms`
  (classe de bug já corrigida em auditoria de 2026-06-27; ver CHANGELOG).
- **Nunca deduzir/inventar termo de set ou referência**: SKU novo só entra com
  product_id real no tcgcsv e preço dentro da sanity band do tipo de produto.
  Produto sem referência limpa fica FORA (regras invioláveis nº 6).

## Fluxo de desenvolvimento e segurança

- **Branch + PR, nunca push direto na `main`** (padrão da frota; todo o histórico
  do repo é via PRs squash-mergeados — cuidado com a família de erro git nº 2 do
  bloco da frota).
- **Secrets nunca versionados**: `.env`/`.env.*`, `*.pem`, `credentials.json` e
  os perfis de browser `.pw_profile_*/` estão no `.gitignore`. `SCRAPERAPI_KEY` /
  `FIRECRAWL_API_KEY` só via `.env` ou env var — nunca no `config.yaml` commitado.
- **Dados de scan ficam FORA do repo**: `results/`, `*.xlsx`, `*.log`, `*.html`
  (exceto fixtures de teste) e caches são gitignored. A entrega é a tabela no
  chat, não arquivo versionado.
- **Release público DISCRETO — não "consertar" o README**: o `README.md` é
  sanitizado de propósito (título neutro `price-compare-tool`, sem
  Pokémon/Liga/arbitragem). NÃO re-adicionar contexto de caso de uso lá — a doc
  técnica canônica é ESTE `CLAUDE.md`. Ver `PUBLIC-RELEASE-CHECKLIST.md` e
  `SECURITY.md`.

## Estado, pendências e histórico

- **Ao retomar sessão**, confira os handoffs datados na raiz
  (`HANDOFF-2026-06-26-gap-skus.md`, `HANDOFF-2026-06-27-coverage.md`,
  `HANDOFF-2026-06-27-gap-skus.md`, `HANDOFF-2026-07-02-skill-liga-sealed.md`) —
  eles registram o que foi feito e os gaps adiados (ex.: SKUs com referência
  achada mas sem título real da Liga p/ confirmar match).
- **`CHANGELOG.md`**: o repo NÃO usa versionamento semântico — entradas por
  data. Última entrada: 2026-08-03 (plataforma: rotas + referência de venda
  eBay + perfil One Piece + painel local). Mudanças que ficaram fora do
  CHANGELOG (ex.: PRs #72–#74 de 2026-07) estão no git log de `main`, que é a
  fonte de verdade do estado atual junto com o código mergeado.
- Marcos preservados: gate de condição selado-vs-aberto (2026-06-21) · modelo de
  entrega agrupado por produto padrão MYP (2026-06-20) · fallback browser $0 da
  Amazon (2026-06-10) · SEM piso (2026-06-27) · cobertura total do catálogo Liga,
  127 títulos (PR #70) · exclusão Battle Decks (2026-07-02) · exclusão Blister
  Duplo Heróis Excelsos Tangela/Komala (2026-07-03) · **plataforma: rotas +
  referência de venda eBay + perfil One Piece + painel local (2026-08-03 —
  entrada detalhada no CHANGELOG)** · **análise técnica US hold-vs-sell
  (2026-08-29 — seção 📈 acima; camada informativa pós-scan, rótulos neutros,
  comparáveis do arquivo tcgcsv, Terapeak p/ vendido, sem sales sheets
  Probstein por decisão do operador)**.
- **Validações §A–§C CONCLUÍDAS em 2026-08-03** (tabela de estado no
  `SETUP-VALIDACAO.md`): §A chaves eBay (nuvem + PC), §B Liga One Piece
  (categorias 10/21/28/36 + smoke headful no PC do operador), §C referência
  eBay OP (55/83). O scan OP real está destravado.
- **Backlog registrado da plataforma:** PriceCharting (vendas realizadas) como
  2ª referência de venda (campo `pc_url` no registry; parser da frota já provou
  páginas de selado); join do score de longo prazo do `pokemon-longterm-outlook
  --sealed` por productId (padrão doubleholo — informativo, nunca classifica);
  selados como 5ª fonte do `integrated-scanner`; pinagem de categoria eBay via
  Taxonomy API; cobertura One Piece em OLX/ML/Amazon; perfis Dragon Ball/
  Lorcana (mesma mecânica de perfil); POST /scan no painel (com guard
  anti-headful); watchdog por jogo. Minors do review de merge do PR #75
  (2026-08-04): escapar HTML/validar URL nos dados de anúncio injetados no
  painel (`panel.py` INDEX_HTML — título de marketplace é input de terceiro);
  piso de versão p/ `httpx2` no requirements; `#` fora do `safe` do
  `snapshot.md_link` (latente — nenhuma fonte emite fragmento hoje).
