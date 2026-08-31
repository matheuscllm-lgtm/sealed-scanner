# HANDOFF — 2026-08-30 (pós-ativação da Análise Técnica US)

Estado ao fim da sessão de 2026-08-30. O runbook de partida
(`HANDOFF-2026-08-30-analise-tecnica.md`, PR #81) foi **executado por completo**
nesta sessão; este arquivo registra o resultado e o que fica pendente.

## O que foi feito hoje

| Item | Resultado |
|---|---|
| Scan Liga do dia (Pokémon) | `results/unified_20260830_140430` → **23 GREEN · 0 YELLOW · 80 RED** (759 anúncios); entrega em `snapshots/scan-2026-08-30-1704.md` |
| Referência TCG (tcgcsv) | Rebuild do dia: 203/205 SKUs com preço (1 excluído por guard de faixa de Tin, 1 sem preço no espelho) |
| Referência eBay | Rebuild do dia **pós-merge**: 179 SKUs ok · 26 sem anúncio; **1º ponto da série de oferta gravado** (205 pontos em `data/history/supply_pokemon.jsonl`) |
| PR #80 (análise técnica) | Já estava mergeado (`1248700`), CI verde — revisores extras não foram necessários |
| Passo 1 do runbook | main atualizada + `py7zr` e dependências instalados na venv |
| Passo 2 (prova de vida) | `pytest` → **599 passed** · `analyze_sealed.py --mock` → tabela "Decisão de venda" com 🔵 MANTER_90D e ⚪ DADOS_INSUFICIENTES |
| Passo 3b (supply extra) | +205 snapshots — série de oferta com 2 pontos no dia 1 |
| Passo 3c (market intel) | Feeds PokeBeach/PokeGuardian indisponíveis (pulados best-effort) → **0 candidatos**; nada a promover |
| Análise real do scan de hoje | `analyze_sealed.py` avulso: **⚪ DADOS_INSUFICIENTES = 74 · ⛔ EVITAR_COMPRA = 27 · 🔵 MANTER_90D = 2** |

O predomínio de ⚪ é o comportamento **esperado por design** nas primeiras 1–2
semanas: a série de histórico acabou de nascer e nunca estimamos artificialmente.
Encorpa a cada `build_ebay_reference`/snapshot diário.

Achado a observar: vários GREEN do scan (ex.: Cynthia's Garchomp, Salamence &
Reshiram) mostram **lucro líquido de hoje negativo** com custos de realização —
conferir o lado de venda antes de importar esses SKUs.

## Pendente com o operador

1. **Terapeak (Passo 4, mensal, ~10 min/SKU):** Seller Hub → Research → Product
   research → aba "Sold" (conta matchil70) → console F12 com
   `scripts/terapeak_scrape.js` → salvar em `data\terapeak\<sku>_<data>.csv` →
   `python scripts/import_terapeak.py <csv> --lookback-days 30`. É o que mais
   eleva a confiança dos sinais.
2. **Market intel:** feeds estavam fora hoje; re-rodar
   `python scripts/collect_market_intel.py` num outro dia e conferir/promover
   candidatos com `scripts/import_events.py` (nada entra sozinho).

## Ritual (nada mudou)

- Diário: `python run_liga_local.py` — a análise roda sozinha e a entrega ganha
  a 3ª tabela "Decisão de venda". Antes de todo scan: rebuild TCG + eBay
  (regra do operador: referência só do dia, `max_reference_age_days=1`).
- Mensal: `python scripts/evaluate_forecasts.py` (previsão vs realidade).
- Extras: `scripts/analysis_report.py` (detalhe/fontes) ·
  `python -m uvicorn panel:app --host 127.0.0.1 --port 8078` (aba "Análise").

## Lembretes de contrato

- Rótulos da análise são técnicos e informativos — decisão de capital é 100% do
  operador; nada altera GREEN/YELLOW/RED nem a margem bruta.
- Entrega de scan: SEMPRE via `scripts/snapshot.py`, verbatim, 2 links por linha.
- One Piece segue com `analysis.enabled: false` até calibrar.
- Doc completa: `ANALISE-TECNICA.md`.
