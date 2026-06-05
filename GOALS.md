# GOALS — TCG Sealed Arbitrage Scanner

> Lista viva dos objetivos do projeto. Editar livremente.
> O comando `/goal` (em `.claude/commands/goal.md`) lê este arquivo
> e apresenta um resumo formatado pra qualquer sessão Claude.

## Em andamento agora

- [ ] **P1** (operador) Rodar no PC o re-scan com o registry novo (105 SKUs, latas re-adicionadas) e entregar o XLSX condensado no Drive. Comandos em `RUNBOOK.md` (refresh US → `run_all_sources.py` → `build_delivery_xlsx.py`). Não roda na nuvem (CF da Liga bloqueia IP de datacenter).
- [ ] **P1** Pós-Pool-Fill: validar manualmente os Top 5 GREEN do `Pool Analysis` num scan Liga real (confirmar qty + frete real antes de mover capital). Rodar: `python sealed\sealed_arbitrage_scanner.py --source liga --pool-budget 5000`.
- [ ] **P2** OLX block CF WAF é por IP (não Turnstile) — patchright NÃO resolve (validado). Pra firmar: proxy residencial (ScraperAPI/Firecrawl). Decisão de capital — fora de escopo de código.

## Backlog priorizado

- [ ] **P1** Validar manualmente os 5 YELLOW do último scan OLX+Amazon (verificar idioma + estoque + reputação do vendedor antes de comprar):
  - OLX-elite-12 Chaos Rising ETB R$346 (RJ)
  - OLX-elite-11 Chaos Rising ETB R$350 (RJ)
  - OLX-booster-2 Perfect Order Booster Bundle R$171
  - OLX-elite-4 Temporal Forces ETB R$1290 (review — Walking Wake vs Iron Leaves)
  - AMZ-pre-etb-en-1 Chaos Rising Booster Bundle R$200
- [ ] **P1** Rodar scan completo Liga local (todas as 8 categorias) e gerar snapshot Markdown.
- [ ] **P1** Pós-Pool-Fill: validar manualmente os Top 5 GREEN do `Pool Analysis` (confirmar qty + frete real antes de mover capital).
- [ ] **P2** Alertas automáticos (Telegram ou email) quando aparecer um GREEN novo.
- [ ] **P2** GitHub Actions cron diário — refresh de preços US + scan + commit do snapshot. Atenção ao quota cap observado no MYP repo.
- [ ] **P2** Expandir registry pra sets antigos quando inventário de sets recentes virar commodity: Crown Zenith, Silver Tempest, Lost Origin, Astral Radiance, Brilliant Stars.
- [ ] **P3** Modelar comissões TCGPlayer Direct vs eBay separadamente (hoje usa 13% genérico).
- [ ] **P3** Filtrar Liga local por sets do registry antes de baixar página de produto, pra não desperdiçar tempo em produtos fora do scope (PT-BR, JAP, etc).

## Feito recente

