# ANALISE-TECNICA.md — análise técnica US (hold vs sell) para selados

> **Em uma frase:** depois que o scanner acha um selado barato na Liga, esta
> camada olha o mercado AMERICANO e responde: **vender assim que chegar, ou
> segurar 30/60/90 dias?** — com números, fontes e datas, nunca no chute.
> A pergunta central: a oferta nos EUA tende a **diminuir** (valorização) ou
> **aumentar** (queda no curto prazo)?

É uma camada **INFORMATIVA e pós-scan**: não muda NADA do scanner (a
classificação GREEN/YELLOW/RED, a margem bruta e a entrega seguem idênticas —
travado em teste). Os rótulos são **classificação técnica neutra**; a decisão
de capital é 100% do operador.

## Como rodar

```bash
python analyze_sealed.py                    # analisa o último scan Pokémon
python analyze_sealed.py --game onepiece    # (perfil OP nasce DESLIGADO — calibrar antes)
python analyze_sealed.py --offline          # sem internet: sinais viram n/d (honesto)
python analyze_sealed.py --mock             # exemplo completo com DADOS SIMULADOS
python scripts/analysis_report.py           # reimprime a última análise (entrega)
```

O `run_liga_local.py` já chama a análise ao fim de todo scan (desligue com
`--no-analise`), e a **tabela de decisão entra na entrega** do
`scripts/snapshot.py` (3ª tabela) quando a análise do mesmo scan existe.
Falha da análise NUNCA derruba o scan. O painel local ganhou a aba "Análise"
(`/api/analysis`). Sem agendamento novo — recorrência é manual (regra da frota).

## Os 5 estados (rótulos neutros)

| Estado | Significado |
|---|---|
| 🟢 `JANELA_VENDA` | listar assim que chegar nos EUA (realiza em ~1 ciclo) |
| 🔵 `MANTER_30D/60D/90D` | segurar N dias ALÉM do ciclo antes de listar |
| ⛔ `EVITAR_COMPRA` | lucro líquido negativo hoje E em todos os horizontes |
| ⚪ `DADOS_INSUFICIENTES` | sem base para decidir — **nunca estimamos artificialmente** |

Cada recomendação traz: confiança 0-100% (qualidade dos DADOS), justificativa
com números, maior catalisador, maior risco, **condição de invalidação** e a
data da próxima revisão — e toda evidência carrega `fonte + URL + data`.

## O ciclo operacional (~24 dias)

Decisão do operador (2026-08-29): venda "imediata" tem um delay natural de
**~10d** (produto chegar) + **~7d** (envio aos EUA) + **~7d** (listar) — os
três componentes ficam em `analysis.cycle` no config (o total é a soma, nunca
hardcoded). Por isso:

- o **lucro de "vender agora"** é projetado para a data de realização
  (~hoje+24d), não para o preço deste minuto;
- "MANTER_30D" = 30 dias **além** do ciclo;
- o custo de capital só conta os dias EXTRAS (o capital do ciclo fica parado
  nos dois caminhos — cancela na comparação).

## Fórmulas (modelo financeiro SIMPLIFICADO)

```text
receita_liquida      = venda_bruta × net_factor          (0,70 inicial — configurável)
lucro_liquido        = receita_liquida_convertida_BRL − preço_compra
margem_sobre_custo   = lucro_liquido ÷ preço_compra
preço_maximo_compra  = receita_liquida_BRL ÷ (1 + 0,25)  (margem mín. 25% s/ custo)
custo_capital        = preço_compra × 15%a.a. × dias_extras/365
lucro_futuro_esperado = Σ(probabilidade × lucro_do_cenário)
valor_de_esperar     = lucro_futuro_esperado − lucro_hoje − custo_capital
```

O fator 0,70 agrega os custos do canal real (Probstein + PayPal + logística +
imposto ≈ 30%) — a composição exata fica POR FORA, na mão do operador; o
sistema só aplica o fator (`analysis.net_factor`). **MANTER só quando
`valor_de_esperar > 0`** depois do custo de capital.

## Os 5 sinais de mercado (calculados SEPARADAMENTE)

| Sinal | Fonte (com data em toda evidência) | O que mede |
|---|---|---|
| **1. Tendência de preço** | arquivo diário REAL do TCGplayer (tcgcsv.com, desde 2024-02-08, por productId) + capturas Terapeak (vendido) | variação 30/90/180d, inclinação, volatilidade, mediana vendida, spread market×vendido×Probstein |
| **2. Volume/liquidez** | **SÓ vendas** (Terapeak importado) + nº de ativos como denominador | unidades vendidas, vendas/semana, sell-through, share Probstein. **Market Price NUNCA mede volume** |
| **3. Evolução da oferta** | snapshots de anúncios ativos no eBay US (`total` da Browse API; `collect_supply_snapshot.py` + 1 ponto por run do `build_ebay_reference.py`) | Δ de ativos em 7/30/90d. <2 pontos → `HISTORICO_INSUFICIENTE` (a série começa vazia — honesto) |
| **4. Risco de reprint/restock** | eventos CURADOS (`data/events_pokemon.yaml`, sempre com fonte) + estrutural (sets de reprint forte/especiais + idade real do set via `data/set_meta.json`) | estado da evidência (`CONFIRMADO_OFICIAL/RESTOCK_OBSERVADO/SINAL_DISTRIBUIDOR/RUMOR/SEM_EVIDENCIA`) + nível alto/médio/baixo. **SEM_EVIDENCIA ≠ risco baixo**; "esgotado" ≠ descontinuado |
| **5. Demanda pelas chases** | top-10 cards do set por Market Price (tcgcsv) + variação 30/90d do arquivo | Δ agregado, quantas sobem×caem, concentração nas top-3. Indicador **AUXILIAR** — não prova escassez do selado (e não é análise de singles) |

