# HANDOFF — Correção do adapter Amazon (503 anti-bot)

> **Tarefa isolada pra rodar em outro terminal.** Não bloqueia Liga nem OLX.
> A **fonte única de verdade** do projeto continua sendo `../README.md`. Este
> arquivo é só o briefing desta correção pontual.

- **Repo:** `C:\Users\mathe\sealed-arbitrage-scanner\`
- **Branch base:** `main` @ `88b8b6f` (working tree estava limpo)
- **Arquivo a corrigir:** `amazon_adapter.py` (125 linhas, **intocado desde o commit inicial** `32915ea`)
- **Datado:** 2026-06-05 · diagnóstico por probe ao vivo nesta data
- **Modo:** MANUAL (sem cron). Criar branch + PR (push direto a `main` é gateado).

---

## TL;DR

O adapter da Amazon BR **funciona quando a Amazon responde**, mas a Amazon serve
**HTTP 503 intermitente** (anti-bot) ao `urllib` puro — medido **~1 em 3 requests**
hoje. O adapter **não tem retry** e **não sinaliza bloqueio**: cada SKU que pega um
503 é **silenciosamente descartado** (`print [aviso]; continue`), e se a Amazon
derrubar tudo o orquestrador ainda marca `status=ok n_listings=0` em vez de
`BLOQUEADA`. Resultado: cobertura furada e silenciosa, sem o operador saber.

**O que precisa:** (1) retry com backoff no fetch, (2) `SourceBlockedError` honesto
quando a taxa de bloqueio for alta. Nada de reescrever o adapter.

---

## Diagnóstico (probe ao vivo 2026-06-05)

Busca `amazon.com.br/s?k=...` via `amazon_adapter._fetch`:

```
try0: OK   bytes=487573  results=13
try1: HTTPError 503 Service Unavailable
try2: OK   bytes=497001  results=13
```

- **Intermitente, não bloqueio total.** ~33% de 503 numa janela curta.
- Quando passa, o parse funciona: **13 resultados** com título + preço BR + ASIN + URL.
  Os seletores `div[data-component-type="s-search-result"]` e
  `span.a-price > span.a-offscreen` **ainda valem** (nada a mexer aí).
- O 503 correlaciona com **frequência** de request. O adapter dispara **1 busca por
  SKU do registry (~105 requests)** a `delay_seconds: 1.5` → martela a Amazon e
  aumenta a chance de anti-bot.

> Histórico: no scan de 2026-06-03 a Amazon **rodou** e foi ela que expôs o bug de
> over-match de era (motivou o fix `era_umbrella`, PR #6). Ou seja, o adapter
> **entrega valor quando não toma 503** — o problema é robustez, não o parser.

---

## O que está FEITO ✅

- Adapter existe e está plugado no orquestrador:
  - `run_all_sources.py --sources amazon`
  - dispatch em `sealed_arbitrage_scanner.py:262-266` (`load_listings`)
  - config em `config.yaml:148-152` (`results_per_sku: 6`, `delay_seconds: 1.5`)
- Parser de busca OK: título, preço (formato BR `R$ 1.412,58`), ASIN, URL — `parse_search_results` (linhas 53-80).
- Dedup por ASIN (`seen_asins`).
- `_derive_query` monta query por SKU (set + product_type + "ingles" se EN); SKU pode dar override via `amazon_query`.

## O que PRECISA ser feito 🔧 (em ordem de prioridade)

### 1. Retry com backoff no fetch — **prioridade alta**
Hoje, `amazon_adapter.py:106-109`:
```python
try:
    html = _fetch(url)
except Exception as exc:
    print(f"  [aviso] busca Amazon falhou para {sku.get('id')}: {exc}")
    continue          # <-- 1 único 503 mata o SKU pro run inteiro
```
**Fix:** envolver `_fetch` numa retry específica pra 503/429/transitório, com
backoff (ex.: 3 tentativas, sleep 2s/4s + jitter). Sugestão de helper dentro de
`amazon_adapter.py`:
```python
import urllib.error

_RETRYABLE = {503, 429, 500, 502, 504}

def _fetch_retry(url: str, attempts: int = 3, base_sleep: float = 2.0) -> str:
    last = None
    for i in range(attempts):
        try:
            return _fetch(url)
        except urllib.error.HTTPError as e:
            last = e
            if e.code not in _RETRYABLE:
                raise
            time.sleep(base_sleep * (i + 1))  # 2s, 4s, 6s
    raise last
