# Session Handoff — TCG Sealed Arbitrage Scanner

**Atualizado:** 2026-06-06
**Repo:** `matheuscllm-lgtm/sealed-arbitrage-scanner` (repo DEDICADO; arquivos na raiz, sem prefixo `sealed/`)
**Branch de trabalho:** `claude/determined-curie-Q1Ur8` · **PR:** #7 (draft)
**Commits desta sessão:** `47f43e2` (refresh preços US) · `7d0fdfc` (remove margem líquida + preço médio por SKU) · `6ee3645` (exclui ROI/líquido do core + snapshots) · `e917c18` (pool freight-free)

> ⚠️ Handoffs antigos apontavam pro monorepo `tcg-arbitrage-scanners` com tudo
> dentro de `sealed/`, e falavam em "ROI líquido mínimo", "22 testes", "55 SKUs".
> Tudo isso está **desatualizado**. O estado abaixo é o atual.

---

## ‼️ Como falar com o operador (dono do projeto)

O operador **NÃO é programador**. Evite jargão ou **sempre explique em português
simples** o que cada termo significa (ex.: "PR" = página no GitHub que junta as
mudanças; "teste" = verificação automática que o programa faz nele mesmo). Ele é
afiadíssimo na lógica de negócio (margem, frete, estoque), mas não na linguagem
técnica. Quando ele corrige uma premissa, ele costuma estar certo.

## TL;DR

Programa que acha **produtos selados de Pokémon** (booster box, ETB, bundle,
lata/tin, pack) mais baratos no Brasil do que valem nos EUA — pra revenda.

- **O programa SÓ monta a lista. NUNCA compra nada.** Toda compra é decisão do
  operador, conferida na mão. Nada é automatizado — isso é **por design**.
- **A busca da Liga roda no PC do operador** (Windows, Chrome real, IP
  residencial). A nuvem **não** consegue (Cloudflare da Liga bloqueia IP de
  datacenter). A nuvem serve pra: manter código/preços/registry corretos e gerar
  o XLSX de entrega quando há um `unified_deals.csv`.

## A regra de ouro (decidido nesta sessão — não rediscutir)

**A única métrica que importa é a DIFERENÇA BRUTA DE PREÇO** vs a referência US:

- **Margem total %** = (preço US − preço BR) ÷ preço BR
- **Δ R$/unid** = preço US − preço BR (a mesma diferença, em reais)
- Classificação: **VERDE ≥ 40% · AMARELO 30–40% · VERMELHO < 30%**

Tudo que dependia de suposição foi **removido**, porque não é sabido na hora da
busca:

- **Margem líquida / lucro líquido / ROI** (taxas de revenda, frete intl., 3PL):
  removido do output **e do miolo** (`compute_margin` só calcula bruto; bloco
  `fees:` saiu do `config.yaml`; campos `net_*` saíram do `ScanRow`).
- **Frete**: depende do tamanho do lote/remessa, cotado pelo operador na mão. O
  programa **não inventa frete em lugar nenhum** — inclusive a simulação de
  volume (Pool) agora é **freight-free**.

## O que mudou nesta sessão

1. **Preços de referência US atualizados** (`build_us_reference.py`; 104/105 SKUs
   têm preço via tcgcsv).
2. **Margem líquida removida da saída** (CSV + XLSX) e criado o **"Preço médio
   por SKU"**: média ponderada pela **quantidade** disponível, somando vários
   vendedores, **sem frete**, com filtro de outlier (typo tipo R$925 num pack de
   R$33 cai sozinho). Aparece no XLSX unificado e no de entrega. Função:
   `pool_fill.avg_price_for_sku()` + `scanner.compute_sku_averages()`.
3. **ROI/líquido excluído do core e dos snapshots** — `snapshot.py` e
   `snapshot_friendly.py` reescritos gross-only (Margem total + Δ R$/unid).
4. **Pool freight-free por default** — novo `freight_model="none"` no
   `pool_fill`; `config.frete.modelo: none`. A aba *Pool Analysis* perdeu as
   colunas Frete/Outlay; "Preço efetivo"→"Preço médio", "Margem real"→"Margem
   total". A engine ainda suporta `flat`/`per_seller` via config (testado), mas
   não é o default.

**Testes: 27 passando** (`tests/test_pool_fill.py`, `test_avg_price.py`,
`test_shipping.py`). Eu rodo na mão a cada mudança.

> Decisão tomada: **NÃO adicionar CI** (verificações rodando sozinhas no GitHub)
> por enquanto — como o operador confere toda compra, não compensa.

## Como retomar — comandos (rodar no PC, na raiz do repo)

```bash
# 0. Puxar a versão deste trabalho
git pull origin claude/determined-curie-Q1Ur8

# 1. Atualiza os preços US (TCGPlayer via tcgcsv)
python build_us_reference.py

# 2. Scan unificado (Amazon + Liga + OLX) — abre Chrome real p/ a Liga
python run_all_sources.py
#    subset:    python run_all_sources.py --sources amazon,liga
#    keep-alive: python watchdog.py --force   /   python watchdog.py --status
# Saída: results/unified_<timestamp>/unified_deals.csv (+ .xlsx completo)

# 3. XLSX condensado p/ entrega (só VERDE+AMARELO + Resumo + Preço médio)
python scripts/build_delivery_xlsx.py
#    usa o results/unified_* mais recente; imprime PATH=...

# Fonte única (debug):
python sealed_arbitrage_scanner.py --source liga     # Chrome headful abre
python sealed_arbitrage_scanner.py --source amazon
```

