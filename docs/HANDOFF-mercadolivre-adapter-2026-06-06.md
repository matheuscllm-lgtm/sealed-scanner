# HANDOFF — Novo scanner de fonte: **Mercado Livre** (selados Pokémon BR)

> **Tarefa isolada pra rodar em outro terminal.** Cria uma 4ª fonte BR
> (`mercadolivre`) ao lado de Amazon, Liga e OLX. Não bloqueia as outras.
> A **fonte única de verdade** do projeto continua sendo `../README.md`
> (invariantes + sequência canônica). Este arquivo é o briefing completo pra
> atingir **scanner do Mercado Livre operacional**.
>
> ⚠️ **Diagnóstico por probe ao vivo 2026-06-06.** Todos os números/seletores
> abaixo foram MEDIDOS, não supostos. Onde for incerto, está marcado como tal.

- **Repo:** `C:\Users\mathe\sealed-arbitrage-scanner\` (clone local; GitHub privado `matheuscllm-lgtm/sealed-arbitrage-scanner`)
- **Branch base:** `main` (working tree limpo). **NÃO** ramificar do branch da OLX/Amazon (não empilhar PRs).
- **Arquivo a criar:** `mercadolivre_adapter.py` (não existe ainda)
- **Infra reusável (copiar, não reinventar):** `olx_adapter.py` — o `_FirecrawlFetcher` + `_make_fetcher` + o padrão `_Fetcher` são o template EXATO. `FIRECRAWL_API_KEY` **já setada** no ambiente.
- **Datado:** 2026-06-06 · diagnóstico por probe ao vivo nesta data
- **Modo:** MANUAL (sem cron). Criar branch + PR (push direto a `main` é gateado).

---

## TL;DR

O Mercado Livre é o maior marketplace BR — inventário de selado Pokémon muito
maior que OLX (48-50 resultados por página, várias páginas por busca). Vale a
4ª fonte. **MAS o acesso é o ponto difícil**, e é mais duro que a OLX:

1. **API oficial fechada:** `api.mercadolibre.com/sites/MLB/search` retorna
   **403 forbidden** sem token OAuth (o ML fechou a Search API pública em ~2024).
2. **HTML direto bloqueado:** `urllib` puro é redirecionado pra
   `mercadolivre.com.br/gz/account-verification` (`suspicious-traffic-frontend`)
   — anti-bot PRÓPRIO do ML (não é Cloudflare WAF como a OLX).
3. **Firecrawl atravessa — mas exige espera maior:** `proxy=stealth` +
   `waitFor=6000` (o mesmo da OLX) **ainda cai no account-verification**.
   Com **`waitFor=15000`** o device-check do ML clareia e a página real volta:
   **1.46 MB, 50 resultados, 1585 blocos de preço.** ✅

**Conclusão honesta:** o adapter do ML deve nascer **firecrawl-first** (não
`urllib-first` como a OLX). O `urllib` puro não vale a pena aqui — cai direto no
anti-bot, sem nem a "janela de IP frio" que a OLX às vezes dá. O caminho pronto
hoje é **Firecrawl com `waitFor≈12-15s`**, espelhando o `_FirecrawlFetcher` que
já existe no `olx_adapter.py`. O parser é DOM/CSS (BeautifulSoup), igual Amazon —
o ML **não** expõe `__NEXT_DATA__` (OLX) nem `preloadedState` (legado ML morto).

Rota alternativa de longo prazo (mais robusta e grátis, mas exige setup):
**API oficial via OAuth** — ver §11.

---

## 1. Intenção (por que ML, e o que "pronto" significa)

- **Objetivo:** mais uma fonte BR de oferta de selado, cruzada contra o preço
  US (TCGPlayer) pelo MESMO pipeline. Mais fontes = mais chance de pegar um
  anúncio mal-precificado antes do mercado.
- **"Pronto" = critério de aceite (§13):** `run_all_sources.py --sources mercadolivre`
  retorna `mercadolivre OK anúncios>0` de forma **repetível** (não só na 1ª
  request), as linhas casam contra o registry e classificam GREEN/YELLOW/RED
  pelas MESMAS regras de margem das outras fontes, e `pytest` fica verde.
- **Escopo:** só **selado** (booster box, ETB, bundle, collection box, tin,
  blister, sleeved booster) e só **inglês** (o matcher filtra o resto). O ML é
  dominado por **PT-BR/COPAG** — isso é esperado e filtrado, não é bug.

---

## 2. Diagnóstico de acesso (probe ao vivo 2026-06-06)

| Rota | Resultado | Detalhe |
|------|-----------|---------|
| API `sites/MLB/search` (sem token) | ❌ **403** | `{"message":"forbidden",...}` — exige OAuth |
| HTML `lista.mercadolivre.com.br/...` via `urllib` | ❌ **anti-bot** | redirect → `gz/account-verification` (`suspicious-traffic-frontend`), 34 KB, 0 resultados |
| Firecrawl `proxy=stealth, waitFor=6000` | ❌ **anti-bot** | ainda cai no `account-verification`, 33 KB |
| Firecrawl `proxy=stealth, waitFor=15000` | ✅ **PASSOU** | 1.46 MB, `ui-search-result`=50, `andes-money-amount`=1585 |

Leitura:
- O anti-bot do ML é um **device-check com challenge JS** que precisa de TEMPO
  pra resolver (≈12-15s), diferente do WAF da OLX (que o stealth fura em 6s) e
  do Turnstile da Liga (Chrome headful). É intermitente por reputação —
  registrar como tal e tratar `account-verification` no HTML como sinal de block.
- Quando passa, vem a página de busca **server-side completa** com os cards.
- **Não é** o mesmo block da OLX. Não copiar a premissa "stealth+6s resolve".

---

## 3. Como um source novo se integra (arquitetura — leia antes de codar)

O adapter **não faz matching nem economia**. Ele só **entrega listings crus**
(título + preço + url). O scanner (`sealed_arbitrage_scanner.py`) faz todo o
resto, igual já faz pra Amazon/OLX/Liga. Pontos de plugue:

1. **Dispatch** — `sealed_arbitrage_scanner.py::load_listings` (linha ~246).
   Adicionar um ramo:
   ```python
   if source == "mercadolivre":
       import mercadolivre_adapter
       listings = mercadolivre_adapter.fetch_listings(config, registry_raw or [])
       return listings, f"mercadolivre (mercadolivre.com.br — busca ao vivo, {len(listings)} listagens)"
   ```
   e incluir `"mercadolivre"` nos `choices` do `--source` (linha ~948) e na
   mensagem de erro.
2. **Orquestrador** — `run_all_sources.py`: `DEFAULT_SOURCES = ["amazon", "liga", "olx"]`
   (linha ~36) → adicionar `"mercadolivre"`. O banner
   `SourceBlockedError → status="blocked" → "BLOQUEADA"` (linha ~203) já é
   genérico; nada a mudar lá.
3. **Contrato do listing** — cada dict que `fetch_listings` devolve precisa, no
   mínimo, de:
   - `title` (str) → o scanner casa por `row.title_br` (match) e rejeita
     idioma não-inglês / cartas avulsas sozinho.
   - `price_brl` (float) → usado em `classify` (filtro `min_brazil_price_brl`,
     cálculo de margem).
   - `seller`, `url` (str) → exibição/auditoria.
   - `id` (str, único), `source="mercadolivre"` → rastreio.
   - opcional: `qty_avail` (int|None), `location`, `query`.
   Ver o dict que o `olx_adapter.parse_search_results` monta — copie a forma.
4. **Matcher (compartilhado, NÃO tocar)** — `match_listing(title, registry)`
   (linha ~305) casa `set_terms` **E** `type_terms`, exclui `exclude_terms`, com
   a regra estrutural `era_umbrella` (NÃO enumerar sub-sets em exclude — ver
   memória/PR #6). O registry (`sku_registry.yaml`, 105 SKUs) já tem
   `exclude_terms` com `copag/portugues/ptbr/japones/...` → **anúncios PT-BR do
   ML são filtrados automaticamente**.
5. **Classificação (compartilhada)** — `classify` (linha ~375): NONE/REVIEW/HIGH
   no match; GREEN/YELLOW/RED na margem. O adapter não opina nisso.

> Resumo: **escrever o adapter do ML é 90% transporte (Firecrawl) + 10% parser
> (DOM→dict)**. Toda a inteligência de match/margem é reaproveitada.

---

## 4. Infra reusável (copiar do `olx_adapter.py`)

O `olx_adapter.py` (pós-PR #10) já tem **exatamente** o que o ML precisa de
transporte. Copiar/adaptar:
- `_Fetcher` (abstrato), `_FirecrawlFetcher` (POST `https://api.firecrawl.dev/v2/scrape`,
  `formats=['rawHtml']`, `location={country:'BR'}`, `proxy='stealth'`, `waitFor`),
  `_make_fetcher`, `_load_dotenv_if_present`, e o tratamento `_is_block_page`.
