# CLAUDE.md — sealed-scanner

Instruções para qualquer sessão Claude Code (local ou nuvem) que trabalhe neste repo.

Scanner de arbitragem de **produtos SELADOS** de Pokémon TCG (booster box, ETB,
fat pack, lata, blister, kit, pré-lançamento…): compara ofertas em marketplaces
BR (Liga Pokémon, OLX, MercadoLivre, Amazon BR) com a referência US do TCGplayer
e classifica por margem bruta. Repo GitHub: `matheuscllm-lgtm/sealed-scanner`;
pasta local no PC do operador: `C:\Users\mathe\sealed-arbitrage-scanner`.

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

**Este scanner (SELADOS):** referência de preço = TCGplayer US (preço Market do selado, via espelho `tcgcsv.com`); chaves = `FIRECRAWL_API_KEY` (no PC; rota Firecrawl fura o WAF da OLX).

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
5. **YELLOW é EXCLUSIVAMENTE match ambíguo** (1 anúncio casa 2+ SKUs) — nunca por
   faixa de margem. A classificação é SÓ por margem bruta.
6. **Exclusões documentadas do registry** (decisões do operador, não re-perguntar):
   - **Blister Duplo Heróis Excelsos [Tangela] e [Komala]** ficam FORA (decisão
     2026-07-03) — o set ASC (group tcgcsv 24541) não tem NENHUM blister selado
     no TCGplayer, logo não há referência US possível e o invariante "nunca
     inventar preço" ganha. Se o tcgcsv um dia listar, cadastrar.
   - **Battle Decks/Baralhos** também seguem fora (decisão 2026-07-02).
   - A cobertura do catálogo de selados da Liga é travada por
     `tests/test_gap_loose_packs.py` (**127 títulos reais do operador** → match
     único, exceto essa lista fechada).

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
  ```

  `run_liga_local.py` usa a saída canônica `results/unified_*` (a que o snapshot
  lê) e já gera as notas markdown no fim (snapshot é default; `--no-snapshot` /
  `--no-janela` só para debug do coletor). Flags úteis: `--categorias 10,27`,
  `--max-por-categoria N`, `--skip-check`. O orquestrador aceita `--config`,
  `--registry` e `--mock` (fixture JSON de `mock_data/`).
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
  Ref. TCG (US$→R$), Margem bruta % por linha e coluna
  `Links` = `[oferta](url) · [TCG](url)` em toda linha. Formato travado em
  `tests/test_snapshot_*`.
- O `scripts/snapshot.py` roda sobre o `unified_deals.csv` da run
  (`results/unified_*/`); o `run_liga_local.py` já o dispara por default.
  `scripts/build_delivery_xlsx.py` gera o XLSX de apoio — só sob pedido.
- Lembrete: selado **não tem piso de preço** (regra inviolável nº 1 acima).

## Testes

```bash
python -m pytest -q     # 354 testes (verificado 2026-07-07), 100% offline
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
sealed_arbitrage_scanner.py  pipeline: match título↔SKU + gate de condição + compute_margin (zero-guard) + classificação GREEN/YELLOW/RED
run_all_sources.py           orquestrador multi-fonte (DEFAULT_SOURCES = liga,olx,mercadolivre; amazon opt-in) → results/unified_*/
run_liga_local.py            atalho canônico do scan Liga local (Chrome headful + snapshot no fim)
liga_adapter.py              Liga Pokémon (patchright + Chrome headful; modo scraperapi p/ servidor)
olx_adapter.py               OLX (rota Firecrawl fura o WAF)
mercadolivre_adapter.py      MercadoLivre
amazon_adapter.py            Amazon BR (urllib + fallback browser $0 default desde 2026-06-10; Firecrawl legado opt-in pago)
build_us_reference.py        gera/refresca a referência US (TCGplayer via tcgcsv.com)
sku_registry.yaml            catálogo canônico de SKUs (~10,6k linhas: product_id tcgcsv, set_terms EN+PT, requires_terms, sanity bands)
config.yaml                  premissas auditáveis: câmbio (fetch/manual), filtros (SEM piso), deal_criteria (0.30 / teto 200% / ref. 14d), fontes
lib/                         browser.py (patchright), console.py, errors.py, firecrawl.py
scripts/snapshot.py          ⭐ GERADOR CANÔNICO da entrega (tabela markdown agrupada por produto)
scripts/snapshot_friendly.py variante de leitura; build_delivery_xlsx.py (XLSX de apoio sob pedido)
scripts/expand_registry_modern.py / readd_tins_split.py   manutenção do registry
watchdog.py, register_task.ps1                            apoio de execução no PC do operador
probe_liga_sealed.py / probe_olx_local.py                 sondas manuais de coleta
mock_data/                   fixtures de listing p/ rodar o pipeline sem rede (--mock)
tests/                       354 testes offline (gaps de cobertura, matcher, gates, snapshot, adapters)
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
  data. Última entrada: 2026-06-27; mudanças posteriores (até o PR #72,
  2026-07-03 — fix registry TEF ETB) estão só no git log de `main`, que é a
  fonte de verdade do estado atual junto com o código mergeado.
- Marcos preservados: gate de condição selado-vs-aberto (2026-06-21) · modelo de
  entrega agrupado por produto padrão MYP (2026-06-20) · fallback browser $0 da
  Amazon (2026-06-10) · SEM piso (2026-06-27) · cobertura total do catálogo Liga,
  127 títulos (PR #70) · exclusão Battle Decks (2026-07-02) · exclusão Blister
  Duplo Heróis Excelsos Tangela/Komala (2026-07-03).
