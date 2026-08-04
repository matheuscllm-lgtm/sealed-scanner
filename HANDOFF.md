# HANDOFF — Plataforma de arbitragem de selados (rotas + venda eBay + One Piece + painel)

> **Data:** 2026-08-03 · **Branch:** `claude/pokemon-tcg-arbitrage-platform-0t3ut0` ·
> **PR:** [#75 (draft)](https://github.com/matheuscllm-lgtm/sealed-scanner/pull/75) ·
> Handoff da sessão de nuvem que construiu e validou a plataforma v1. Leia junto
> com o `CLAUDE.md` (doc canônica, já atualizada) e o `SETUP-VALIDACAO.md` (runbook §A–§D).

## 🎯 ~~PRÓXIMA TAREFA~~ ✅ RESOLVIDA 2026-08-04 (sessão do terminal no PC)

**Causa raiz (2 camadas, ambas corrigidas e travadas em teste):**

1. **Espaço cru no `prod=`** do href (site OP) → fix `b2d6b06`
   (percent-encode na coleta `_sanitize_product_url` + defesa em `md_link`).
2. **Parênteses crus** (`(ING)`, `(Kit Pré-Lançamento)`) na URL dentro de
   `[oferta](url)`: o `)` cru fecha o link markdown no primeiro parêntese e o
   renderizador do chat truncava a URL ("não levava em lugar nenhum") → fix
   `0765881` (`md_link` encoda `( )` → `%28/%29`; teste
   `test_md_link_encodes_parentheses`). Confirmado pelo operador: era o mesmo
   sintoma nos selados Pokémon.

**Verificação fim-a-fim 2026-08-04 (navegador do PC, logado):** URL encodada
abre a página do produto nos DOIS sites — Pokémon (`pcode=133774`, Booster
Fogo Branco, e `pcode=133198`, Box Zacian, com "Lojas Vendendo") e One Piece
(`pcode=136936`, Deck ST-32 Roronoa Zoro). NÃO era a classe do fix #39 do
liga-cards (roteamento `edid` é só na listagem de singles; `?view=prod/view&
pcode=` segue válido). Suíte: **442 passed**. CSVs antigos não precisam de
re-scan: o `md_link` do snapshot encoda retroativamente na entrega.

## 🎯 Texto original da tarefa (histórico — aberta pelo operador 2026-08-03)

**Sintoma:** links `[oferta]` da entrega não abrem a página do produto na Liga
("gerava links da oferta que não levava em lugar nenhum", relato do operador).
O fix `b2d6b06` já cobriu UM caso (espaço cru no href do site OP →
percent-encode na coleta e na entrega), mas o relato do operador sugere que há
mais coisa além do encoding.

⚠️ **A frase do operador chegou CORTADA no chat:** *"os links de oferta podemos
pegar da liga pokemon como …"* — ele ia indicar o formato certo. **1º passo da
sessão: pedir ao operador um exemplo de link FUNCIONAL** (com a página do
produto aberta no navegador, copiar a URL da barra de endereço) para comparar
com o que está no CSV.

**Roteiro sugerido (PC, com o site alcançável):**

1. **Reproduzir:** abrir o CSV do último scan real
   (`results/onepiece/unified_*/unified_deals.csv` e um run Pokémon), clicar
   3–5 URLs da coluna `URL` de cada jogo e anotar o que acontece (abre a
   página? cai na home? 404?).
2. **Comparar** com o link funcional fornecido pelo operador e identificar o
   delta (parâmetro faltando? roteamento novo? encoding?). Precedente da
   frota: **fix #39 do `liga-cards-scanner`** — a Liga mudou o roteamento das
   listagens de singles (2026-06) e a URL antiga passou a cair na home; pode
   ser a mesma classe aqui no `?view=prod/view&pcode=`.
3. **Corrigir na camada certa:** a coleta já captura o href REAL da página de
   categoria (`parse_category_products` → `_sanitize_product_url`,
   `liga_adapter.py:~580-592`) — se faltar parâmetro, **extraí-lo da própria
   página** (nunca montar URL na mão / nunca inventar); se for só encoding, a
   defesa retroativa mora em `scripts/snapshot.py::md_link`. CSV antigo com
   URL irreparável = dizer honesto que re-scan resolve (não "consertar"
   fabricando link).
4. **Travar em teste** com href real capturado como fixture — Pokémon e OP em
   casos separados (o bug pode ser de um site só).
5. **Verificar fim-a-fim:** scan curto (`run_liga_local.py
   --max-por-categoria 3` e/ou `--game onepiece`) → clicar os links do
   snapshot novo → commit + push na MESMA branch (PR #75 segue draft; a
   correção entra nele).

Nota: o painel (`panel.py`) serve as MESMAS URLs do CSV — consertar a coleta
conserta entrega e painel de uma vez.

## Estado atual (resumo de 30 segundos)

A plataforma v1 está **pronta e validada**: o sealed-scanner agora declara a
**ROTA** (onde comprar → para onde vender), mostra a **referência do lado de
VENDA** (menor anúncio ativo no eBay US, onde se vende via Probstein) ao lado da
referência TCGplayer, tem **perfil One Piece** (`--game onepiece`) e um **painel
web local** read-only. Tudo em 1 PR draft com **438 testes offline verdes**. A
validação §A (chaves eBay) foi feita **ao vivo com a API de produção** nesta
sessão — funcionou e ainda rendeu 2 endurecimentos de guard (ver abaixo).

- Últimos commits: `4903216` (gate barra code cards digitais) e `2b87221`
  (piso de busca = 50% da ref TCG) — **conferir o CI do PR** ao retomar
  (estava rodando no fechamento deste handoff; a base b757187 estava verde).
- Classificação GREEN/YELLOW/RED **não mudou em nada**: continua 100% TCGplayer;
  o lado eBay é informativo (regras invioláveis nº 7 e 8 do CLAUDE.md).

## Decisões tomadas (com o operador, 2026-08-03)

1. **Nicho novo nº 1 = One Piece TCG** (Dragon Ball/Lorcana ficam no backlog).
2. **Referência de venda = eBay ativos** (Browse API; PriceCharting/vendas
   realizadas fica no backlog). Rótulo duro: **pedida, não venda realizada**.
3. **Entrega = rotas em config + tabela enriquecida + painel local FastAPI**
   (integração ao integrated-scanner fica no backlog).
4. Arquitetura (D1–D7 no corpo do PR): perfil por jogo via DADOS (zero
   condicional de jogo no matcher/margem/classificação); referência eBay é
   pré-passo separado que degrada honesto sem chaves e nunca sobrescreve a
   anterior; `data/ebay_reference*.json` é gitignored; painel é read-only.

## Validação ao vivo já feita (§A — números reais, Browse API produção)

| Jogo | SKUs ok | Sem anúncio plausível | Lixo vencedor | Erros |
|---|---:|---:|---:|---:|
| Pokémon (205 SKUs) | **182** | 23 | 0 | 0 |
| One Piece (83 SKUs) | **55** | 28 | 0 | 0 |

- Duas lições do probe viraram código no mesmo dia: **code cards digitais**
  (US$0,99 citando set+tipo) → `DIGITAL_TOKENS` no gate; **janela de busca
  saturada de lixo barato** em SKU popular → piso de busca = 50% da ref TCG.
- Smoke fim-a-fim (mock + snapshot): 10/10 SKUs com referência de venda, 3
  links por linha, e o insight que justifica a plataforma — ex. real: Surging
  Sparks Booster Box **+78,9% vs TCG** mas só **+4,4% vs a menor pedida no
  eBay**; Stellar Crown Box +42,5% vs TCG e **−5,9%** vs eBay.
- ⚠️ Os arquivos `data/ebay_reference*.json` gerados aqui eram do container
  efêmero da nuvem — **regenere onde for rodar** (1 comando, ~4 min; as env
  vars `EBAY_CLIENT_ID`/`EBAY_CLIENT_SECRET` **já existem no PC do operador**
  como User env vars desde 2026-06-10). Se quiser, rotacionar o Cert ID no
  developer.ebay.com é opcional (foi colado no chat da sessão) — depois é só
  atualizar a env var.

## Arquivos tocados (11 commits no PR #75)

- **Novos:** `lib/ebay_client.py` · `build_ebay_reference.py` · `panel.py` ·
  `sku_registry_onepiece.yaml` (83 SKUs, 100% dados reais tcgcsv cat 68) ·
  `config_onepiece.yaml` · `data/us_reference_onepiece.json` ·
  `scripts/gen_onepiece_registry.py` · `SETUP-VALIDACAO.md` ·
  `mock_data/onepiece_listings.json` · testes novos (eBay client/builder/
  enrichment, registry OP, perfis, painel).
- **Modificados:** `sealed_arbitrage_scanner.py` (5 campos eBay no ScanRow,
  CSV 22→27 colunas, `apply_ebay_reference`, `GAME_PROFILES`; `compute_margin`
  e `match_listing` **intocados**) · `run_all_sources.py` (+`run_meta.json`,
  `--game`) · `run_liga_local.py` · `liga_adapter.py` (parametrizado por
  perfil; defaults Pokémon byte-idênticos) · `build_us_reference.py`
  (`--game/--category-id/--bands`) · `scripts/snapshot.py` (3º link `[eBay]`,
  colunas de venda, cabeçalho de rota, `--game`) · `config.yaml` (bloco
  `route:`) · `requirements.txt` (fastapi/uvicorn) · `.gitignore` ·
  `CLAUDE.md` · `CHANGELOG.md` · skill `sealed-scan`.

## Pendências (em ordem)

1. ~~CI do PR #75~~ ✅ verde (pytest pass nos 3 commits, conferido 2026-08-03
   na sessão do PC; suíte local também: 438/438).
