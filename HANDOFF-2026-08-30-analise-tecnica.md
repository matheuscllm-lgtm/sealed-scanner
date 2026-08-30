# HANDOFF — 2026-08-30 — Análise técnica US (hold vs sell) mergeada: como iniciar pelo terminal

> **Estado:** PR #80 **MERGEADO** no `main` (squash `1248700`, 2026-08-30) após
> reavaliação adversarial por agente revisor independente (veredito PASS) +
> correções de acabamento (cadeia monetária no render, timeout do hook, notas
> de honestidade, contadores de doc). CI verde; suíte **599 testes** offline.
> Doc canônica da camada: `ANALISE-TECNICA.md` · seção 📈 do `CLAUDE.md`.

Este handoff é o **runbook de partida no PC do operador** (Windows,
`C:\Users\mathe\sealed-arbitrage-scanner`). Ordem pensada para a primeira
semana de uso real.

## 1. Atualizar e validar (uma vez, ~5 min)

```powershell
cd C:\Users\mathe\sealed-arbitrage-scanner
git checkout main
git pull origin main
pip install -r requirements.txt        # traz o py7zr (leitor do arquivo tcgcsv)
python -m pytest -q                     # esperado: 599 passed
python analyze_sealed.py --mock         # exemplo completo com DADOS SIMULADOS (exit 0)
```

O `--mock` mostra como a saída real vai parecer (3ª tabela "Decisão de venda",
sinais, cenários) — tudo rotulado ⚠️ DADOS SIMULADOS.

## 2. Semear os dados que a análise consome (primeira vez)

A análise nunca inventa dado: o que não existir sai como `n/d` /
`HISTORICO_INSUFICIENTE` / `DADOS_INSUFICIENTES`. Para sair disso:

```powershell
# a) datas de lançamento reais (já versionadas; re-rodar só se entrar set novo):
python build_set_meta.py

# b) 1º snapshot da oferta ativa no eBay (exige EBAY_CLIENT_ID/SECRET — §A do SETUP-VALIDACAO.md):
python scripts/collect_supply_snapshot.py
# ⚠️ a série de oferta precisa de ≥2 pontos p/ tendência → rode de novo em ~7 dias;
#    depois, 1×/semana é suficiente. O build_ebay_reference.py também alimenta a série.

# c) candidatos a evento de reprint/restock (feeds públicos → curadoria manual):
python scripts/collect_market_intel.py
python scripts/import_events.py --help   # promover candidato exige fonte (URL) + data
```

## 3. Captura Terapeak (vendas reais — mensal, ~10 min)

Fluxo validado na sua conta (matchil70) em 2026-08-29; a UI **não tem** export
nem coluna de seller — por isso o snippet:

1. Seller Hub → Research → **Product Research** → aba **Sold**; busque o
   produto, ajuste o período (lookback), **role a tabela até o fim**.
2. F12 → Console → cole o conteúdo de `scripts/terapeak_scrape.js` → Enter →
   o CSV cai no clipboard/download. Salve em `data\terapeak\<nome>_<data>.csv`.
3. Importe (o seller de cada anúncio vem via API oficial `getItem`, com cache):

```powershell
python scripts/import_terapeak.py data\terapeak\<arquivo>.csv --lookback-days 30
```

Anúncio encerrado há >90 dias perde o seller na API (fica `null`, contado à
parte) → **capture mensalmente**. Sales sheets da Probstein NÃO são usadas
(sua decisão, 2026-08-29) — a proporção Probstein vem do lookup de seller.

## 4. Dia a dia (nada muda no seu fluxo)

```powershell
python run_liga_local.py               # scan Liga como sempre; a análise roda
                                       # sozinha antes do snapshot (--no-analise desliga)
```

A entrega continua a MESMA tabela do snapshot — quando existe análise do mesmo
scan, ela ganha a **3ª tabela "Decisão de venda"**: 🟢 JANELA_VENDA ·
🔵 MANTER_30/60/90D · ⛔ EVITAR_COMPRA · ⚪ DADOS_INSUFICIENTES, com lucro
líquido hoje, lucro esperado, valor de esperar, confiança e próxima revisão.
Nota: a coluna "Venda base (US$)" com **†** é o preço **projetado para a data
de realização** (~fim do ciclo de ~24d) — é o preço que entra na conta do
lucro; o preço de hoje está no detalhe por produto (`analise_tecnica.md` do
run). Painel: aba "Análise" em http://127.0.0.1:8078.

## 5. Mensal — fechar o ciclo do método

```powershell
python scripts/evaluate_forecasts.py   # previsões vencidas × preço realizado do arquivo
```

Hit-rate baixo / erro alto ⇒ recalibrar `analysis.comparables` no
`config.yaml` (percentis/coorte) — o backtest é parte do método, não enfeite.

## Lembretes duros

- Rótulos são **classificação técnica** — a decisão de capital é 100% sua.
- One Piece nasce com `analysis.enabled: false` (`config_onepiece.yaml`) —
  ligar só depois de calibrar com dados reais.
- A análise é informativa e pós-scan: GREEN/YELLOW/RED, margem e CSV do scan
  **não mudam** (travado em teste).

## Backlog registrado (não iniciar sem pedido)

- Teste de byte-identidade da entrega por fixture golden (hoje a prova é por
  ausência de seção; a byte-identidade foi provada manualmente por sha256).
- Default `hold.min_wait_value_brl: 0` é agressivo (R$0,01 já vira MANTER) —
  subir é decisão sua, no `config.yaml`.
- Fase 2 declarada: probes de varejistas/GTS/Southern Hobby, PriceCharting
  selado via `pc_url`, Google Trends automatizado, colunas de análise no
  `unified_deals.csv`, calibração One Piece.
