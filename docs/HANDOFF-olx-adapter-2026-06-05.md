# HANDOFF — Fazer o scraping da OLX funcionar (block CF = reputação de IP)

> **Tarefa isolada pra rodar em outro terminal.** Não bloqueia Liga nem Amazon.
> A **fonte única de verdade** do projeto continua sendo `../README.md`. Este
> arquivo é o briefing pra atingir **scraping de OLX operacional**.
>
> ⚠️ **REVISÃO 2026-06-05 (tarde).** Esta versão **substitui** o rascunho anterior
> de mesma data, cuja premissa central ("block ~50% intermitente, retry simples
> recupera a OLX inteira") foi **falsificada por probe ao vivo** (ver Diagnóstico).
> Hoje o block é **escalação por reputação de IP**, não coin-flip — retry sozinho
> **não** entrega inventário confiável. O caminho real pro objetivo é **rota de
> proxy/render** (Firecrawl/ScraperAPI), reaproveitando o padrão da Liga.

- **Repo:** `C:\Users\mathe\sealed-arbitrage-scanner\` (clone local; GitHub privado `matheuscllm-lgtm/sealed-arbitrage-scanner`)
- **Branch base:** `main` @ `88b8b6f` (working tree limpo na origem desta tarefa)
- **Arquivo a corrigir:** `olx_adapter.py` (218 linhas, **intocado desde o commit inicial** `32915ea`)
- **Infra reaproveitável:** `liga_adapter.py` (abstração `_Fetcher` local/scraperapi) + `FIRECRAWL_API_KEY` **já setada** no ambiente
- **Datado:** 2026-06-05 · diagnóstico por probe ao vivo nesta data
- **Modo:** MANUAL (sem cron). Criar branch + PR (push direto a `main` é gateado).

---

## TL;DR

O adapter da OLX é **maduro e bem escrito**: parse de `__NEXT_DATA__`, detecção de
block CF robusta (403/429/503 + 200-com-block + gzip no corpo de erro),
`SourceBlockedError` honesto, queries amplas por tipo de produto. **O parser e a
detecção de block estão certos — não mexer neles.**

O problema é **acesso**, não código de parse. A OLX serve **Cloudflare WAF managed-rule
/ IP-reputation block** neste IP. Medição ao vivo de hoje:

1. **1ª request (IP "frio") passa** → 50 anúncios parseados OK.
2. Depois de um burst, o WAF **escala e mantém o IP bloqueado** de forma sustentada:
   `30s de cooldown + 10s de espaçamento → 5/5 ainda BLOCKED`.

**Conclusão honesta:** o block **não é** recuperável por retry-com-backoff dentro de
um run (a flag de IP persiste além do cooldown testado). Há também um **modo de
falha novo** não-coberto: `RemoteDisconnected` (conexão fechada sem resposta — não é
`SourceBlockedError`, hoje cai no `[aviso]; continue`).

**O que precisa, em dois níveis:**
- **Tier 1 (barato, robustez correta):** retry+backoff+jitter, tratar
  `RemoteDisconnected`, e só declarar `BLOQUEADA` se TODAS as queries falharem após
  retry. Captura a janela inicial (IP frio) e **para de abortar no 1º block**.
  ⚠️ Honesto: **sozinho NÃO entrega OLX confiável hoje** — pega 1–2 queries e escala.
- **Tier 2 (atinge o objetivo "scraping de OLX funcionando"):** rotear a OLX por
  **render/proxy residencial**, espelhando a abstração `_Fetcher` da Liga. Opção
  recomendada = **Firecrawl** (`FIRECRAWL_API_KEY` já configurada, custo marginal
  ~$0). Alternativa = **ScraperAPI `premium=true`** (mesmo padrão da Liga; exige
  `SCRAPERAPI_KEY` + custo).

---

## Diagnóstico (probe ao vivo 2026-06-05, tarde)

Busca `olx.com.br/brasil?q=booster box pokemon ingles` via `olx_adapter._fetch`:

**Burst 1 — 8 requests, 3s de espaçamento:**
```
0 OK ads=50
1 BLOCKED  Cloudflare WAF block (HTTP 403)
2 RemoteDisconnected  Remote end closed connection without response   <-- modo novo
3 BLOCKED  (HTTP 403)
4 BLOCKED  (HTTP 403)
5 BLOCKED  (HTTP 403)
6 BLOCKED  (HTTP 403)
7 BLOCKED  (HTTP 403)
--- ok=1 blocked=6 err=1 (de 8)
```

**Burst 2 — após 30s de cooldown, 5 requests a 10s de espaçamento (baixa frequência):**
```
0..4 BLOCKED  (HTTP 403)
--- ok=0 blocked=5 (de 5)
```

Leitura:
- **Não é ~50% coin-flip.** É **escalação por reputação de IP**: a 1ª request num
  IP frio passa; depois de poucas requests o WAF flaga o IP e **mantém** o block —
  cooldown de 30s + frequência baixa **não** limparam dentro da janela testada.
- **Parser intacto:** quando passa, vêm **50 anúncios** com título, preço BR,
  `listId`, location, `professionalAd`. `props.pageProps.ads` ainda vale.
- Títulos majoritariamente **PT-BR** — esperado; o matcher filtra via `exclude_terms`
  e só passa quem explicita "Inglês". **Não é bug.**
- **Modo de falha extra:** `http.client.RemoteDisconnected` (o servidor derruba a
  conexão) — transitório, hoje **não** é tratado como retentável nem como block.

> Por que isso contradiz o rascunho da manhã: aquele mediu uma janela em que o IP
> ainda não tinha sido flagado e viu ~50%. A medição da tarde, com o IP já
> "aquecido", expôs a escalação sustentada. **A premissa muda a estratégia:** retry
> vira complemento, não solução.

---

## Contexto atual do trabalho da OLX

- **Onde a OLX entra no pipeline:**
  - `run_all_sources.py --sources olx` (orquestrador multi-fonte)
  - dispatch em `sealed_arbitrage_scanner.py` (`load_listings`, ramo `source == "olx"`)
  - config em `config.yaml:156-162` (`results_per_query: 50`; `delay_seconds` usa default 1.5)
  - banner: `SourceBlockedError → _scan_one status="blocked" → tag "BLOQUEADA"` em `run_all_sources.py:203`
- **Status operacional hoje:** OLX entrega **0 inventário confiável** por causa do
  block. As outras fontes seguem: **Amazon** (com fix de robustez 503 em PR #9) e
  **Liga** (modo local headful / scraperapi). O scanner degrada graciosamente — só
  falha se NENHUMA fonte entregar.
- **Infra de bypass que JÁ existe no projeto (reuso, não do zero):**
  - `liga_adapter.py` tem a abstração limpa `_Fetcher` (abstrato) →
    `_LocalFetcher` (patchright+Chrome, IP residencial, $0) e `_ScraperAPIFetcher`
    (`api.scraperapi.com`, `premium=true`, proxy residencial, custo). Dispatch por
    `config.liga.mode` (`local` | `scraperapi`), `_get_api_key` lê `SCRAPERAPI_KEY`.
    **Esse é o template exato pra OLX.**
  - `FIRECRAWL_API_KEY` **está setada** no ambiente (herdada por todos os scanners) →
    Firecrawl `scrape` (render + bypass CF, retorna HTML) usável **já**, ~$0 marginal.
  - `SCRAPERAPI_KEY` **NÃO** está setada hoje (a Liga roda em `mode=local`).

## O que está FEITO ✅ (não regredir)

- Parser `__NEXT_DATA__` correto: título, preço BR (`R$ 1.412,58`), `listId`,
  location, `professionalAd` (`parse_search_results`, linhas 116-146).
- Detecção de block robusta (`_fetch`, linhas 77-101): tokens CF, gzip no corpo de
  erro, 403/429/503 e 200-com-block. Levanta `SourceBlockedError("olx", msg, hint)`.
- Queries amplas por tipo de produto (`TYPE_TO_QUERY`, linhas 153-162), dedup por
  `listId`. Decisão certa (inventário OLX é esparso por SKU).
- Orquestrador já mapeia `SourceBlockedError → BLOQUEADA` (igual Amazon pós-PR #9).

## O que PRECISA ser feito 🔧

### Tier 1 — robustez de fetch (barato, ship primeiro)
**Prioridade alta. Necessário mas NÃO suficiente pro objetivo.**

1. **Retry+backoff por query + tratar `RemoteDisconnected`.** Hoje o loop
   (`fetch_listings`, linhas 190-200) faz `except SourceBlockedError: raise` —
   aborta a fonte inteira no 1º block. Trocar por: retenta a MESMA query algumas
   vezes com backoff+jitter; `RemoteDisconnected`/`URLError` também são retentáveis;
   só conta a query como perdida após esgotar.
   ```python
   import http.client
   _BLOCK_RETRIES = 4
   _BACKOFF = 4.0  # block escala; backoff mais largo que o da manhã

   blocked = 0
   for i, query in enumerate(queries):
       url = BASE + urllib.parse.quote_plus(query)
       html = None
       for attempt in range(_BLOCK_RETRIES):
           try:
               html = _fetch(url)
               break
           except SourceBlockedError:
               time.sleep(_BACKOFF * (attempt + 1) + random.uniform(0, 1.0))
           except (urllib.error.URLError, http.client.RemoteDisconnected) as exc:
               time.sleep(_BACKOFF * (attempt + 1) + random.uniform(0, 1.0))
       if html is None:
           blocked += 1
           continue
       # ...parse normal...
   ```
2. **`BLOQUEADA` honesto só no fim:** só levantar `SourceBlockedError` se
   `blocked == len(queries) and not all_listings` (mesma trilha do fix da Amazon no
   PR #9 — manter consistência entre adapters).
3. **Jitter no delay entre queries** (linha ~216) — cadência fixa correlaciona com WAF.

> ⚠️ Seja honesto no PR: dado o comportamento de escalação medido hoje, o Tier 1
> recupera a **janela inicial** (IP frio) e para de abortar cedo, mas **não** vai
> entregar OLX cheia de forma confiável. Ele é a base correta; o objetivo real é o
> Tier 2.

### Tier 2 — rota de proxy/render (ATINGE o objetivo de scraping funcionando)
**Prioridade alta pro objetivo. Este é o item que faz a OLX voltar a entregar.**

4. **Abstrair o fetch da OLX num `_Fetcher`, espelhando a Liga.** Adicionar
   `config.olx.mode: urllib | firecrawl | scraperapi` (default `urllib` = comportamento
   atual + Tier 1). Implementar:
   - **`firecrawl` (recomendado, $0 marginal):** GET da URL de busca da OLX via
     Firecrawl `scrape` (formats inclui HTML), e passar o HTML retornado pro
     **mesmo** `parse_search_results` (o `__NEXT_DATA__` vem no HTML renderizado).
     `FIRECRAWL_API_KEY` já está no ambiente. Validar primeiro com 1 URL via skill
     `firecrawl-scrape` / `mcp__firecrawl__firecrawl_scrape` antes de codar o adapter.
   - **`scraperapi` (alternativa paga):** copiar `_ScraperAPIFetcher` da Liga
     (`premium=true`, render se necessário); exige `SCRAPERAPI_KEY`.
   O parser e a detecção de block **não mudam** — só a camada de transporte.
5. **Critério de sucesso do Tier 2:** `python run_all_sources.py --sources olx`
   com `mode=firecrawl` retorna `olx OK anúncios>0` de forma **repetível** (não só
   na 1ª request de IP frio).

### Tier 3 — premissas stale + testes
6. **Corrigir docstring e config (barato):**
   - Docstring `olx_adapter.py:10-17`: "block terminal por requisição" está
     impreciso — é **IP-reputation escalation** (1ª passa, depois sustenta block);
     mitigável por retry parcial + **proxy/render** pra acesso confiável.
   - `config.yaml:158` comentário **"Sem CF, sem auth" está ERRADO** — há CF WAF. Corrigir.
7. **Testes de regressão** (`tests/test_olx.py`, hoje inexistente; padrão em
   `tests/test_amazon.py` do PR #9): `parse_search_results` contra fixture de
   `__NEXT_DATA__` salvo; classificação de block (`_is_block_page` 403/200/gzip);
   loop de retry (mock: block 2× depois OK → recupera; tudo block → `BLOQUEADA`).
   Fixture versionada (já há negação `!tests/fixtures/*.html` no `.gitignore`, do PR #9).
   Rodar: `python -m pytest -q` (hoje **45/45** com os testes da Amazon — não regredir).

---

## Como reproduzir o block (pra validar os fixes)

```bash
cd ~/sealed-arbitrage-scanner
python -u -c "import olx_adapter as o, urllib.parse, time
from lib.errors import SourceBlockedError
url=o.BASE+urllib.parse.quote_plus('booster box pokemon ingles')
for i in range(8):
    try: h=o._fetch(url); print(i,'OK',len(o.parse_search_results(h)))
    except SourceBlockedError: print(i,'BLOCKED')
    except Exception as e: print(i,type(e).__name__,str(e)[:40])
    time.sleep(3)"
```
Espere: 1ª request OK (~50 ads), depois escalada pra BLOCKED sustentado + algum
`RemoteDisconnected`. **Esse é o sinal de que precisa do Tier 2** — se só o Tier 1
fosse suficiente, o cooldown recuperaria, e não recupera.

Validar Tier 2 (Firecrawl) **antes** de codar o adapter:
```bash
# via skill firecrawl-scrape ou MCP — scrape da URL de busca da OLX e conferir
# se o HTML retornado contém <script id="__NEXT_DATA__"> com props.pageProps.ads
```

## Validação end-to-end (depois dos fixes)

```bash
cd ~/sealed-arbitrage-scanner
python build_us_reference.py               # refresca preços US (tcgcsv)
python run_all_sources.py --sources olx    # default urllib (Tier 1)
# e, com a rota de proxy:
# (setar config.olx.mode: firecrawl) && python run_all_sources.py --sources olx
```
**Critério de aceite:**
- **Tier 1 (`urllib`):** quando o IP está frio, banner `olx OK anúncios>0`; quando o
  WAF já escalou, banner `olx BLOQUEADA` honesto (não trava o run; Amazon/Liga seguem).
- **Tier 2 (`firecrawl`):** `olx OK anúncios>0` **repetível** request após request —
  é isso que significa "scraping de OLX funcionando".
- `python -m pytest -q` → 45 + novos testes OLX, todos verdes.

## Entrega
- Branch: `fix/olx-block-retry-and-proxy` (ou 2 PRs: `fix/olx-block-retry` Tier 1,
  depois `feat/olx-firecrawl-fetcher` Tier 2 — não empilhar PRs; ver memória de PR workflow).
- PR(s) contra `main`. Não commitar `results/` nem XLSX de TEMP.
- Não toca README (fonte única) — robustez/transporte de adapter, não invariante. Se
  mudar `config.yaml` (novo `mode` / comentário / knobs), mencionar no corpo do PR.

---

## Objetivos (ordem)

1. **Parar de abortar no 1º block** e tratar `RemoteDisconnected` (Tier 1) — base correta.
2. **OLX voltar a entregar inventário de forma repetível** via Firecrawl (Tier 2) —
   **este é o objetivo central do pedido** ("atingir scraping da OLX funcionando").
3. Premissas stale corrigidas + cobertura de teste (Tier 3) — higiene.

## Armadilhas conhecidas (não repetir)

- **NÃO é o block da Liga.** Liga = Turnstile "Just a moment" (auto-resolve com
  Chrome headful). OLX = **managed-rule WAF / IP reputation** — não há captcha pra
  clicar; a 1ª request passa e depois escala. Saída de acesso = **render/proxy
  residencial** (Firecrawl/ScraperAPI), não headful local.
- **Retry NÃO é a solução, é complemento.** A medição de hoje mostra que cooldown +
  baixa frequência não limpam a flag de IP. Quem prometer "retry recupera a OLX
  inteira" está repetindo a premissa falsificada da manhã.
- **Não fabricar dado.** Se mesmo via proxy a OLX bloquear, reportar `BLOQUEADA`
  honesto (degradação graciosa). O fix nunca é "fingir que passou".
- **Custo é decisão do operador.** Firecrawl já está pago (key setada) → preferir.
  ScraperAPI premium tem custo por request → só com OK do operador.
- **PowerShell vs Bash:** ambiente Windows. Em PS use `$null`, não `/dev/null`.
- **stdout buffer:** `python ... | tee` bufferiza; pra ver progresso use `python -u`.
- **Paralelo à Amazon:** o adapter da Amazon tinha a mesma classe de bug (transitório
  sem retry) — resolvido no **PR #9** (`fix/amazon-503-retry-and-block-signal`). Use
  os fixes da Amazon como referência de estilo (mesma convenção de `SourceBlockedError`
  honesto e fixture versionada).