- [x] (2026-06-05) **ROI líquido excluído de vez (core + snapshots)** — operador: "exclua essa ideia de roi líquido, apenas com a diferença bruta de preço". `compute_margin` agora só calcula bruto (removidos `net_profit`/`net_margin`, `pct_fees`, `flat_fees`, `tax`); campos `net_*` saíram do `ScanRow`; o bloco `fees:` do `config.yaml` foi removido (só alimentava o líquido), junto das linhas de taxa/frete da aba Assumptions. `snapshot.py` perdeu a coluna "Lucro líq R$"; `snapshot_friendly.py` reescrito gross-only (Margem total + Δ R$/unid bruto; glossário sem ROI). Verificado: mock scan + os 2 snapshots geram sem erro; 26/26 testes. (Frete/taxas seguem só no `pool_fill`, que é margem bruta COM frete do lote — outra coisa.)
- [x] (2026-06-05) **Margem líquida removida do output + preço médio por SKU** — operador: "a única coisa que importa é a margem total; líquida não faz sentido sem saber frete e quantidades". Removidas as colunas `Lucro líquido est.`/`Margem líquida est.` do `CSV_COLUMNS` (limpa CSV **e** XLSX unificado, que reusa as mesmas colunas; o `build_delivery_xlsx` já estava limpo). Nova `avg_price_for_sku` no `pool_fill.py` (média ponderada pela qty, SEM frete, reusando o filtro de outlier) + `compute_sku_averages` no scanner; aba **Preço médio por SKU** no XLSX unificado e no de entrega (nº vendedores, qtd total, melhor preço, preço médio, margem total no médio). Caso de uso: estoque pequeno por vendedor → comprar volume = varrer vários logistas. 26/26 testes (4 novos). (Seguido pelo item acima: os snapshots foram reescritos gross-only e o cálculo de líquido saiu do core.)
- [x] (2026-06-02) **Review pós-tins: matching das latas endurecido** — revisão multi-agente achou que os termos largos das latas (`lata`/`tin` soltos + set_term genérico `151`) casavam carta avulsa ("Carta 151/165 na lata"), lata vazia e lote como GREEN falso (bypassa o guard `nao_e_selado`), e que excluir `booster`/`premium` derrubava lata legítima ("2 boosters + carta promo"). Fix: type_terms exigem "mini" (mini tin/mini lata); excludes trocam `booster`/`premium` por `vazia`/`vazio`/`lote`; `+mega heroes` no set Mega (latas são marca "Mega Heroes Mini Tin"). Script e registry batem (provenance), zero colisões, 22/22 testes.
- [x] (2026-06-02) **Gap SSP Booster Bundle fechado** — Surging Sparks era o único set (de 20) sem SKU de bundle; "Booster Bundle Surging Sparks" caía em NONE. Adicionado `ssp-bundle-en` (TCGPlayer Retail 679564, US$59.18) espelhando `jtg-bundle-en`. Agora casa HIGH; todos os 20 sets têm bundle. Registry 104→105.
- [x] (2026-06-02) **Limpeza dead-code margem líquida** — guarda-chuva já inerte desde `d48d025` (classificação só margem bruta): removido `min_net_margin_pct` do `config.yaml` + o read morto e os locais `net_profit`/`net_m` não usados no `classify`; comentários alinhados. A líquida segue calculada/exibida só como alerta.
- [x] (2026-06-02) **Tins re-adicionados com SPLIT** — 12 SKUs (`{set}-mini-tin` + `{set}-mini-tin-display`) p/ 6 sets (Mega Evolution, Ascended Heroes, Black Bolt, Prismatic Evolutions, Shrouded Fable, 151). Descoberta: esses sets não têm "Tin premium" no TCGPlayer — a linha é Mini Tin avulsa + Mini Tin Display (caixa) + Display Case. Avulsa usa o preço da lata mais barata do set (conservador); display exige "display" e exclui "booster". Gerador: `scripts/readd_tins_split.py` (âncoras YAML, diff aditivo). Zero colisões, 22/22 testes. Registry 92→104.
- [x] (2026-06-02) **Comandos + entrega preparados** — `RUNBOOK.md` (refresh US → scan → `build_delivery_xlsx.py` → Drive). Caminho de entrega smoke-testado (GREEN+YELLOW + Resumo).

