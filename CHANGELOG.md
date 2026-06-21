# CHANGELOG — Sealed Arbitrage Scanner

Registro datado de mudanças relevantes. O repo não usa versionamento semântico
(SemVer); as entradas são por data. Fonte única de estado segue o `README.md`.

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