2. ~~§B — validar a Liga One Piece no PC do operador~~ ✅ FEITO 2026-08-03 na
   sessão do PC: categorias `10/21/28/36` validadas no site real (38 Kits e
   24 Latas fora — sem SKU no registry), `type_translate` ganhou
   `"Deck Inicial" → "Starter Deck"`, smoke headful ok (preços decodificaram
   com os templates existentes) e **primeiro scan OP real completo**: 504
   anúncios → 38 produtos (15 GREEN), com lado de venda eBay (329/340). §A
   regenerado no PC (182/205) e §C feito (55/83). Tabela de estado atualizada
   no `SETUP-VALIDACAO.md`.
3. ~~🎯 Links de oferta da Liga não abrem~~ ✅ RESOLVIDO 2026-08-04
   (fixes `b2d6b06` + `0765881`; verificação fim-a-fim nos 2 sites — ver
   seção 🎯 do topo).
4. **Revisar e mergear o PR #75** (decisão do operador; está draft).
5. Backlog registrado no CLAUDE.md (PriceCharting, score de longo prazo por
   productId, 5ª fonte do integrado, categoria eBay via Taxonomy API, OP em
   OLX/ML/Amazon, perfis DBZ/Lorcana, POST /scan no painel). Novo item vindo
   do 1º scan OP real: avaliar SKUs para "Kit Colecionável"/"Illustration
   Box"/"Gift Collection" (aparecem na categ 28/38 e hoje ficam sem match de
   propósito — só entram com product_id real no tcgcsv).