- [x] (2026-05-30) **P0 qty_avail no output** — `("qty_avail", "Qtd disponível")` em `CSV_COLUMNS` (sealed_arbitrage_scanner.py). O campo já existia no `ScanRow` e era populado, mas não saía no CSV/XLSX. Verificado no scan mock. PR [#2](https://github.com/matheuscllm-lgtm/tcg-arbitrage-scanners/pull/2) (`f8ccd48`).
- [x] (2026-05-30) **P0 UnicodeEncodeError cp1252** — novo `sealed/lib/console.py::harden_stdout()` (UTF-8 `errors='replace'`, idempotente), wired em `run_all_sources`, `sealed_arbitrage_scanner`, `liga_adapter.__main__`; `run_liga_local` refatorado pro helper. Repro confirmada (sem fix exit 1 / com fix exit 0). PR #2 (`f8ccd48`).
- [x] (2026-05-30) **P1 trabalho pendente da árvore** — `merge_myp_ct.py` passa a ler sheet `Deals` do CT postprocess v2 (fallback legado `Oportunidades`). Nota: `run_all_sources.py`+`watchdog.py` do P1 original já estavam commitados via PR #1 (`7567369`); o único pendente real era o merge. PR #2 (`783addd`). 22/22 tests OK.
- [x] (2026-05-28) **Pool Fill COMPLETO** — 5 fases executadas via `/goal execute` com `sealed-reviewer` entre cada (todas PASS). Adapter captura qty por vendedor (sprite imgunid, 100% coverage 2 pcodes); modelo de frete flat do operador (R$250 1-loja / R$350 multi-loja); engine `pool_fill.py` (20 tests); aba `Pool Analysis` no XLSX. Plan: [`sealed/POOL-FILL-PLAN.md`](sealed/POOL-FILL-PLAN.md). Snapshot: `sealed/snapshots/plan-completion-pool-fill-2026-05-28.md`.
- [x] (2026-05-28) Critério `min_net_margin_pct: 0.05` (ROI líquido mínimo) — fecha gap onde produtos caros (ex.: Perfect Order BOX R$799 → R$6,75 líquido = 0,8%) viravam GREEN ilusório. Agora caem em YELLOW com alerta explícito.
- [x] (2026-05-28) Snapshot didático (`sealed/scripts/snapshot_friendly.py`) — agrupa por SKU, filtra ofertas perdedoras, glossário e premissas embutidas. Roda junto com `--snapshot` no `run_liga_local.py`. PYTHONIOENCODING=utf-8 também fixo no runner pra console Windows.
- [x] (2026-05-27) Primeiro scan local da Liga validado no PC do usuário: 224 listings, 11 GREEN/26 YELLOW/187 RED — adapter local + sprite decoder + tradução PT→EN funcionando ponta-a-ponta.
- [x] (2026-05-26) Liga adapter operacional em modo local (patchright + Chrome real). Default agora é `mode=local`. Modo `scraperapi` fica como fallback.
- [x] (2026-05-26) Liga adapter via ScraperAPI funcional: sprite decoder via template matching (10 PNGs), tradução PT→EN de tipo + sets, listagem por categoria com render JS + premium=true.
- [x] (2026-05-26) Bug PT-BR no exclude_terms (Amazon BR mostra PT-BR como "(PT-BR)" sem "português" no título). Adicionado `pt br`/`ptbr`/`copag`.
- [x] (2026-05-25) Snapshot system: gera nota Markdown datada em `sealed/snapshots/` com ranking unificado pra vault Obsidian.
- [x] (2026-05-25) Booster Packs adicionados ao registry com modelo `bulk_qty` (amortiza frete em compra em lote).

## Notas / contexto

- **Repo dedicado**: `matheuscllm-lgtm/sealed-arbitrage-scanner` (módulos na raiz, não mais em `sealed/`). **Branch atual**: `claude/determined-curie-Q1Ur8`.
- **Stack**: pipeline Python (`sealed_arbitrage_scanner.py`), preços US via tcgcsv (TCGPlayer Market), **105 SKUs** no registry. Classificação só por **margem bruta** desde 2026-06-02.
- **Fontes BR operacionais**: OLX (`--source olx`), Amazon BR (`--source amazon`), Liga (`--source liga`).
- **Cuidado de credits**: modo `scraperapi` do Liga adapter consome ~25-50 credits por render JS (Liga é "protected domain"). Free tier 1000/mês NÃO cobre 1 scan completo. Preferir `mode=local`.
- **Custo zero**: rodando da máquina do usuário em casa (Windows 11, Chrome instalado), IP residencial passa o Cloudflare da Liga.
- **Workflow `/goal execute`** (novo 2026-05-27): orquestrador lê P0 ativo, abre PLAN.md vinculado, executa fase-a-fase com `sealed-reviewer` agent entre cada. Comando `/goal` continua read-only sem argumento.
