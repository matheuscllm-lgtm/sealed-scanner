# Checklist manual — tornar o repositório público (discreto)

> Tudo que o Claude **não** consegue fazer por você (mudanças de configuração no
> site do GitHub, e virar o repo público). Faça **nesta ordem**. O objetivo é
> reduzir descoberta casual — **não** é segurança real: qualquer pessoa com o
> link verá tudo.
>
> ⚠️ **Este repo é PRIVADO hoje.** Virar público é a maior mudança. Confirme que
> o PR de preparação já foi mergeado no `main` (ele tira os dados de deal do
> repositório e neutraliza o README) **antes** de flipar a visibilidade.

## 0. Pré-checagem (1 min)

- [ ] O PR `chore/prepare-public-release` está **mergeado** no `main`.
- [ ] Apague os branches remotos antigos (o Claude **não** apaga branches por
      regra). Rode no seu terminal:
      ```bash
      git push origin --delete chore/amazon-live-progress
      git push origin --delete data/us-reference-2026-06-09
      git push origin --delete docs/binder-price-audit
      git push origin --delete feat/browser-mode-ml-amazon
      git push origin --delete feat/delivery-snapshot-mandatory
      git push origin --delete fix/amazon-503-retry-and-block-signal
      git push origin --delete fix/olx-block-retry-and-proxy
      git push origin --delete review-baseline
      ```
      (Deixe só `main`. Esses branches podem conter listas de deal / preços /
      handoffs de estratégia em commits antigos.)

## 1. Renomear o repositório (nome menos óbvio)

- [ ] `Settings → General → Repository name` → trocar `sealed-arbitrage-scanner`
      por algo neutro, ex.: `price-compare-tool` ou `pc-utils`.
- [ ] (O GitHub cria redirect do nome antigo; se quiser cortar isso, evite usar
      o nome antigo em links públicos.)
- [ ] Atualizar o `git remote` local depois:
      ```bash
      git remote set-url origin https://github.com/matheuscllm-lgtm/<novo-nome>.git
      ```

## 2. Remover description e topics

- [ ] Na página inicial do repo → engrenagem ⚙️ ao lado de "About".
- [ ] Apagar a **Description**.
- [ ] Apagar todos os **Topics** (tags).
- [ ] Desmarcar "Use your GitHub Pages website" e "Releases/Packages" se marcados.

## 3. Desligar features que criam superfície pública

- [ ] `Settings → General → Features`:
  - [ ] **Issues** → desligar.
  - [ ] **Wikis** → desligar.
  - [ ] **Discussions** → desligar.
  - [ ] **Projects** → desligar.
- [ ] `Settings → Pages` → Source = **None** (confirmar que Pages está desligado).

## 4. Conferir secrets de CI (antes de publicar)

- [ ] `Settings → Secrets and variables → Actions` → se você for rodar algum
      workflow de scan no Actions, confirme que existem os secrets usados
      (`FIRECRAWL_API_KEY`, `SCRAPERAPI_KEY`). O workflow de **testes**
      (`tests.yml`) **não** usa nenhum secret e roda offline.
- [ ] Lembre: em repo **público**, os **logs e artifacts** de cada run de um
      workflow de scan ficam baixáveis por qualquer um que achar o repo. Para
      resultados realmente privados, rode o scan **local** (venv + .env), não no
      Actions. (Hoje este repo não tem nenhum workflow de scan — só o de testes.)

## 5. Tornar público

- [ ] `Settings → General → Danger Zone → Change repository visibility`
      → **Make public** → confirmar digitando o nome.

## 6. Validar que o Actions roda de graça

- [ ] Aba **Actions** → workflow **tests** deve rodar sozinho no próximo push/PR
      (ou rode via "Run workflow") e ficar **verde**, em runner `ubuntu-latest`.
- [ ] `Settings → Billing` → confirmar que minutos de Actions de repo público
      **não** consomem cota paga (são gratuitos).

## 7. Pós-publicação (higiene)

- [ ] Rotacionar o `FIRECRAWL_API_KEY` e o `SCRAPERAPI_KEY` se houver qualquer
      dúvida sobre exposição passada (gerar novo no dashboard de cada provedor;
      atualizar o secret no GitHub e o `.env` local).
- [ ] As notas operacionais e de estratégia (`AGENT.md`, `GOALS.md`, `RUNBOOK.md`,
      `snapshots/`, `docs/`) ficam **só no seu disco** (git-ignored). Não as
      re-commite no repo público.
