# CLAUDE.md

Instruções para qualquer sessão Claude Code (local ou nuvem) que trabalhe neste repo.

## 🛰️ Convenções da frota (cross-scanner)

> **Manual completo** (repo privado): https://github.com/matheuscllm-lgtm/scanners-commons — erros comuns, referências de preço, chaves, GitHub Actions e modelo de entrega de TODOS os scanners. Cópia-mestra local: `C:\Users\mathe\scanners-commons\`.

Invariantes que valem para TODOS os scanners:
- **Margem BRUTA, mínimo 30%** — só `(revenda − compra)/compra`, sem taxa embutida. ⚠️ **Piso de preço difere por produto:** scanners de **cartas avulsas (singles: MYP/CardTrader/Liga/COMC/eBay/PSA)** têm piso de relevância **R$50 (~US$10)**; **este scanner é de SELADOS, que NÃO têm piso** (decisão do operador 2026-06-27) — o único critério é margem bruta ≥30%. Ver seção "Este scanner" abaixo.
- **Só Near Mint** — condição por match EXATO `== "NM"`, nunca substring (já vazou SP).
- **Nunca inventar preço** — fonte falhou → marca fallback/erro e segue; jamais fabrica número.
- **Entrega = tabela markdown no chat** (nunca XLSX por padrão), gerada pela ferramenta do repo, mostrando TODAS as linhas (aprovadas + rejeitadas). Coluna `Carta` = nome + número; coluna `Links` combinada = `[oferta](url) · [TCG/referência](url)`.
- ⚠️ **Convenção de threshold:** percentual inteiro (`30`) = MYP, Liga, eBay; fração (`0.30`) = CardTrader, COMC, Selados.

Erros recorrentes (3 famílias — detalhe no manual):
1. **Segredo/ambiente:** BOM/zero-width numa chave → crash latin-1 no header → scan "verde mas vazio". Setar sem BOM (`printf '%s' 'KEY' | gh secret set`) **e** sanitizar ao ler no código (`.strip()` NÃO tira BOM).
2. **Git:** galho ou `main` local defasado por squash-merge PARECE pendência. O teste real de "já mergeado" é `git diff --stat origin/main <galho>` estar vazio (não `git merge-base`).
3. **Honestidade de preço:** inflação de referência, fallback tratado como real, NM frouxo → sempre validar versão/condição e rotular fallback.

**Este scanner (SELADOS):** referência de preço = TCGplayer US (preço Market do selado, via espelho `tcgcsv.com`); chaves = `FIRECRAWL_API_KEY` (no PC; rota Firecrawl fura o WAF da OLX).
- **SEM PISO DE PREÇO** (`config.yaml: filters.min_brazil_price_brl: 0`, decisão do operador 2026-06-27): selado não tem piso; o único critério de GREEN é margem bruta ≥30% (`deal_criteria.min_total_margin_pct`). NÃO reintroduzir o piso R$50 das cartas avulsas aqui — ele vale só para singles. Preço 0/malformado continua RED via o zero-guard de `compute_margin` (margem 0% < 30%), nunca GREEN.
- **Exclusões documentadas do registry** (decisão do operador 2026-07-03, não re-perguntar): **Blister Duplo Heróis Excelsos [Tangela] e [Komala]** ficam FORA — o set ASC (group tcgcsv 24541) não tem NENHUM blister selado no TCGplayer, logo não há referência US possível e o invariante "nunca inventar preço" ganha. Se o tcgcsv um dia listar, cadastrar. Battle Decks/Baralhos também seguem fora (decisão 2026-07-02). A cobertura do catálogo de selados da Liga é travada por `tests/test_gap_loose_packs.py` (127 títulos reais do operador → match único, exceto essa lista fechada).

## 📤 Como rodar e entregar resultados (skill `sealed-scan` — MANDATÓRIO)

> Caminho único, detalhado na skill do repo
> `.claude/skills/sealed-scan/SKILL.md` (canônica; espelhada em
> `~/.claude/skills/sealed-scan/` no PC do operador pra disparar fora do repo —
> se editar uma, sincronize a outra). Resumo:

- **Pergunte a fonte primeiro** (menu na skill): Liga ($0, default recomendado) /
  Liga+OLX+ML / Amazon (opt-in, ~51 créditos Firecrawl — avisar custo) / todas.
- **Rodar (Liga é local-only, PC do operador, janela do Chrome VISÍVEL — CF dá
  0 produtos em headless):** `python run_liga_local.py` — roda via
  `run_all_sources.py --sources liga` (saída canônica `results/unified_*`, a que
  o snapshot lê) e já gera as notas markdown no fim (snapshot é default;
  `--no-snapshot`/`--no-janela` só para debug). Multi-fonte:
  `run_all_sources.py --sources ...` → `scripts/snapshot.py`.
- **Entrega = colar VERBATIM o markdown do `scripts/snapshot.py` no chat.**
  NUNCA montar tabela à mão, nunca XLSX/CSV por padrão, mostrar TODAS as linhas
  (acionáveis GREEN+YELLOW **e** o ranking completo com os RED). Formato = modelo
  MYP adaptado a selados (agrupado por produto/SKU, coluna
  `Links` = `[oferta](url) · [TCG](url)`), travado em `tests/test_snapshot_*`.
- **⚠️ Piso de preço: selado NÃO tem** (`config.yaml: filters.min_brazil_price_brl: 0`,
  operador 2026-06-27). O piso R$50 da frota vale **só para cartas avulsas
  (singles)**. Não reintroduzir aqui; único critério de GREEN é margem bruta ≥30%
  (fração `0.30` em `deal_criteria.min_total_margin_pct`).
