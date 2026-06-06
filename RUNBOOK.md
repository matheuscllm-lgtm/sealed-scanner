# RUNBOOK — Scan + Entrega no Drive

> Passo-a-passo operacional. O scan ao vivo da Liga roda **no seu PC** (Windows,
> Chrome real, IP residencial) — o Cloudflare da Liga bloqueia IP de
> datacenter/nuvem, então a sessão em nuvem **não** consegue rodar o scan.
> O que a nuvem faz: manter registry/preços/código corretos e gerar/entregar
> o XLSX condensado quando houver um `unified_deals.csv`.

## 1. No seu PC — refresh dos preços US + scan

```bash
# (a) Atualiza os preços US (TCGPlayer via tcgcsv). Importante após mudanças no
#     registry — ex.: as 12 Mini Tins re-adicionadas hoje. 1 fetch por set.
python build_us_reference.py

# (b) Scan unificado (Amazon + Liga + OLX). Abre Chrome real p/ a Liga.
python run_all_sources.py
#   subconjunto:  python run_all_sources.py --sources amazon,liga
#   keep-alive:   python watchdog.py --force        (força um scan agora)
#                 python watchdog.py --status        (idade do último resultado)

# Saída: results/unified_<timestamp>/unified_deals.csv  (+ .xlsx completo)
```

Classificação (margem **bruta** = (US − BR)/BR, só diferença de preço, **sem taxa
embutida**): **GREEN ≥30%** (é deal), **YELLOW** = match ambíguo (revisar), **RED
<30%**. Piso de 30% é a regra única do operador (2026-06-06). Frete, cartão, IOF e
demais taxas ficam fora do scanner (calculados na mão).

## 2. XLSX condensado p/ entrega

O XLSX completo (~800 linhas, maioria RED) é grande demais p/ upload inline.
Este gera só GREEN+YELLOW + aba Resumo:

```bash
python scripts/build_delivery_xlsx.py
#   usa o results/unified_* mais recente; saída em TEMP (imprime PATH=...)
# ou aponte explicitamente:
python scripts/build_delivery_xlsx.py results/unified_<ts> entrega.xlsx
```

## 3. Entrega no Drive

- **Manual:** suba o `entrega.xlsx` na pasta do Drive de sempre.
- **Via sessão Claude:** dê `git add results/unified_<ts>/unified_deals.csv && commit && push`
  (ou cole o caminho). Aí eu gero o condensado e subo pro Drive pela integração.

## Notas

- **Mini Tins (2026-06-02):** 12 SKUs re-adicionados com split — `*-mini-tin`
  (lata avulsa, preço da avulsa mais barata do set, conservador) e
  `*-mini-tin-display` (a caixa lacrada; exige "display"). Sets: Mega Evolution,
  Ascended Heroes, Black Bolt, Prismatic Evolutions, Shrouded Fable, 151.
  Rode o passo 1(a) no PC p/ popular os preços (já vêm no `us_reference.json`,
  mas o refresh garante valores do dia).
- **OLX:** bloqueada por IP (CF WAF) — o orquestrador registra "bloqueada" e
  segue sem derrubar o run. Só destrava com proxy residencial.
