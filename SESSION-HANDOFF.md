# Session Handoff — TCG Sealed Arbitrage Scanner

**Atualizado:** 2026-05-30
**Repo:** `matheuscllm-lgtm/tcg-arbitrage-scanners`
**Branch:** `main` (sealed mergeado via PR #1; correções recentes via PR #2)
**Últimos commits:** `62ffee7` (refresh preços US) · watchdog auto-refresh US · `f8ccd48` (P0 qty + cp1252)

> ⚠️ Versões antigas deste arquivo diziam "Liga bloqueada / OLX funcionando".
> Isso se **inverteu** a partir de 2026-05-26. O estado abaixo é o atual.

## TL;DR

O scanner roda **ponta-a-ponta no PC do operador** (Windows, em casa). O
`watchdog.py` mantém um scan unificado fresco (<45min) de hora em hora via Task
Scheduler, atualiza os preços US ~1x/dia, e entrega `unified_deals.csv` +
`unified_sealed_*.xlsx` rankeado (GREEN→YELLOW→RED) com coluna de quantidade
disponível por anúncio.

**Fontes BR:** Liga (✅ local headful, ~765 listings/scan) e Amazon BR (✅ ~25)
funcionam. OLX está **bloqueada** (Cloudflare WAF por IP) — só destrava com
proxy residencial (decisão de capital, fora de escopo de código). O orquestrador
registra OLX como "bloqueada" e segue com as outras sem derrubar o run.

## Como retomar — comandos

```bash
# Estado do watchdog (o que está rodando / idade do último resultado)
python sealed/watchdog.py --status

# Forçar um scan unificado agora (amazon + liga + olx)
python sealed/watchdog.py --force

# Scan unificado direto (sem watchdog)
python sealed/run_all_sources.py
python sealed/run_all_sources.py --sources amazon,liga   # subset

# Fonte única (debug)
python sealed/sealed_arbitrage_scanner.py --source liga    # Chrome headful abre
python sealed/sealed_arbitrage_scanner.py --source amazon

# Refresh manual dos preços US (o watchdog já faz ~1x/dia)
python sealed/build_us_reference.py
```

O Liga em `mode=local` abre um **Chrome real visível** (necessário pro
Cloudflare) usando o IP residencial da casa — é isso que o ambiente de nuvem
não consegue replicar.

## Estado das peças

| Peça | Estado | Notas |
|---|---|---|
| Pipeline (match → margem → bucket → CSV/XLSX) | ✅ | `sealed_arbitrage_scanner.py`; 22 testes |
| Orquestrador multi-fonte unificado | ✅ | `run_all_sources.py` → `unified_deals.csv` + xlsx |
| Watchdog keep-alive (Task Scheduler 15min) | ✅ | `watchdog.py`; resultado sempre <45min |
| Refresh de preços US automático (~1x/dia) | ✅ | dentro do watchdog, antes do scan, não-fatal |
| Coluna `Qtd disponível` por anúncio | ✅ | sprite `imgunid` da Liga → `CSV_COLUMNS` |
| Console Windows cp1252 (UnicodeEncodeError) | ✅ | `lib/console.harden_stdout()` nos entrypoints |
| Pool Fill (frete flat, aba `Pool Analysis`) | ✅ | `pool_fill.py` (20 tests); `POOL-FILL-PLAN.md` |
| Critério margem total ≥40% GREEN / 30-40% YELLOW | ✅ | `config.yaml` → `deal_criteria` |
| Critério ROI líquido mínimo (`min_net_margin_pct`) | ✅ | barra "GREEN ilusório" em produto caro |
| Fonte US: TCGPlayer Market via tcgcsv.com | ✅ | sem auth, sem CF; 54/55 SKUs |
| Fonte BR: **Liga Pokémon** (`--source liga`) | ✅ | `mode=local` (patchright + Chrome real) |
| Fonte BR: **Amazon BR** (`--source amazon`) | ✅ | busca textual HTML, sem CF |
| Fonte BR: **OLX** (`--source olx`) | ❌ | Cloudflare WAF por IP — precisa proxy residencial |
| Fonte BR: Mercado Livre | ❌ | API 403 + anti-bot; fora de escopo |

## O que falta pra "inteiramente funcional"

**Técnico (sem capital):**
- Alerta automático (Telegram/email) quando aparecer GREEN novo — backlog P2.
- `pb-pack-en` (Pitch Black booster pack) sem `marketPrice` na tcgcsv (54/55).
- Expandir registry pra sets antigos (Crown Zenith, Silver Tempest, Lost Origin,
  Astral Radiance, Brilliant Stars) quando os recentes virarem commodity.
- Modelar comissão TCGPlayer Direct vs eBay separadamente (hoje 13% genérico).

**Capital (decisão do operador):**
- **Proxy residencial** (~US$20-50/mês: Bright Data/Smartproxy) — destrava OLX e,
  mais importante, permite rodar o Liga **na nuvem 24/7** sem depender do PC de
  casa ligado com Chrome aberto. É o único gargalo de "autonomia completa".
- Validação manual de cada GREEN (vendedor, frete real, qty) antes de comprar —
  isto é **por design**, não é bug.

## File map

```
sealed/
├── PLAN.md / POOL-FILL-PLAN.md / AGENT.md / README.md
├── SESSION-HANDOFF.md                  # este arquivo
├── config.yaml                         # câmbio, taxas, critérios, modos dos adapters
├── sku_registry.yaml                   # 55 SKUs (boxes, ETBs, bundles, packs)
├── sealed_arbitrage_scanner.py         # pipeline principal (--source ...)
├── run_all_sources.py                  # orquestrador unificado (amazon+liga+olx)
├── run_liga_local.py                   # runner Liga local + snapshot
├── watchdog.py                         # keep-alive + auto-refresh US (Task Scheduler)
├── build_us_reference.py               # refresh preços US (tcgcsv)
├── pool_fill.py                        # engine de pool/frete flat
├── liga_adapter.py / amazon_adapter.py / olx_adapter.py
├── lib/                                # console.py, errors.py, shipping.py
├── data/us_reference.json              # snapshot preços US (auto-refresh ~1x/dia)
├── mock_data/liga_listings.json        # listings offline pra teste
├── scripts/snapshot.py + snapshot_friendly.py
├── snapshots/                          # notas datadas pro vault Obsidian
├── results/unified_<ts>/               # saídas dos scans + run.log
└── tests/                              # 22 testes (pool_fill, shipping, ...)
```

## Fontes BR — diagnóstico do bloqueio (histórico)

- **OLX**: Cloudflare WAF classifica o IP (datacenter/VPN) como bot. Não é o
  desafio Turnstile auto-clearable — patchright headful **não** resolve
  (validado). Só proxy residencial.
- **Liga**: mesmo bloqueio de IP **resolvido** rodando local com Chrome real no
  IP residencial da casa (default `mode=local`). `mode=scraperapi` existe como
  fallback mas consome ~25-50 credits/render (free tier 1000/mês não cobre 1
  scan completo).
- **Mercado Livre**: API exige app credentials (403); front tem anti-bot pesado.

## Para retomar na próxima sessão

1. Ler este arquivo + `GOALS.md` (lista viva de pendências priorizadas).
2. `python sealed/watchdog.py --status` — confirmar que está vivo e fresco.
3. Conferir o último `results/unified_<ts>/` e o snapshot mais recente.
4. Se aparecer GREEN: validar manualmente (vendedor, frete, qty) antes de comprar.
5. Pendências técnicas e de capital estão no `GOALS.md`.
