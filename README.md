# Sealed Arbitrage Scanner

> **📍 FONTE ÚNICA DE VERDADE.** Este README é o front door do projeto. Para
> rodar o scanner ou entender o estado atual, **siga só este arquivo + os
> autoritativos do [Mapa de documentos](#mapa-de-documentos)**. Os docs em
> `docs/archive/` são **histórico** (apontam pra repo/branch/workflow antigos) —
> **não seguir.**

Scanner de arbitragem de **produtos selados** de Pokémon TCG: comprar no Brasil
(Liga Pokémon / Amazon BR / OLX) e revender nos EUA, com o **TCGPlayer** (via
`tcgcsv.com`) como referência de preço.

**Repo dedicado** `matheuscllm-lgtm/sealed-arbitrage-scanner`. Cobre só
**selados** (Booster Box, ETB, Bundle, Collection Box, Tin, Blister, Booster
Pack). **NÃO** envolve MYP Cards nem CardTrader — esses são scanners de **cartas
avulsas (singles)**, em repos separados. Selados é outra coisa, propositalmente
isolado.

---

## ⭐ Invariantes do operador (não violar)

Decisões fixas. Qualquer sessão que rode/entregue o scanner segue **todas**:

1. **Classificação = SÓ margem bruta.** `GREEN` = margem total ≥ 40%; `YELLOW`
   = 30–40% ou match ambíguo (REVIEW); `RED` = resto. **Sem guarda-chuva de
   margem líquida** — sem saber frete real + tamanho de lote, o líquido é
   fabricado. A líquida é calculada/exibida só como alerta, **nunca** define o
   bucket. (operador 2026-06-02)
2. **Tabelas mostram `Qtd disponível`** (estoque do vendedor) junto do preço —
   o operador importa em **lote**, nunca 1 unidade.
3. **Sem recomendação de compra.** Claude é técnico (código/dados/auditoria),
   não operacional. Não rankear "BUY", não dizer o que comprar — o operador
   decide capital.
4. **NM/EN selado.** Referência US é TCGPlayer EN; produto não-inglês = sem
   liquidez → fora do escopo.
5. **Liga roda HEADFUL no PC do operador.** O Cloudflare da Liga só clareia com
   janela real (headless = 0 produtos) e bloqueia IP de datacenter → o scan ao
   vivo **não roda na nuvem**.
6. **Modo MANUAL** (desde 2026-06-01). O watchdog/Task Scheduler está
   **DESATIVADO** — só roda quando o operador pede. Ver [Modo autônomo](#modo-autônomo-desativado).
7. **Entrega no chat + arquivo em disco.** Upload pro Drive é opcional e hoje
   **pulado** (base64 inline corrompe; rclone recusado pelo operador).

---

## 🚀 Como rodar (sequência canônica)

Quando o operador pedir **"rodar scanner de selados"**, é exatamente isto, nesta
ordem (detalhe operacional completo em **[RUNBOOK.md](RUNBOOK.md)**):

```bash
pip install -r requirements.txt          # 1ª vez

python build_us_reference.py             # 1) refresca preços US (tcgcsv) — rápido
python run_all_sources.py                # 2) scan default: Liga(HEADFUL) + OLX + MercadoLivre — NO PC
                                         #    (Amazon é opt-in: --sources amazon)
python scripts/build_delivery_xlsx.py    # 3) XLSX condensado (GREEN+YELLOW) p/ entrega
```

- `run_all_sources.py` orquestra as fontes e escreve
  `results/unified_<timestamp>/unified_deals.csv` + `.xlsx` (coluna `Fonte`,
  ordenado `GREEN → YELLOW → RED`, aba `Resumo`). Imprime o marcador
  `UNIFIED_OUT_DIR=`. Uma fonte bloqueada (ex.: OLX no CF WAF) **não derruba** o
  run (`SourceBlockedError`, degradação graciosa); só falha se NENHUMA entregar.
  **Default = Liga + OLX + MercadoLivre.** A **Amazon é opt-in** (`--sources amazon`):
  seu fallback Firecrawl é per-SKU (~51 créditos/run sob block pesado), caro p/ rodar
  sempre — as outras 3 custam ~0 (Liga headful) ou ~8 créditos (OLX/ML per-tipo).
- Entrega: mostrar **todas** as linhas GREEN/YELLOW no chat (não amostra curada),
  ordem por margem total desc, com `Qtd disponível`. Arquivo completo fica em
  `results/unified_<ts>/` (gitignorado).

Estado das fontes:

| Fonte | Estado | Default? | Observação |
|---|---|---|---|
| **Liga Pokémon** | ✅ operacional | ✅ sim | `patchright` + Chrome **headful**. Passo mais longo (~15-25 min). $0. |
| **OLX** | ⚠️ intermitente | ✅ sim | CF WAF por reputação de IP. `urllib`-first + Tier 2 Firecrawl render/proxy. ~8 créditos quando bloqueado. |
| **MercadoLivre** | ⚠️ intermitente | ✅ sim | anti-bot próprio (device-check). **firecrawl-first** (`waitFor ~14s`, stealth). ~8 créditos/run. |
| **Amazon BR** | ✅ operacional | ❌ **opt-in** | `urllib`+retry → fallback Firecrawl per-SKU. **~51 créditos/run** sob block pesado → fora do default; rode com `--sources amazon`. |

Rodar uma fonte só (debug):

```bash
python sealed_arbitrage_scanner.py --source mock
python sealed_arbitrage_scanner.py --source amazon         # opt-in (gasta créditos Firecrawl)
python sealed_arbitrage_scanner.py --source olx
python sealed_arbitrage_scanner.py --source mercadolivre
python run_liga_local.py --janela --snapshot     # Liga headful + snapshot
```

---

## Como o matching funciona

O catálogo de selados é pequeno e enumerável, então o matcher é uma busca
**determinística** contra o `sku_registry.yaml` curado (atualmente **105 SKUs**)
— não fuzzy. Cada SKU define `set_terms`, `type_terms`, `exclude_terms`
(opcional `requires_terms`):

- **HIGH** — 1 SKU casou.
- **REVIEW** — 2+ SKUs casaram (ambíguo) → revisão manual, nunca casado por engano.
- **NONE** — 0 SKUs → rejeitado.

Adicionar um produto = adicionar entrada no `sku_registry.yaml`.

⚠️ **Armadilha de set-prefix:** nomes de **era** que prefixam títulos da Liga
(ex.: "Mega Evolution" antes de "Perfect Order"/"Chaos Rising") fazem SKUs da era
casarem com sub-sets. Mitigado via `exclude_terms` (sub-sets no exclude
compartilhado). Ao adicionar SKUs de uma era nova, repetir o padrão.

---

## Modelo de margem

```
margem_total = (preço_US − preço_BR) / preço_BR        # ÚNICO filtro
```

Lucro sobre o capital de compra, antes das taxas. Classificação **só por margem
bruta** (ver [Invariantes](#-invariantes-do-operador-não-violar) #1):
**GREEN** ≥ 40% · **YELLOW** 30–40% ou REVIEW · **RED** < 30% / sem match / sem
ref US / abaixo do preço mínimo.

A margem líquida (após ~18% de taxas + frete + 3PL) é **calculada e exibida como
alerta informativo**, mas **NÃO** define o bucket. A diferença também é exibida
como **"mais barato que US"** `(preço_US − preço_BR) / preço_US`.

---

## Preços de referência US — tcgcsv.com

`data/us_reference.json` contém preços **reais** do TCGPlayer (Market Price)
gerados a partir do [tcgcsv.com](https://tcgcsv.com) (espelho público da API do
TCGPlayer, grátis, sem auth, atualização diária). Cada SKU em `sku_registry.yaml`
tem `tcgplayer_group_id` + `tcgplayer_product_id`. Refrescar:

```bash
python build_us_reference.py                       # marketPrice (default)
python build_us_reference.py --price-field lowPrice
```

---

## Modo autônomo (DESATIVADO)

> ⚠️ **Em modo MANUAL desde 2026-06-01** (invariante #6). O bloco abaixo descreve
> o keep-alive autônomo, hoje **desligado**. Não reativar sem o operador pedir.

`watchdog.py` mantém o scan unificado vivo via Windows Task Scheduler (a cada
15 min). Lock atômico + `scan_pid` evitam double-launch / colisão do Chrome.
Reativar (só se o operador pedir):

```powershell
Enable-ScheduledTask -TaskName SealedScannerWatchdog
# ou registrar do zero:
powershell -ExecutionPolicy Bypass -File .\register_task.ps1
```

`python watchdog.py --status` mostra o estado; `--force` dispara um scan agora.

---

## Mapa de documentos

| Documento | Papel | Seguir? |
|---|---|---|
| **README.md** (este) | Front door / fonte única — identidade, run, invariantes | ✅ **Sim** |
| **[RUNBOOK.md](RUNBOOK.md)** | Passo-a-passo operacional de scan + entrega | ✅ Sim |
| **[AGENT.md](AGENT.md)** | Especificação do agente (missão, classificação, regras invioláveis) | ✅ Sim |
| **[GOALS.md](GOALS.md)** | Lista viva de objetivos (lida pelo `/goal`) | ✅ Sim |
| **[SETUP-WINDOWS.md](SETUP-WINDOWS.md)** | Setup de ambiente no Windows (Python + Chrome p/ Liga headful) — referência de 1ª vez, não diretiva operacional | ✅ Sim (setup) |
| `docs/SESSION-*.md` | Resumão datado da última sessão (o que rolou + onde retomar). Snapshot — defere ao README | ✅ Referência (mais recente) |
| `docs/archive/*` | Planos/handoffs antigos (repo/branch/workflow obsoletos) | 🔴 **Não** — histórico |

---

## Estrutura

```
.
├── README.md                   # ⭐ FONTE ÚNICA — comece aqui
├── RUNBOOK.md                  # passo-a-passo de scan + entrega
├── AGENT.md / GOALS.md         # spec do agente / objetivos vivos
├── SETUP-WINDOWS.md            # setup de ambiente no Windows (1ª vez)
├── run_all_sources.py          # ENTRADA padrão — orquestrador (default 3 fontes + Amazon opt-in) → tabela unificada
├── sealed_arbitrage_scanner.py # pipeline (1 fonte por vez): match → margem → classificação
├── build_us_reference.py       # gera data/us_reference.json a partir de tcgcsv
├── scripts/build_delivery_xlsx.py  # XLSX condensado (GREEN+YELLOW) p/ entrega
├── watchdog.py / register_task.ps1 # keep-alive autônomo (DESATIVADO — modo manual)
├── liga_adapter.py             # Liga (patchright + Chrome headful)
├── amazon_adapter.py           # Amazon BR (urllib+retry → fallback Firecrawl; opt-in)
├── olx_adapter.py              # OLX (urllib-first + Tier 2 Firecrawl render/proxy)
├── mercadolivre_adapter.py     # MercadoLivre BR (firecrawl-first; device-check próprio)
├── pool_fill.py                # preço efetivo por unidade dado budget
├── config.yaml                 # câmbio, taxas, critérios, seções dos adapters
├── sku_registry.yaml           # catálogo curado de SKUs selados (= o matcher)
├── lib/                        # errors, shipping, console, browser, firecrawl (transporte /scrape)
├── data/us_reference.json      # preços REAIS TCGPlayer (gerado, commitado)
└── docs/archive/               # 🔴 histórico — não seguir
```

## Saídas

Cada execução cria `results/<timestamp>/` (gitignorado — runs nunca se misturam):

| Arquivo | Conteúdo |
|---|---|
| `unified_deals.csv` / `unified_sealed_<ts>.xlsx` | tabela consolidada das fontes (via `run_all_sources.py`) |
| `real_opportunities.csv` / `review_required.csv` / `rejected.csv` | por bucket (via `sealed_arbitrage_scanner.py`) |
