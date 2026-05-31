# Setup no Windows 11 — Liga Pokémon scanner (modo local, sem custo)

Este guia leva você do zero até rodar o scanner da Liga no SEU PC, sem
gastar credits de proxy. O scanner usa o Google Chrome instalado pra
passar o Cloudflare da Liga (IP residencial seu funciona).

Tempo estimado: **15-20 minutos** no primeiro setup. Depois é só
**1 comando** quando quiser um snapshot.

---

## 1. O que você precisa antes

- **Windows 10 ou 11** ✓ (você já tem)
- **Google Chrome** ✓ (você já tem)
- Conexão de internet doméstica

---

## 2. Instalar o Python

O Windows não vem com Python por padrão. Tem 2 formas — escolha a mais fácil pra você.

### Opção A — Microsoft Store (mais simples)

1. Abra o menu Iniciar e digite "Microsoft Store"
2. Procure por "Python 3.12" (ou 3.11)
3. Clique em **Obter** / **Instalar**
4. Depois de instalado, abra o **PowerShell** e teste:

   ```powershell
   python --version
   ```

   Deve mostrar algo como `Python 3.12.x`.

### Opção B — python.org (alternativa)

1. Baixe em https://www.python.org/downloads/windows/
2. Execute o instalador
3. **MARQUE** a opção "Add Python to PATH" antes de clicar em Install
4. Conclua a instalação
5. Abra PowerShell e teste `python --version`

---

## 3. Instalar o Git (opcional mas recomendado)

Se você quiser baixar atualizações fáceis depois:

1. Baixe em https://git-scm.com/download/win
2. Instale com as opções padrão
3. Teste no PowerShell: `git --version`

**Se você não quer Git**, pode baixar o ZIP do repositório direto pelo
GitHub (botão verde "Code" → "Download ZIP") e descompactar.

---

## 4. Baixar o scanner

No PowerShell, navegue até onde quer guardar o projeto (ex: pasta Documentos):

```powershell
cd $HOME\Documents
```

Depois clone o repositório (na branch certa):

```powershell
git clone -b claude/tcg-sealed-arbitrage-agent-eNXVg `
  https://github.com/matheuscllm-lgtm/tcg-arbitrage-scanners.git
cd tcg-arbitrage-scanners
```

(Se baixou ZIP, descompacte e use `cd` pra entrar na pasta descompactada.)

---

## 5. Instalar as dependências Python

No PowerShell, dentro da pasta do projeto:

```powershell
python -m pip install --upgrade pip
python -m pip install -r sealed\requirements.txt
python -m pip install patchright
```

A última linha (patchright) é o que controla o Chrome.

---

## 6. Testar que tudo funciona

Antes de rodar o scan completo, faça um teste leve:

```powershell
python sealed\run_liga_local.py --categorias 27 --max-por-categoria 2
```

O que vai acontecer:
1. Verificação de dependências (deve passar tudo OK)
2. Chrome abre em modo invisível e visita a Liga
3. Cloudflare é resolvido pelo seu IP residencial
4. Scanner lista a categoria 27 (ETB), pega 2 produtos, decodifica preços
5. Imprime ranking de oportunidades GREEN/YELLOW/RED

Se aparecer algo como `1 GREEN, 15 YELLOW` no final, **funcionou!** 🎉

---

## 7. Uso no dia a dia

### Scan completo (todas as categorias)

```powershell
python sealed\run_liga_local.py
```

Dura ~5-10 minutos dependendo da conexão. Salva resultados em
`sealed\results\<data_hora>\`.

### Scan rápido (só Booster Box + ETB)

```powershell
python sealed\run_liga_local.py --categorias 10,27
```

### Ver o Chrome em ação (modo janela)

Útil pra debugar se algo parecer errado:

```powershell
python sealed\run_liga_local.py --janela --categorias 27 --max-por-categoria 1
```

### Snapshot Markdown pro Obsidian

```powershell
python sealed\run_liga_local.py --snapshot
```

Gera um arquivo `.md` em `sealed\snapshots\` com o ranking unificado.

---

## 8. Manutenção / atualizações

Quando eu atualizar o código no GitHub, você pega assim:

```powershell
cd $HOME\Documents\tcg-arbitrage-scanners
git pull origin claude/tcg-sealed-arbitrage-agent-eNXVg
```

---

## 9. Problemas comuns

**`patchright` não encontrado** → rode `pip install patchright` de novo.

**Chrome não abre / erro de "executable"** → o patchright procura o Chrome
no caminho padrão. Se você instalou em local diferente, me avise pra
ajustar.

**Cloudflare bloqueia mesmo do seu IP** (raro) → tente sem VPN; se você
estiver usando uma VPN, desligue-a antes de rodar o scanner.

**Erro `ModuleNotFoundError`** → rode novamente `pip install -r
sealed\requirements.txt` no PowerShell, dentro da pasta do projeto.

**Quer voltar a usar o modo cloud (ScraperAPI)** → edite
`sealed/config.yaml` e mude `mode: local` para `mode: scraperapi`.