## De onde vêm as probabilidades (nunca chute)

1. **Comparáveis alinhados por idade**: produtos do MESMO tipo (ETB↔ETB…) do
   registry; para cada um, medimos o retorno REAL que ele teve quando tinha a
   idade que o alvo tem hoje, na janela do horizonte (arquivo tcgcsv).
2. **Cenários = percentis documentados** dessa distribuição (p20/p50/p80 →
   pessimista/base/otimista), aplicados ao preço de hoje. Probabilidades base
   0,25/0,50/0,25 (`analysis.comparables`).
3. **Ajustes por sinal, cada um citado na justificativa**: reprint alto capa o
   base em ≤0% e alarga o pessimista; oferta caindo forte + fora da janela de
   impressão alarga o otimista; probabilidade desloca ±0,10 conforme o caso.
4. **Coorte < 8 comparáveis → `DADOS_INSUFICIENTES`** — sem probabilidade
   arbitrária, nunca.
5. **Backtest é parte do método**: toda análise loga as previsões
   (`data/forecasts/*.jsonl`) e `python scripts/evaluate_forecasts.py` compara
   com o preço REALIZADO do arquivo na data de vencimento (hit-rate + erro
   médio). Errou muito → recalibrar os percentis no config.

## Runbook: vendas reais do eBay (Terapeak)

O eBay não dá API de vendidos (restrita) e o Product Research **não tem export
nem coluna de seller** (validado pelo operador em 2026-08-29). O caminho
oficial:

1. Seller Hub → Research → **Product research** → aba **Sold**; busque o
   produto e escolha o período (anote: 30/90 dias).
2. Role a página até o fim; console (F12); cole `scripts/terapeak_scrape.js`.
3. O CSV cai na área de transferência → salve em `data/terapeak/<sku>_<data>.csv`.
4. `python scripts/import_terapeak.py data/terapeak/<arquivo>.csv --lookback-days 30`
   — casa título→SKU (ambíguo é descartado), busca o **seller** de cada item
   via Browse API `getItem` (cache em `data/cache/ebay_sellers.json`) e marca
   `is_probstein`. Anúncio encerrado há >~90d some da API → fica sem seller
   (nunca inventado) — **por isso capture mensalmente**.

## Eventos de mercado (reprint/restock)

- `python scripts/collect_market_intel.py` — varre feeds públicos (PokéBeach,
  PokeGuardian…) e junta CANDIDATOS com gatilho (reprint/restock/wave…).
- Candidato só vira evento por `python scripts/import_events.py` (fonte
  obrigatória: URL + data). Notícia = no máximo `SINAL_DE_MERCADO`; fórum/rede
  social = sempre `RUMOR`.
- Pokémon Center/Walmart/Target/GTS/Southern Hobby exigem conta/anti-bot →
  **fase 2**; enquanto isso entram MANUALMENTE pelo mesmo import_events.
- Google Trends: só CSV exportado da UI (`scripts/import_trends.py`) —
  informativo.

## Limitações honestas (leia antes de usar)

1. **Não é previsão garantida** — comparáveis são passado; o mercado pode
   fazer outra coisa. O avaliador mede o erro e realimenta a calibração.
2. **Pedida ≠ venda realizada** — anúncio ativo é o que pedem; vendido real só
   via Terapeak importado (AGREGADO por anúncio, não transação a transação).
3. **FX constante** nos horizontes (não prevemos câmbio).
4. O arquivo tcgcsv começa em **2024-02-08**; set/produto sem histórico sai
   `n/d`.
5. A série de oferta **começa vazia** — nas primeiras semanas o sinal 3 sai
   `HISTORICO_INSUFICIENTE` e a confiança fica baixa, por design.
6. Ausência de dado NUNCA vira evidência favorável.
7. **Decisão de capital é do operador** — sempre.

## Fase 2 (backlog declarado — não construído)

Probes de estoque de varejistas (PC/Walmart/Target/BestBuy/GameStop) e
GTS/Southern Hobby; PriceCharting selado via `pc_url` no registry (mapeamento
próprio de labels: used=aberto/new=selado); Google Trends automatizado; nº de
sellers do TCGplayer; colunas de análise no `unified_deals.csv`; calibração e
ativação do perfil One Piece.
