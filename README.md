# Sealed Arbitrage Scanner

Scanner de arbitragem de **produtos selados** de Pokémon TCG: comprar no Brasil
(Liga Pokémon / Amazon BR / OLX) e revender nos EUA, com o **TCGPlayer** (via
`tcgcsv.com`) como referência de preço.

> **Repo dedicado.** Cobre só **selados** (Booster Box, ETB, Bundle, Collection
> Box, Tin, Blister, Booster Pack). **NÃO** envolve MYP Cards nem CardTrader —
> esses são scanners de **cartas avulsas (singles)**, em repos separados
> (`myp-arbitrage-scanner`, etc.). Selados é outra coisa, propositalmente isolado.

## Como rodar

```bash
pip install -r requirements.txt
```

**Entrada padrão — roda as 3 fontes de uma vez e consolida numa tabela:**

```bash
python run_all_sources.py
```

Orquestra **Amazon + Liga + OLX** numa só execução e escreve
`results/unified_<timestamp>/unified_deals.csv` + `.xlsx` (coluna `Fonte`,
ordenado `GREEN → YELLOW → RED`, aba `Resumo` por fonte). Uma fonte bloqueada
(ex.: OLX no Cloudflare WAF) **não derruba** o run — registra como
`SourceBlockedError` e segue com as outras. Só falha se NENHUMA fonte entregar.

Estado das fontes:

| Fonte | Estado | Observação |
|---|---|---|
| **Liga Pokémon** | ✅ operacional | `patchright` + Chrome **headful** (o CF "Um momento…" só clareia com janela; headless = 0 produtos). Passo mais longo (~15-25 min). |
| **Amazon BR** | ✅ operacional | `urllib` puro; pode tomar 503 por SKU em pico (tratado por-query). |
| **OLX** | ⚠️ intermitente | CF WAF "you have been blocked" por reputação de IP — oscila (bloqueado num scan, OK no outro). Degradação graciosa quando bloqueado. |

Rodar uma fonte só (debug):

```bash
python sealed_arbitrage_scanner.py --source mock
python sealed_arbitrage_scanner.py --source amazon
python sealed_arbitrage_scanner.py --source olx
python run_liga_local.py --janela --snapshot     # Liga headful + snapshot
```

Pool Fill (preço efetivo por unidade dado um budget, considerando estoque por
vendedor e frete por lote):

```bash
python sealed_arbitrage_scanner.py --source liga --pool-budget 5000
```

## Modo autônomo (keep-alive)

`watchdog.py` mantém o scan unificado vivo via Windows Task Scheduler (a cada
15 min, auto-ressuscita). Lock atômico + `scan_pid` evitam double-launch /
colisão do Chrome headful. Antes de cada scan, atualiza os preços US se
estiverem velhos (~1x/dia). Registrar:

```powershell
powershell -ExecutionPolicy Bypass -File .\register_task.ps1
```

`python watchdog.py --status` mostra o estado; `--force` dispara um scan agora.

## Preços de referência US — tcgcsv.com

`data/us_reference.json` contém preços **reais** do TCGPlayer (Market Price)
gerados a partir do [tcgcsv.com](https://tcgcsv.com) (espelho público da API do
TCGPlayer, grátis, sem auth, atualização diária). Cada SKU em
`sku_registry.yaml` tem `tcgplayer_group_id` + `tcgplayer_product_id`. Refrescar:

```bash
python build_us_reference.py                       # marketPrice (default)
python build_us_reference.py --price-field lowPrice
```

## Como o matching funciona

O catálogo de selados é pequeno e enumerável, então o matcher é uma busca
**determinística** contra o `sku_registry.yaml` curado — não fuzzy. Cada SKU
define `set_terms`, `type_terms`, `exclude_terms`:

- **HIGH** — 1 SKU casou.
- **REVIEW** — 2+ SKUs casaram (ambíguo) → revisão manual, nunca casado por engano.
- **NONE** — 0 SKUs → rejeitado.

Adicionar um produto = adicionar entrada no `sku_registry.yaml`.

## Modelo de margem

```
margem_total = (preço_US − preço_BR) / preço_BR
```

Lucro sobre o capital de compra, antes das taxas. **GREEN** exige margem total
**≥ 40%**; entre 30-40% vai para **YELLOW**; abaixo, **RED** (`config.yaml →
deal_criteria`). A classificação é **só por margem total**: sem saber frete real
e tamanho do lote por remessa, a margem líquida seria um número fabricado — por
isso não é calculada nem exibida (operador 2026-06-05).

Cada anúncio traz a **`Qtd disponível`** ao lado do preço, e o relatório inclui
a aba **Preço médio por SKU** — preço médio ponderado pela quantidade, somando o
estoque de vários logistas (estoque pequeno por vendedor → comprar volume =
varrer várias lojas). Frete fica fora; a margem ali é a total no preço médio.

A diferença também é exibida como **"mais barato que US"**
`(preço_US − preço_BR) / preço_US`.

## Estrutura

```
.
├── run_all_sources.py          # ENTRADA padrão — orquestrador 3 fontes → tabela unificada
├── sealed_arbitrage_scanner.py # pipeline (1 fonte por vez): match → margem → classificação
├── watchdog.py                 # keep-alive autônomo (Task Scheduler 15 min)
├── register_task.ps1           # registra a tarefa no Windows Task Scheduler
├── liga_adapter.py             # Liga (patchright + Chrome headful)
├── amazon_adapter.py           # Amazon BR (urllib)
├── olx_adapter.py              # OLX (urllib + detecção de WAF block)
├── pool_fill.py                # preço efetivo por unidade dado budget
├── build_us_reference.py       # gera data/us_reference.json a partir de tcgcsv
├── config.yaml                 # câmbio, taxas, critérios, seções dos adapters
├── sku_registry.yaml           # catálogo curado de SKUs selados (= o matcher)
├── lib/                        # errors, shipping, console, browser
├── data/us_reference.json      # preços REAIS TCGPlayer (gerado, commitado)
└── mock_data/liga_listings.json
```

## Saídas

Cada execução cria `results/<timestamp>/` (gitignorado — runs nunca se misturam):

| Arquivo | Conteúdo |
|---|---|
| `unified_deals.csv` / `unified_sealed_<ts>.xlsx` | tabela consolidada das 3 fontes (via `run_all_sources.py`) |
| `real_opportunities.csv` / `review_required.csv` / `rejected.csv` | por bucket (via `sealed_arbitrage_scanner.py`) |
