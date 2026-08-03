# SETUP-VALIDACAO.md — validações que só você (Matheus) consegue fazer

Este guia lista os passos da **plataforma de arbitragem de selados** que
precisam do SEU PC (IP residencial + janela do Chrome) ou das SUAS chaves.
Tudo o que dava pra validar da nuvem já foi validado e está nos testes; o que
está aqui é o resto — cada seção é independente e diz o que destrava.

> Vocabulário: **referência de venda** = o preço do mercado onde você VENDE
> (eBay US, via Probstein). É **pedida** (anúncio ativo), não venda realizada,
> e **nunca muda a classificação** GREEN/YELLOW/RED (que segue o TCGplayer).

---

## §A — Chaves do eBay (uma vez, ~5 min, grátis) → liga as colunas de VENDA

O que destrava: colunas `Ref. eBay (R$)` / `Margem vs eBay %` + o 3º link
`[eBay]` na tabela de entrega, para Pokémon E One Piece.

1. Entre em https://developer.ebay.com (pode usar sua conta eBay normal).
2. Em **Application Keys**, crie um keyset de **PRODUCTION**.
3. No arquivo `.env` na raiz deste repo (crie se não existir), adicione:

   ```
   EBAY_CLIENT_ID=<App ID (Client ID)>
   EBAY_CLIENT_SECRET=<Cert ID (Client Secret)>
   ```

   ⚠️ Cole SEM espaços/quebras extras (o código sanitiza BOM/zero-width, mas
   não custa colar limpo — erro recorrente nº 1 da frota).
4. Gere a referência de venda (1 chamada por SKU; 205 ≪ 5.000/dia grátis):

   ```
   python build_ebay_reference.py
   ```

   Confira a linha final (`X ok · Y sem anúncio · Z só lixo · W erro`). Sem as
   chaves o comando avisa e NÃO toca no arquivo anterior — nunca zera nada.
5. Rode um scan normal — as colunas eBay aparecem sozinhas. A referência vale
   7 dias (depois só AVISA que está velha; nada é rebaixado por causa dela).

---

## §B — Liga One Piece (no seu PC, Chrome VISÍVEL) → liga o scan OP de verdade

O que destrava: `python run_liga_local.py --game onepiece` coletando de
verdade. Hoje o scan OP **falha de propósito** com uma instrução, porque os
IDs de categoria do site OP ainda não foram validados (o Cloudflare barra a
nuvem; e os IDs `categ=N` são POR SITE — os do site Pokémon NÃO valem).

1. Abra https://www.ligaonepiece.com.br no seu Chrome normal e navegue até as
   categorias de PRODUTOS SELADOS (caixas de booster, decks etc. — o
   equivalente do que fazemos no site Pokémon).
2. Em cada categoria, copie a URL — o número depois de `categ%3D` (ou
   `categ=`) é o ID. Anote o par ID → nome (ex.: `12 → Caixas de Booster`).
3. Rode uma sonda num produto selado qualquer (o probe é agnóstico de site):

   ```
   python probe_liga_sealed.py "<URL de um produto selado OP>" --headful
   ```

   Me mande a saída no chat (título cru, se o preço decodificou, idiomas).
4. Preencha em `config_onepiece.yaml`: `liga.categorias` (a lista de IDs) e
   `liga.categorias_nomes` (o mapa ID → nome). Se o passo 3 mostrar nomes PT
   de tipo diferentes de "Caixa de Booster"/"Booster Avulso", me avise para
   ajustarmos `type_translate`.
5. Smoke curto com janela visível:

   ```
   python run_liga_local.py --game onepiece --max-por-categoria 3
   ```

   - Se os preços saírem como `?`/pulados: os templates de dígito do site OP
     diferem dos do site Pokémon — me avise, capturamos novos templates (o
     coletor NUNCA inventa preço; ele pula o anúncio).
6. **Cole no chat os títulos reais coletados.** Só então os aliases PT entram
   no `sku_registry_onepiece.yaml` (regra da frota: nunca deduzir termo de
   set — os aliases nascem de título real, não de chute).

---

## §C — Referência de venda One Piece (depois do §A)

```
python build_ebay_reference.py --game onepiece
```

Mesma mecânica do §A, com o registry/arquivos do perfil OP.

---

## §D — Painel local (opcional, leitura)

```
python -m uvicorn panel:app --host 127.0.0.1 --port 8078
```

Abra http://127.0.0.1:8078 — deals do último scan de cada jogo, com filtros e
os 3 links por produto. É SÓ leitura (não dispara scan; a entrega oficial
continua sendo a tabela do `scripts/snapshot.py` colada no chat).

---

## Estado desta validação (atualize ao concluir)

| Passo | Estado |
|---|---|
| §A chaves eBay + referência Pokémon | ⏳ pendente |
| §B Liga One Piece (categorias/sonda/títulos reais) | ⏳ pendente |
| §C referência eBay One Piece | ⏳ pendente (depende de §A) |
| §D painel local | pronto para usar após qualquer scan |
