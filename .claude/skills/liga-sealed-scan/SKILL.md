---
name: liga-sealed-scan
description: Rodar e entregar o scan de produtos SELADOS Pokémon da Liga (sealed-scanner) sempre pelo MESMO caminho e no MESMO formato. Use quando o operador pedir para rodar o scan de selados da Liga, pedir "deals de selados", "resultados do sealed scanner", "panorama de selados" ou a tabela de entrega de um scan de selados. Execução única via run_liga_local.py; entrega única via scripts/snapshot.py (tabela markdown modelo MYP adaptado a selados, colada verbatim no chat).
---

# Scan de selados da Liga — caminho único de execução e entrega

Esta skill existe para o scan de **produtos selados** (booster box, ETB, bundle,
lata, blister...) da **Liga Pokémon** rodar sempre da mesma maneira e ser entregue
sempre no mesmo formato — o modelo MYP da frota, adaptado a selados. Não improvise
comandos nem formatos fora do que está aqui.

## ⚠️ Invariantes deste scanner (NÃO negociar)

1. **SEM PISO DE PREÇO.** O piso de relevância R$50 (~US$10) da frota vale **só
   para cartas avulsas (singles: MYP/CardTrader/Liga singles/COMC/eBay)**.
   **Selado NÃO tem piso** (decisão do operador, 2026-06-27):
   `config.yaml → filters.min_brazil_price_brl: 0`. O único critério de GREEN é
   margem bruta ≥ 30%. **Nunca reintroduzir piso aqui** — nem no config, nem em
   filtro ad-hoc na entrega. Preço 0/malformado continua RED pelo zero-guard de
   margem (0% < 30%), nunca GREEN.
2. **Threshold em FRAÇÃO**: `deal_criteria.min_total_margin_pct: 0.30` = 30%
   (convenção CardTrader/COMC/Selados; o MYP/Liga singles/eBay usam inteiro `30`).
3. **Margem BRUTA pura**: `(Ref. TCG − preço BR) / preço BR`, sem frete, taxa ou
   IOF embutidos — o operador soma custos por fora.
4. **Nunca inventar preço**: fonte falhou → linha marcada/erro e segue. Teto de
   plausibilidade: margem > 200% → RED `margem_anomala` (provável referência ou
   match errado).
5. **Nunca recomendar compra**: a entrega reporta margem, status e flags ⚠️;
   decisão de capital é do operador.

## Como RODAR (caminho único)

O scan da Liga é **local-only** (patchright + Chrome real; o Cloudflare da Liga
barra datacenter/headless de nuvem). No PC do operador:

```powershell
cd C:\Users\mathe\sealed-scanner
.venv\Scripts\python.exe run_liga_local.py            # scan + snapshots markdown (default)
.venv\Scripts\python.exe run_liga_local.py --categorias 10,27 --max-por-categoria 10
.venv\Scripts\python.exe run_liga_local.py --janela   # mostra a janela do Chrome
```

- O runner já gera as notas markdown de entrega no fim (snapshot técnico +
  didático). `--no-snapshot` só para debug do coletor.
- Multi-fonte (Amazon + Liga + OLX): `python run_all_sources.py` e depois
  `python scripts/snapshot.py` (fluxo canônico: watchdog → run_all_sources →
  snapshot).
- **Numa sessão de nuvem** (que não alcança a Liga): NÃO tente coletar por outra
  via. Use o último resultado existente — `python scripts/snapshot.py` (pega o
  `results/unified_*` mais recente) ou `--scan-dir results/unified_<stamp>` — e
  entregue esse markdown, dizendo de quando é o scan.

## Como ENTREGAR (formato único — modelo MYP adaptado a selados)

**Um caminho só:** cole no chat, **VERBATIM**, o markdown que `scripts/snapshot.py`
gerou (`snapshots/scan-YYYY-MM-DD-HHMM.md`). É o gerador canônico e obrigatório.

- **PROIBIDO** montar/reformatar tabela à mão, reordenar/renomear colunas, tirar
  um link ou "resumir" linhas. Se a entrega não saiu do `snapshot.py`, pare e
  gere por ele.
- **Nunca** entregar XLSX/CSV por padrão — arquivo só se o operador pedir
  explicitamente. O XLSX/CSV em `results/` é insumo, não entrega.
- **Mostrar TODAS as linhas**: a seção "Produtos acionáveis (GREEN + YELLOW)"
  **e** o "Ranking completo por produto" (que inclui os RED). Nada de amostra
  curada.

Colunas canônicas (travadas em `tests/test_snapshot_links.py` e
`tests/test_snapshot_grouping.py`; a fonte de verdade do layout é o próprio
`scripts/snapshot.py`):

```
Acionáveis: | # | Status | Produto (EN) | Tipo | Ref. Nacional (R$) | Ref. TCG (R$) | Margem bruta % | Δ R$/unid | Qtd total | Ofertas | ⚠️ | Links |
Ranking:    | # | Status | Produto (EN) | Ref. Nacional (R$) | Ref. TCG (R$) | Margem bruta % | Δ R$/unid | Qtd total | Ofertas | Links |
Escada:     | Vendedor | Fonte | Qtd disp. | Preço BR (R$) | Margem bruta % | Oferta |
```

- Entrega é **agrupada por produto** (SKU canônico), com a escada de ofertas por
  unidade logo abaixo de cada acionável — é o modelo MYP adaptado: selado não tem
  "nome + número" de carta nem set único, então a coluna de identidade é o
  **Produto (EN) canônico** + `Tipo`, e as referências vêm em R$ (`Ref. Nacional`
  = menor oferta BR com referência TCG; `Ref. TCG` = TCGplayer Market US$→R$
  pelo câmbio do scan).
- `Links` = `[oferta](url BR) · [TCG](url TCGplayer)` numa célula só — padrão da
  frota; os links são lidos do CSV, **nunca inventados**.
- ⚠️ = conferência manual (match ambíguo/margem suspeita); o motivo sai listado
  abaixo da tabela. Não esconda linhas flagadas.

## Armadilhas conhecidas

- **Não confundir com o scanner de singles da Liga** (`liga-cards-scanner` /
  `liga-pokemon-scanner`): lá é carta avulsa, threshold inteiro (`30`), COM piso
  R$50. Aqui é selado: fração (`0.30`), SEM piso.
- Se a entrega vier "vazia" (0 GREEN/YELLOW), entregue a tabela mesmo assim — o
  ranking completo mostra os RED e os near-miss. Nunca substitua por texto solto.
- Recorrência é **manual**: o operador aciona o scan; não criar agendamento.