```
e trocar `html = _fetch(url)` por `html = _fetch_retry(url)` na linha 106.

### 2. `SourceBlockedError` honesto quando bloqueio for alto — **prioridade alta**
Hoje o adapter **nunca** levanta `SourceBlockedError`; só o `print [aviso]`. Se a
Amazon 503ar tudo, o orquestrador (`run_all_sources.py:_scan_one`) vê `status=ok,
n_listings=0` — **silencioso e enganoso**. Compare com Liga/OLX, que sobem
`SourceBlockedError` e o banner mostra `BLOQUEADA`.
**Fix:** contar falhas no loop `fetch_listings`; se
`falhas / total_skus >= ~0.6` **e** `len(all_listings) == 0`, levantar
`SourceBlockedError("Amazon BR: 503 anti-bot em N/M buscas")`.
```python
from lib.errors import SourceBlockedError   # já existe no projeto
# ...no fim de fetch_listings, antes do return:
if fails and not all_listings and fails / max(1, len(registry)) >= 0.6:
    raise SourceBlockedError(f"Amazon BR bloqueou: 503 em {fails}/{len(registry)} buscas")
```
(`lib/errors.py` já define `SourceBlockedError` — usado por liga/olx.)

### 3. Reduzir pressão de request — **prioridade média**
- Aumentar `delay_seconds` (1.5 → 2.5–3.0) e/ou adicionar **jitter** no `time.sleep(delay)` (linha 124) pra não bater em cadência fixa.
- Opcional: rotacionar `User-Agent` (hoje fixo, linha 28).
- Opcional: cortar `results_per_sku` de 6 → 3 (selado relevante costuma vir no topo).

### 4. Teste de regressão — **prioridade média**
Não há `tests/test_amazon*.py`. Adicionar ao menos:
- `parse_search_results` contra um HTML-fixture salvo (selectors não regridem).
- `_fetch_retry` com mock que devolve 503 nas 2 primeiras e 200 na 3ª.
- `_price_to_float('R$ 1.412,58') == 1412.58`.
Rodar a suíte: `python -m pytest -q` (hoje **32/32** passando — não pode regredir).

---

## Como reproduzir o 503 (pra validar o fix)

```bash
cd ~/sealed-arbitrage-scanner
python -c "import amazon_adapter as a, urllib.parse, time
url=a.BASE+urllib.parse.quote_plus('Destined Rivals ingles')
for i in range(6):
    try:
        h=a._fetch(url); print(i,'OK',len(a.parse_search_results(h)))
    except Exception as e: print(i,type(e).__name__,e)
    time.sleep(2)"
```
Espere ver uma mistura de `OK 13` e `HTTPError 503`. Depois do fix #1, um
`_fetch_retry` deve transformar a maioria dos 503 em `OK` na 2ª/3ª tentativa.

## Validação end-to-end (depois dos fixes)

```bash
cd ~/sealed-arbitrage-scanner
python build_us_reference.py                 # refresca preços US (tcgcsv)
python run_all_sources.py --sources amazon   # só Amazon
```
**Critério de aceite:**
- Se a Amazon estiver respondendo: banner mostra `amazon OK anúncios>0` com GREEN/YELLOW/RED.
- Se a Amazon estiver mesmo down: banner mostra `amazon BLOQUEADA` (não `OK ... anúncios=0`).
- `python -m pytest -q` → 32 + novos testes, todos verdes.

## Entrega
- Branch: `fix/amazon-503-retry-and-block-signal`
- PR contra `main`. Não commitar `results/` nem XLSX de TEMP.
- Atualizar este projeto **não** exige tocar README (fonte única) — é correção de robustez de adapter, não mudança de invariante. Se mudar `config.yaml` (delay/results_per_sku), mencionar no corpo do PR.

---

## Armadilhas conhecidas (não repetir)

- **`--threshold`/margens:** convenção do projeto é **fração** em alguns scanners
  irmãos — aqui a classificação é só **margem bruta**, não mexer nisso de passagem.
- **Não fabricar dado:** se a Amazon bloquear, reportar `BLOQUEADA` honesto. O
  objetivo do fix #2 é exatamente **parar de mascarar** bloqueio como "0 anúncios".
- **PowerShell vs Bash:** ambiente é Windows. Em PS use `$null`, não `/dev/null`.
- **stdout buffer:** `python ... | tee` bufferiza; pra ver progresso ao vivo use
  `python -u` ou rode sem pipe.