- **Diferenças pro ML:**
  - `waitFor` default **12000-15000** (não 6000). Expor como
    `config.mercadolivre.firecrawl_wait_ms`.
  - `_is_block_page` do ML detecta `account-verification` / `suspicious-traffic`
    (tokens próprios), não os tokens Cloudflare. Adaptar a lista.
  - **firecrawl-first:** `config.mercadolivre.mode` default = `firecrawl`
    (a OLX é `urllib`; o ML não — urllib puro não passa). Manter um modo
    `urllib` opcional só por simetria/futuro, mas documentar que hoje não rende.

---

## 5. Estrutura da página + seletores (VALIDADOS ao vivo)

Página: `https://lista.mercadolivre.com.br/games-brinquedos/pokemon-booster-box`
(SSR; sem `__NEXT_DATA__`, sem `preloadedState`). Parse via BeautifulSoup+lxml:

| Dado | Seletor (validado) | Exemplo medido |
|------|--------------------|----------------|
| Container do anúncio | `li.ui-search-layout__item` (≡ `div.poly-card`) | 48-50 por página |
| Título | `a.poly-component__title` | "Booster Box Pokémon Escarlate e Violeta Raio Preto..." |
| Preço inteiro | `span.andes-money-amount__fraction` | `319` |
| Preço centavos | `span.andes-money-amount__cents` | `21` → **R$ 319,21** |
| Link | `a.poly-component__title['href']` | `https://www.mercadolivre.com.br/...` |
| Vendedor | `span.poly-component__seller` | `COPAG` (PT-BR → filtrado) |
| Condição (novo/usado) | **A CONFIRMAR** (ver §10/⚠️) | não apareceu no 1º card como texto simples |

