# HANDOFF — Sealed Scanner — 2026-07-02 (skill liga-sealed-scan + sem piso)

> Documento de passagem de contexto para **assumir este trabalho em outra sessão**
> — em especial a **sessão LOCAL no terminal do PC do operador**, que é onde o
> próximo passo (o scan de produção) precisa rodar. Linguagem direta para o
> operador (Matheus, médico, não-programador). **Não supersede** o
> `HANDOFF-2026-06-27-coverage.md` (a pendência de scan de produção de lá continua
> viva e é a pendência nº 1 daqui). Estado atual = `main` @ `2992837`, **287 testes**.

---

## 0. TL;DR — onde paramos

Sessão de hoje (nuvem, 2026-07-02) foi de **revisão + skill**, não de scan:

1. **A skill do scanner de selados da Liga NÃO existia no GitHub** (o operador
   achava que sim; foi verificado em todas as branches dos 12 repos). Ela foi
   **criada e mergeada**: `.claude/skills/liga-sealed-scan/SKILL.md` — o caminho
   único de RODAR e ENTREGAR o scan de selados (formato MYP adaptado a selados,
   tabela verbatim do `scripts/snapshot.py`). Qualquer sessão que clonar o repo
   (local ou nuvem) já a enxerga automaticamente.
2. **Política SEM PISO firmada** (PR #64): selado não tem piso de preço — o piso
   R$50 da frota vale **só para cartas avulsas (singles)**. `CLAUDE.md`, docstring,
   código (`min_price > 0` gate) e 2 testes agora dizem a mesma coisa que o
   `config.yaml` (`filters.min_brazil_price_brl: 0`).
3. **`run_liga_local.py` agora SEMPRE termina na entrega**: o snapshot markdown
   virou default (antes precisava lembrar do `--snapshot`; `--no-snapshot` ficou
   só para debug do coletor).
4. **Nenhum scan foi rodado hoje** — a nuvem não alcança a Liga (Cloudflare barra
   datacenter) e não havia `results/` no clone. O scan de produção é o próximo
   passo, LOCAL.

---

## 1. Estado do repositório

- `main` @ `2992837`. **287 testes** (`python -m pytest tests/ -q`). Working tree limpo.
- Skill: `.claude/skills/liga-sealed-scan/SKILL.md` (ativa em qualquer sessão no repo).
- Piso: `config.yaml → filters.min_brazil_price_brl: 0` (SEM piso; não reintroduzir).
- Threshold: `deal_criteria.min_total_margin_pct: 0.30` (**fração** = 30%).

### PRs desta sessão (todos mergeados)
| PR | O que entrou |
|---|---|
| #64 | Política SEM PISO firmada em docs/código/testes (era o branch `docs/sealed-no-price-floor`, pendente desde 28/06) |
| #65 | Skill `liga-sealed-scan` + seção "📤 Como rodar e entregar" no CLAUDE.md + snapshot default no `run_liga_local.py` + rodapé do snapshot sem "preço baixo" |
| #66 | (de outra sessão) sync do `/auto` da frota |

---

## 2. ⏳ PENDÊNCIAS para a sessão local (ordem de prioridade)

1. **Atualizar o clone local**: `git pull origin main` em
   `C:\Users\mathe\sealed-scanner` (traz a skill, o snapshot default e a política
   sem piso).
2. **Rodar o SCAN DE PRODUÇÃO completo** (herdada do handoff 06-27 — as margens ao
   vivo dos ~50 SKUs novos de latas/boxes/prerelease nunca foram vistas):
   ```powershell
   cd C:\Users\mathe\sealed-scanner
   .venv\Scripts\python.exe run_liga_local.py
   ```
   O run já imprime e salva a entrega no fim (`snapshots\scan-<data>.md`, técnica +
   didática) — não precisa de flag.
3. **Entregar**: colar o conteúdo do `snapshots\scan-<data>.md` **VERBATIM** no
   chat (é o que a skill `liga-sealed-scan` manda — não montar tabela à mão, não
   mandar XLSX, mostrar todas as linhas incl. RED).
4. **Higiene de skill duplicada**: o operador criou em algum momento uma skill
   local de selados que nunca chegou ao GitHub. Se existir algo parecido em
   `~/.claude/skills/` (ou `%USERPROFILE%\.claude\skills\`) da máquina local,
   conferir e **remover/substituir pela do repo** — uma fonte de verdade só.

---

## 3. Invariantes-lembrete (não negociar)

- **SEM piso de preço** para selado (piso R$50 = só singles). Único critério de
  GREEN: margem bruta ≥ 30% (fração `0.30`). Margem > 200% → RED `margem_anomala`.
- **Entrega** = tabela do `scripts/snapshot.py` colada verbatim (agrupada por
  produto, `Links` = `[oferta](url) · [TCG](url)`), todas as linhas.
- **Nunca inventar preço; nunca recomendar compra** — capital é decisão do operador.

Detalhe completo: `.claude/skills/liga-sealed-scan/SKILL.md` e a seção "📤" do
`CLAUDE.md`.
