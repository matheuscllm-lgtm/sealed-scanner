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

margem_total       = lucro_bruto / preço_compra_br    <- ÚNICO filtro (bruta)
mais_barato_que_us = lucro_bruto / us_price_brl        <- métrica de leitura
```

Só margem BRUTA. O scanner **NÃO** calcula nem exibe margem líquida, e **não**
embute custos operacionais (taxas de marketplace, frete internacional, 3PL,
imposto, lote) — o operador calcula isso por fora, na mão. As premissas que
restam (câmbio, preço mínimo, piso de margem) vivem em `config.yaml` e são
impressas no relatório — nunca escondidas.

## Critérios de deal

Filtro único: **margem bruta** = (preço_US − preço_BR) / preço_BR — só preço
contra preço, SEM nenhuma taxa embutida. Piso: **30%**.

- `GREEN`  — match HIGH e margem bruta ≥ 30%.
- `YELLOW` — match ambíguo (REVIEW): 1 anúncio casa com 2+ SKUs. NUNCA por
  faixa de margem.
- `RED`    — margem bruta < 30%, sem match, sem referência US, ou preço
  inválido/abaixo do mínimo de operação.

Classificação é SÓ por margem bruta. O scanner NÃO calcula nem exibe margem
líquida; custos operacionais (frete, taxas, lote) ficam FORA do scanner — o
operador calcula por fora.

Saída separada em três baldes: `real_opportunities`, `review_required`,
`rejected`.

## Regras invioláveis

- **Nunca inventar preço.** Sem referência TCGPlayer → rejeitado, não estimado.
- **Cada scan é fresco.** Diretório novo por execução; nada de misturar runs.
- **Match incerto → REVIEW**, nunca um palpite.
- Um deal só é "real" se a margem sobrevive às premissas de custo conservadoras.
