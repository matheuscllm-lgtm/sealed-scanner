# TCG Sealed Arbitrage Agent — especificação

## Missão

Encontrar oportunidades reais de arbitragem de **produtos selados** de Pokémon
TCG: comprar no Brasil e revender nos Estados Unidos, usando o TCGPlayer como
referência de preço de venda nos EUA.

A pergunta que o agente responde:

> Esse produto selado comprado no Brasil, por esse preço, ainda dá lucro se
> revendido nos EUA pelo preço do TCGPlayer, depois de taxas conservadoras?

Esta primeira versão é **Brasil → EUA**, sem previsão de valorização futura.

## Escopo

**Inclui** (selados): Booster Box, Elite Trainer Box, Booster Bundle,
Collection Box, Premium Collection, Tin, Sleeved Booster, Blister Pack.

**Exclui**: cartas avulsas, cartas graded, produtos abertos, danificados, e
qualquer item sem equivalente claro no mercado dos EUA.

## Fontes

- **Compra (Brasil)**: Liga Pokémon (`ligapokemon.com.br`). Fonte única
  desta versão. A Liga está atrás de CloudFlare — o bypass via `patchright`
  já existe nos `probe_liga_*.py` na raiz do repo.
- **Referência (EUA)**: TCGPlayer Market Price para o produto selado.

## Matching — registry curado, não fuzzy match

O catálogo de selados é pequeno e enumerável (algumas centenas de SKUs, vs.
~16k singles). Por isso o matching é uma **busca determinística** contra o
`sku_registry.yaml` curado:

- `HIGH`   — exatamente 1 SKU casou.
- `REVIEW` — 2+ SKUs casaram (ambíguo, ex.: "ETB Prismatic" sem dizer se é a
  versão Pokémon Center). Vai para revisão manual, nunca casado por engano.
- `NONE`   — 0 SKUs casaram. Rejeitado.

Nunca assumir que dois produtos são o mesmo sem bater tipo, coleção, idioma,
formato selado e edição.

## Modelo financeiro

```
us_price_brl  = us_price_usd × câmbio
lucro_bruto   = us_price_brl − preço_compra_br

margem_total       = lucro_bruto / preço_compra_br    <- filtro principal
mais_barato_que_us = lucro_bruto / us_price_brl        <- métrica de leitura

lucro_liquido  = lucro_bruto
                 − taxas_percentuais(sobre a venda US)
                 − frete_internacional − 3PL − buffer_imposto
margem_liquida = lucro_liquido / preço_compra_br       <- alerta, não filtro
```

Todas as premissas vivem em `config.yaml` e são impressas no relatório —
nunca escondidas.

## Critérios de deal

Filtro principal: **margem total** — lucro sobre o preço de compra, antes das
taxas. Alvo: 30–35% mais barato que os EUA, o que equivale a ≥40% de margem
total.

- `GREEN`  — match HIGH, margem total ≥ 40% **e** lucro líquido ≥ 0.
- `YELLOW` — margem total entre 30% e 40%; ou margem total no alvo mas
  líquido negativo (taxas consomem o lucro); ou match ambíguo (REVIEW).
- `RED`    — margem total < 30%, sem match, sem referência US, ou abaixo do
  preço mínimo de operação.

A margem líquida após taxas é alerta, não filtro: não esconde um deal, mas
rebaixa de GREEN para YELLOW quando o lucro real fica negativo.

Saída separada em três baldes: `real_opportunities`, `review_required`,
`rejected`.

## Regras invioláveis

- **Nunca inventar preço.** Sem referência TCGPlayer → rejeitado, não estimado.
- **Cada scan é fresco.** Diretório novo por execução; nada de misturar runs.
- **Match incerto → REVIEW**, nunca um palpite.
- Um deal só é "real" se a margem sobrevive às premissas de custo conservadoras.
