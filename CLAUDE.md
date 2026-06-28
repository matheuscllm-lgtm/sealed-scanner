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