Setup de primeira vez no Windows: ver `SETUP-WINDOWS.md`. O Liga em `mode=local`
abre um **Chrome visível** (necessário pro Cloudflare) no IP residencial da casa.

## Estado das peças

| Peça | Estado | Notas |
|---|---|---|
| Pipeline (match → margem bruta → bucket → CSV/XLSX) | ✅ | `sealed_arbitrage_scanner.py` |
| Orquestrador multi-fonte unificado | ✅ | `run_all_sources.py` → `unified_deals.csv` + xlsx |
| Watchdog keep-alive + auto-refresh US | ✅ | `watchdog.py` (Task Scheduler) |
| Coluna `Qtd disponível` por anúncio | ✅ | sprite `imgunid` da Liga → `CSV_COLUMNS` |
| **Preço médio por SKU** (ponderado por qty, sem frete) | ✅ | `avg_price_for_sku`; abas nos 2 XLSX |
| Pool Fill — simulação de volume **freight-free** | ✅ | `pool_fill.py`; aba `Pool Analysis` (sem colunas de frete) |
| Classificação SÓ margem bruta (40/30) | ✅ | `config.yaml` → `deal_criteria` |
| ~~ROI líquido / margem líquida~~ | ❌ REMOVIDO | não existe mais em lugar nenhum |
| Fonte US: TCGPlayer Market via tcgcsv.com | ✅ | sem auth/CF; 104/105 SKUs com preço |
| Fonte BR: **Liga Pokémon** (`--source liga`) | ✅ | só no PC (`mode=local`, Chrome real) |
| Fonte BR: **Amazon BR** (`--source amazon`) | ✅ | HTML, sem CF — roda até na nuvem |
| Fonte BR: **OLX** (`--source olx`) | ❌ | Cloudflare WAF por IP — só com proxy residencial |
| Fonte BR: Mercado Livre | ❌ | API 403 + anti-bot; fora de escopo |

`sku_registry.yaml`: ~105 SKUs (boxes, ETBs, bundles, packs, mini tins).

## File map (raiz do repo)

```
.
├── README.md / AGENT.md / RUNBOOK.md / GOALS.md / PLAN.md
├── POOL-FILL-PLAN.md / SETUP-WINDOWS.md / SESSION-HANDOFF.md (este)
├── config.yaml                      # câmbio, critérios (deal_criteria), frete (modelo: none)
├── sku_registry.yaml                # ~105 SKUs
├── sealed_arbitrage_scanner.py      # pipeline principal (--source ...)
├── run_all_sources.py               # orquestrador unificado (amazon+liga+olx)
├── run_liga_local.py                # runner Liga local + snapshot
├── watchdog.py                      # keep-alive + auto-refresh US
├── build_us_reference.py            # refresh preços US (tcgcsv)
├── pool_fill.py                     # preço médio (avg_price_for_sku) + simulação de volume (fill_pool)
├── liga_adapter.py / amazon_adapter.py / olx_adapter.py
├── probe_liga_sealed.py / probe_olx_local.py   # sondas de debug
├── lib/                             # console, errors, shipping, browser
├── data/us_reference.json           # snapshot preços US
├── mock_data/                       # listings offline pra teste
├── scripts/                         # build_delivery_xlsx, snapshot[_friendly], registry tools
├── snapshots/                       # notas datadas (Obsidian)
├── results/unified_<ts>/            # saídas dos scans
└── tests/                           # 27 testes (pool_fill, avg_price, shipping)
```

## O que falta

- **Rodar a busca completa da Liga no PC** e validar na mão os melhores (conferir
  estoque + cotar frete real antes de comprar). É o próximo passo natural.
- (Capital, decisão do operador) Proxy residencial (~US$20-50/mês) destravaria a
  OLX e permitiria rodar a Liga na nuvem 24/7 — único gargalo de autonomia total.
- (Backlog) Alerta automático (Telegram/email) quando aparecer VERDE novo.

## Diagnóstico do bloqueio das fontes (histórico)

- **OLX**: Cloudflare WAF classifica o IP (datacenter/VPN) como bot. Não é o
  desafio Turnstile auto-clearable — patchright headful **não** resolve. Só proxy
  residencial.
- **Liga**: mesmo bloqueio de IP, **resolvido** rodando local com Chrome real no
  IP residencial (`mode=local`). `mode=scraperapi` existe como fallback, mas
  consome créditos e o free tier não cobre 1 scan completo.
- **Mercado Livre**: API exige app credentials (403); front com anti-bot pesado.

## Pra retomar na próxima sessão

1. Ler este arquivo + `GOALS.md` (pendências priorizadas).
2. Confirmar a branch: `git pull origin claude/determined-curie-Q1Ur8`.
3. Rodar a busca no PC (passos acima) e conferir `results/unified_<ts>/`.
4. Qualquer VERDE: validar na mão (vendedor, estoque, frete real) antes de comprar.
5. Falar com o operador em português simples, explicando os termos.