## Próximos passos sugeridos para a PRÓXIMA sessão

1. **A tarefa 🎯 do topo** (links de oferta da Liga) — começa pedindo ao
   operador o exemplo de link funcional.
2. Depois dela: operador revisa/mergeia o PR #75 (draft).
3. Primeiro scan Pokémon completo com o lado de venda: refresh das 2
   referências + `run_liga_local.py` + snapshot (comandos abaixo).

## Comandos para continuar (nova sessão)

```bash
# ── Em qualquer ambiente: pegar o trabalho ──────────────────────────────
git fetch origin claude/pokemon-tcg-arbitrage-platform-0t3ut0
git checkout claude/pokemon-tcg-arbitrage-platform-0t3ut0
git pull origin claude/pokemon-tcg-arbitrage-platform-0t3ut0
pip install -r requirements.txt
python -m pytest -q                      # esperado: 438 passed, offline

# ── PC do operador (Windows; venv + env vars eBay JÁ configuradas) ──────
cd C:\Users\mathe\sealed-arbitrage-scanner
.venv\Scripts\python.exe build_us_reference.py            # refresh ref TCG (diário)
.venv\Scripts\python.exe build_ebay_reference.py          # refresh ref VENDA (~4 min)
.venv\Scripts\python.exe run_liga_local.py                # scan Liga (janela do Chrome)
#   → o snapshot sai sozinho no fim; entrega = colar o .md no chat

# One Piece (depois do §B validar as categorias do site):
.venv\Scripts\python.exe build_us_reference.py --game onepiece
.venv\Scripts\python.exe build_ebay_reference.py --game onepiece
.venv\Scripts\python.exe run_liga_local.py --game onepiece

# Painel local (somente leitura):
.venv\Scripts\python.exe -m uvicorn panel:app --host 127.0.0.1 --port 8078
#   → abrir http://127.0.0.1:8078

# ── Smoke sem rede/chaves (qualquer ambiente) ───────────────────────────
python run_all_sources.py --sources mock --mock mock_data/liga_listings.json
python scripts/snapshot.py
```

> Segredos: NUNCA commitar `.env` (gitignored). Na nuvem, as chaves eBay
> precisam ser postas no `.env` a cada container novo (`SETUP-VALIDACAO.md §A`);
> no PC elas já são User env vars.
