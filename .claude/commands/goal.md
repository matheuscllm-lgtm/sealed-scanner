---
description: Mostra status do GOALS.md (sem args) OU executa o plan ativo ponta-a-ponta com revisor (`/goal execute`)
allowed-tools: Read, Write, Edit, Bash, Grep, Glob, Task, TaskCreate, TaskUpdate, TaskList
---

Você foi invocado pelo comando `/goal` do projeto TCG Sealed Arbitrage Scanner.

**Argumento recebido:** `$ARGUMENTS`

---

## Modo A — sem argumento (`/goal`): status check

Se `$ARGUMENTS` estiver vazio ou for `status`:

Leia o arquivo `GOALS.md` na raiz do repositório e apresente:

1. **Em andamento agora** — o item ativo, em uma linha. Se houver mais de um, destaque o de maior prioridade.
2. **Backlog priorizado** — lista ordenada, máximo 8 itens. Use checkboxes literais do arquivo (`- [ ]` / `- [x]`).
3. **Feito recente** — últimos 3-5 itens marcados como concluídos.

Regras de apresentação:
- Mantenha o texto sucinto. Não floreie nem reformule descrições.
- Se um item tiver tag de prioridade (P0/P1/P2), preserve.
- Se houver seção "Notas / contexto", mostre só se for relevante pro foco atual.
- Termine com uma sugestão de 1 linha do próximo passo prioritário, e nada mais.

Se o arquivo não existir, sugira criá-lo com `touch GOALS.md` e pare.

**NÃO execute nada nesse modo. Só leia e reporte.**

---

## Modo B — `/goal execute`: orquestração ponta-a-ponta com revisor

Se `$ARGUMENTS` contiver `execute` (ou aliases: `run`, `go`, `executar`):

### Passo 0 — Pre-flight

1. Leia `GOALS.md`. Identifique o item P0 marcado como "Em andamento agora" que aponta pra um arquivo `PLAN.md`-style (procure por links markdown apontando pra `.md` na seção "Em andamento agora", ex.: `POOL-FILL-PLAN.md`).
2. Se não encontrar plan vinculado, **PARE** e reporte: "Nenhum P0 com plan vinculado em GOALS.md. Edite manualmente e reexecute."
3. Leia o plan vinculado integralmente. Confirme com o operador via texto curto: "Vou executar [PLAN_TITLE] — N fases. Reviewer entre cada fase. Confirmar?". Aguarde resposta. Se operador disser não/parar, abortar.
4. Verifique git status: se houver mudanças não commitadas, **PARE** e reporte. Plan execution exige árvore limpa.
5. Crie tasks via `TaskCreate` — 1 task por fase + 1 task de revisor por fase. Marque a primeira como `in_progress`.

### Passo 1 — Loop fase-a-fase

Para cada fase do plan, em ordem:

**a) Executor (você mesmo):**
- Releia a seção da fase no PLAN.md.
- Liste arquivos a serem tocados.
- Leia esses arquivos integralmente antes de editar (regra anti-erro: nunca edite sem ler).
- Implemente as tarefas da fase.
- Rode os testes/smoke checks da seção "Aceitação" da fase.
- Faça commit atômico com mensagem `phase N: <título da fase>`.
- Marque task `completed`.

**b) Reviewer (spawne via Task tool):**
- Use `subagent_type: "sealed-reviewer"`.
- Prompt do reviewer (preencha placeholders):
  ```
  Revisar Fase {N} ({nome}) do plan {PLAN_PATH}.

  Diff da fase: rode `git diff HEAD~1 HEAD` pra ver.
  Acceptance criteria da fase (lista exata): [cole as bullets de Aceitação]

  Sua tarefa:
  1. Para CADA item de acceptance, rode o check correspondente (Bash/Read/test).
  2. Verifique que o diff realmente contém o que o commit message afirma (não há claims sem código).
  3. Verifique que arquivos não-relacionados NÃO foram tocados (fase atômica).
  4. Procure por silent failures: try/except bare, print('error') em vez de raise, fallbacks sem log.
  5. Retorne veredito estruturado:
     - PASS (todos acceptance bateram, sem findings críticos)
     - FIX_NEEDED (findings específicos com file:line + sugestão de fix)
     - BLOCKED (não consegui verificar — explique o quê)

  NÃO modifique código. Você é read-only.
  ```
- Aguarde o veredito.

**c) Despacho do veredito:**
- Se `PASS`: marque task do reviewer `completed`, avance pra próxima fase.
- Se `FIX_NEEDED`: aplique fixes específicos do reviewer (em novo commit `phase N fix: <findings>`), respawne reviewer com mesmo prompt. Limite: 3 iterações por fase. Se ainda não passar, PARE e reporte ao operador.
- Se `BLOCKED`: PARE e reporte ao operador o que o reviewer não conseguiu verificar.

### Passo 2 — Encerramento

Após todas fases passarem:

1. Atualize `GOALS.md`: mova o item P0 ativo pra "Feito recente" com data, e promova o próximo P1 (se houver) pra ativo.
2. Gere `sealed/snapshots/plan-completion-<plan-name>-<data>.md` com:
   - Resumo das fases.
   - Commits criados (output de `git log --oneline -<N> --since=<inicio>`).
   - Findings do reviewer por fase (se houve FIX_NEEDED, registre).
   - Próximos passos do plan (se "Fora de escopo" listou v2 items).
3. Reporte ao operador: "[PLAN_TITLE] executado. N commits. Reviewer aprovou todas fases. Snapshot em ...".

### Regras gerais de execução

- **NÃO pule fases** (mesmo que pareçam triviais).
- **NÃO modifique** o PLAN.md durante execução (se descobrir gap, registre no snapshot final).
- **NÃO comprime** dois commits em um.
- Se um teste falhar durante implementação, NÃO siga em frente — trate como FIX_NEEDED auto-detectado.
- Se reviewer pedir fix que contraria explicitamente o PLAN.md, escalone ao operador.
- Sempre que o plan exigir input do operador (CEP, cotação, etc.), PARE e peça. Não invente valores.

---

## Modo C — `/goal help`: mostre essa ajuda

Se `$ARGUMENTS` for `help` ou `--help` ou `-h`:

Mostre uma versão condensada das 2 modos acima (3-5 linhas cada).
