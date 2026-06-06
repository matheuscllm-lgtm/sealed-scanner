# 👉 COMECE AQUI

> **Porta de entrada do contexto deste projeto.**
> Se o operador pediu pra "abrir o contexto", "retomar" ou "começar daqui",
> você está no arquivo certo. Faça os passos abaixo ANTES de qualquer coisa.

## Que projeto é este
**Scanner de Produtos Selados de Pokémon** — acha selados (booster box, ETB,
bundle, lata/tin, pack) mais baratos no Brasil do que valem nos EUA, pra revenda.

## Pra retomar — faça nesta ordem
1. Leia **`SESSION-HANDOFF.md`** → estado atual completo + todas as decisões.
2. Leia **`GOALS.md`** → lista de pendências priorizadas.
3. Confirme a versão do nosso trabalho:
   ```
   git pull origin claude/determined-curie-Q1Ur8
   ```
   (proposta aberta: PR #7)

## Regras que NÃO mudam (resumo; detalhes no handoff)
- Só importa a **DIFERENÇA BRUTA DE PREÇO** (margem total = (US − BR)/BR).
  Nada de "lucro líquido"/ROI, nada de frete inventado — foi tudo removido.
- O programa **só monta a lista; NUNCA compra**. Toda compra é decisão do
  operador, conferida na mão.
- A busca da **Liga roda no PC do operador** (Chrome real, internet de casa) —
  a nuvem não consegue (a Liga bloqueia servidores).
- **Fale com o operador em PORTUGUÊS SIMPLES** e explique os termos técnicos —
  ele não é programador.

---
_Convenção: este arquivo se chama sempre `COMECE-AQUI.md` e fica na raiz de cada
projeto. Pra retomar qualquer projeto, o operador só precisa dizer: "leia o
COMECE-AQUI"._