Parser de preço: juntar `fraction` + `,` + `cents` e reusar a lógica
`_price_to_float` (ponto=milhar, vírgula=decimal) que já existe no OLX/Amazon.
Cuidado: o ML repete `andes-money-amount` pra **preço cheio riscado + preço com
desconto**; pegar o preço do bloco principal do card (`.poly-component__price` /
`.poly-price__current`), não o riscado (`.andes-money-amount--previous`).

---

## 6. Métricas, alvos e margens (HERDADOS — não inventar números)

O ML usa **as mesmas** regras econômicas das outras fontes. Estão centralizadas
em `config.yaml` e impressas no relatório (auditável). **Não criar critério novo
pro ML** — só plugar a fonte.

- **Classificação (só margem BRUTA, invariante do operador 2026-06-02):**
  `margem_total = (preço_US − preço_BR) / preço_BR`
  - **GREEN** ≥ `min_total_margin_pct` = **0.40** (40%)
  - **YELLOW** entre `review_floor_pct` **0.30** e 0.40 (revisar)
  - **RED** abaixo de 0.30, ou sem match, ou abaixo do preço mínimo
  - Equivalências: 40% de margem total ≈ 29% mais barato que os EUA.
- **Filtro de entrada:** `filters.min_brazil_price_brl` = **R$ 25** (corta
  parts/itens incompletos).
- **Custos (informativo, NÃO definem cor — margem líquida é alerta, não gate):**
  `platform_fee_pct` 0.13 + `payment_fee_pct` 0.03 + `fx_spread_pct` 0.02 sobre
  o preço de venda US; `international_shipping_brl` 90 + `three_pl_brl` 25 fixos.
  Frete BR modelo `flat`: `flat_base_pct` 5% + `flat_per_seller_brl` R$17/loja extra.
- **Câmbio:** `currency.mode=fetch` (AwesomeAPI ao vivo; fallback `usd_brl` 5.05).
- **Alvos (targets) = o registry curado** (`sku_registry.yaml`, 105 SKUs, EN).
  O ML é especialmente forte em **ETBs** e **booster boxes** importados; provável
  bom rendimento em sets recentes (Surging Sparks, Prismatic Evolutions,
  Journey Together, Destined Rivals) e ME EN. Não ampliar o registry no PR do
  adapter — se aparecer selado EN fora do registry, o scanner já sinaliza
  `sem_match_no_registry` (curadoria é trabalho separado).

> Nenhuma dessas métricas é "do ML" — todas vivem no `config.yaml` e são
> compartilhadas. O adapter só alimenta `price_brl` + `title`; o resto é o
> pipeline existente.

---

## 7. O que está FEITO (padrões a seguir, não regredir)

- **3 adapters irmãos** com o mesmo contrato: `amazon_adapter`, `olx_adapter`,
  `liga_adapter`. Use-os como referência de estilo.
- **Transporte Firecrawl pronto** no `olx_adapter` (PR #10) — copiar.
- **`SourceBlockedError` honesto** (`lib/errors.py`): adapter levanta quando a
  fonte nega acesso; orquestrador marca `BLOQUEADA` (não-fatal, as outras
  fontes seguem). O ML deve seguir o MESMO contrato: se o anti-bot vencer todas
  as queries e nada for coletado → `SourceBlockedError("mercadolivre", ...)`.
- **Fixture versionada + testes herméticos:** padrão em `tests/test_olx.py` +
  `tests/fixtures/olx_search.html` (negação `!tests/fixtures/*.html` no
  `.gitignore`). Replicar pro ML.
- **`min_total_margin` honesto fim-de-run:** padrão Amazon/OLX — só declarar
  BLOQUEADA quando TODAS as queries falharem **e** nada coletado.

---

## 8. O que PRECISA ser feito 🔧

### Núcleo
1. **`mercadolivre_adapter.py`** — firecrawl-first:
   - `_FirecrawlFetcher` adaptado (waitFor 12-15s; `_is_block_page` detecta
     `account-verification`/`suspicious-traffic`).
   - `parse_search_results(html)` via BeautifulSoup nos seletores da §5.
   - `_derive_queries(registry)` — ver §9 (custo!).
   - `fetch_listings(config, registry)` — loop por query, dedup por id do
     anúncio (extrair do href, ex.: `MLB-\d+`), `SourceBlockedError` honesto no fim.
2. **Filtro condição = NOVO** ⚠️ — o ML vende **usado** também. Selado usado =
   caixa aberta/danificada, fora do escopo. Detectar a condição no card e
   **descartar usados** (ou marcar). CONFIRMAR o seletor real (não apareceu no
   1º card — pode estar em `.poly-component__condition`, num label do card, ou
   só na página do produto). Se não der pra extrair na listagem, documentar a
   limitação e deixar passar (o matcher não pega isso sozinho).
3. **Dispatch + orquestrador** — §3 itens 1 e 2.

### Config
4. **Bloco `mercadolivre:` no `config.yaml`:**
   ```yaml
   mercadolivre:
     # ML tem anti-bot próprio (account-verification/suspicious-traffic).
     # urllib puro NÃO passa → firecrawl-first. waitFor maior que a OLX
     # (device-check precisa de ~12-15s pra clarear).
     mode: firecrawl
     firecrawl_proxy: stealth
     firecrawl_wait_ms: 14000
     results_per_query: 50
     delay_seconds: 1.5
     # firecrawl_api_key: ""   # NÃO commitar; prefira FIRECRAWL_API_KEY / .env
   ```

### Testes (Tier higiene)
5. **`tests/test_mercadolivre.py`** (mock, sem rede) + fixture
   `tests/fixtures/mercadolivre_search.html` (recortar um `ui-search-layout`
   real com 2-3 cards: 1 EN válido, 1 PT-BR/COPAG, 1 sem preço): parser
   (seletores §5, preço fraction+cents), detecção de block
   (`account-verification`), retry/BLOQUEADA honesto, Firecrawl fetcher (mock do
   POST). Rodar `python -m pytest -q` — não regredir o baseline.

---

## 9. Custo & estratégia de queries (decisão de capital — confirmar)

Firecrawl `stealth` + `waitFor 14s` **custa créditos por scrape** (stealth é o
tier mais caro; ~vários créditos/página). Logo o **nº de queries importa**:

- **Opção A (recomendada p/ v1, barata): queries por TIPO de produto** (igual
  OLX) — ~8 buscas amplas (`booster box pokemon ingles`, `elite trainer box
  pokemon ingles`, ...). Custo ≈ 8 scrapes/scan. O ML tem inventário grande, então
  busca ampla já traz bastante; o matcher filtra. **Comece por aqui.**
- **Opção B (cara, cobertura máxima): query por SKU** (igual Amazon) — 105
  buscas/scan. Cobertura melhor em set específico, mas ~13× o custo. Só se a
  Opção A deixar buracos medidos.
- **Paginação:** cada query pode ter várias páginas (`_Desde_51`, `_Desde_101`).
  Pra v1, **1 página (50 itens) por query** já basta; paginar é otimização futura
  (mais custo). Documentar o cap (não truncar em silêncio — `log` o que ficou de fora).

> Firecrawl já está pago (key setada) → é a rota recomendada. **Não** introduzir
> ScraperAPI premium sem OK de capital do operador.

---

## 10. Validação (reproduzir antes/depois de codar)

**Confirmar o block (urllib) e o bypass (Firecrawl):**
```bash
cd ~/sealed-arbitrage-scanner
# 1) urllib cai no anti-bot:
python -u -c "import urllib.request as u; r=u.urlopen(u.Request('https://lista.mercadolivre.com.br/pokemon-booster-box-ingles', headers={'User-Agent':'Mozilla/5.0'}), timeout=30); print(r.geturl())"
#   -> .../gz/account-verification?...  (anti-bot)

# 2) Firecrawl com waitFor alto passa (REST direto, FIRECRAWL_API_KEY no env):
python -u -c "
import os,json,urllib.request
p={'url':'https://lista.mercadolivre.com.br/games-brinquedos/pokemon-booster-box','formats':['rawHtml'],'location':{'country':'BR'},'proxy':'stealth','waitFor':15000}
req=urllib.request.Request('https://api.firecrawl.dev/v2/scrape',data=json.dumps(p).encode(),headers={'Authorization':'Bearer '+os.environ['FIRECRAWL_API_KEY'],'Content-Type':'application/json'})
h=json.load(urllib.request.urlopen(req,timeout=200))['data']['rawHtml']
print('len',len(h),'suspicious=', 'account-verification' in h.lower(),'results=',h.count('ui-search-result'))"
#   -> len ~1.4M  suspicious=False  results=50
```

**End-to-end (depois do adapter):**
```bash
python build_us_reference.py                       # refresca preços US (tcgcsv)
python run_all_sources.py --sources mercadolivre   # default firecrawl
```

**Critério de aceite (§13):**
- `mercadolivre OK anúncios>0` **repetível** (2 runs seguidos entregam cards).
- Anúncios PT-BR/COPAG caem por `idioma_nao_ingles`/`exclude_terms` (esperado).
- Quando o anti-bot vence tudo: `mercadolivre BLOQUEADA` honesto (não trava o run).
- `python -m pytest -q` → baseline + novos testes ML, todos verdes.

---

## 11. Rota alternativa (futuro): API oficial via OAuth

Mais robusta e **grátis** a longo prazo, mas exige setup que o scrape não exige:
- Registrar uma app em `developers.mercadolivre.com.br` → `client_id` + `client_secret`.
- Fluxo OAuth (`client_credentials` ou `authorization_code`) → `access_token`.
- `GET api.mercadolibre.com/sites/MLB/search?q=...` **com** `Authorization: Bearer`
  → JSON estruturado (`price`, `condition:new`, `sold_quantity`, `seller`,
  `shipping.free_shipping`) — muito mais limpo que raspar DOM, e resolve o
  filtro novo/usado de graça (`condition`).
- **Trade-off:** setup de credenciais + manejo de refresh token + termos de uso
  da API. Pra **v1**, o scrape via Firecrawl é o caminho pronto e consistente
  com a OLX (zero setup novo). Deixar a API OAuth como **evolução v2** documentada.

---

## 12. Armadilhas conhecidas (não repetir)

- **NÃO é o block da OLX.** OLX = Cloudflare WAF, stealth+6s fura. ML = anti-bot
  próprio (`suspicious-traffic`), precisa **waitFor ~12-15s**. Copiar o número da
  OLX (6s) = cair no `account-verification`.
- **NÃO é o block da Liga.** Liga = Turnstile, Chrome headful resolve. ML headful
  local provavelmente cai no mesmo anti-bot (mesma classe de reputação de IP) —
  **não** assumir que headful resolve sem medir.
- **Novo vs Usado:** o ML vende usado. Selado usado está fora do escopo —
  filtrar `condition=new`. (A API OAuth daria isso de graça; no scrape, confirmar
  o seletor.) Não fabricar: se não der pra ler a condição, documentar a lacuna.
- **PT-BR/COPAG domina** — esperado e filtrado pelo `exclude_terms` do registry
  (`copag` já está lá). Não é bug. Só passa quem explicita "Inglês"/"English".
- **Preço com centavos em `<span>` separado** (`fraction` + `cents`) e **preço
  riscado** (`andes-money-amount--previous`): pegar o preço atual do card, não o
  de tabela/riscado.
- **Custo Firecrawl por query** (stealth caro) — começar por queries amplas por
  tipo (§9-A), 1 página, e medir antes de escalar.
- **Anti-bot intermitente:** mesmo com waitFor alto pode falhar às vezes. Tratar
  `account-verification` no HTML como block → `SourceBlockedError` honesto;
  retry com backoff entre queries.
- **PowerShell vs Bash:** ambiente Windows. Em PS use `$null`, não `/dev/null`.
- **stdout buffer:** use `python -u` pra ver progresso; `harden_stdout()` pra
  títulos PT-BR no console Windows (ver `lib/console`).
- **`__NEXT_DATA__`/`preloadedState` NÃO existem** na busca do ML hoje (medido
  `preloadedState=False`). Parser é DOM/CSS (igual Amazon), não JSON embutido
  (≠ OLX). Não procurar JSON que não está lá.

---

## 13. Entrega

- **Branch:** `feat/mercadolivre-adapter` (do `main`; não empilhar com OLX/Amazon).
- **PR** contra `main`. Não commitar `results/` nem XLSX. Fixture HTML versionada
  (recorte pequeno, não a página de 1.4 MB inteira).
- **Toca:** `mercadolivre_adapter.py` (novo), `sealed_arbitrage_scanner.py`
  (dispatch), `run_all_sources.py` (DEFAULT_SOURCES + banner já genérico),
  `config.yaml` (bloco `mercadolivre`), `tests/` (novos). **Não toca README**
  (invariante) — é fonte/transporte, não regra de negócio. Mencionar no corpo
  do PR as mudanças de `config.yaml`.

---

## 14. Objetivos (ordem)

1. **Atravessar o anti-bot** de forma repetível (Firecrawl stealth + waitFor
   ~14s) e parsear a busca (seletores §5) → `mercadolivre OK anúncios>0`. **Núcleo.**
2. **Filtrar novo vs usado** + dedup + `SourceBlockedError` honesto.
3. **Plugar no pipeline** (dispatch + orquestrador + config) e classificar pelas
   métricas compartilhadas (§6).
4. **Testes + fixture** (higiene) e validação end-to-end.
5. (futuro/v2) Avaliar a **API oficial OAuth** (§11) como rota mais robusta.
