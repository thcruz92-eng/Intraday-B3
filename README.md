# Intraday · B3

Base de candles intradiários da B3 (5 e 60 min), pregão ao vivo e motor de
estratégias de day trade. Mesmo esquema do overnight: o app mora no Netlify,
os dados moram no GitHub e um robô do GitHub Actions coleta tudo sozinho.

**Novidades da v6** (29/09/2026)
- **Uma estratégia seletiva: Compra no leilão · nota.** Cada papel líquido ganha uma nota antes
  da abertura — o resultado esperado da operação, por um modelo que cruza 36 indicadores e é
  refeito a cada trimestre só com os pregões anteriores. A lista mostra os papéis com nota ≥ 0,30%
  e o **COMPRA ATÉ** de cada um (o preço máximo do leilão, 0,5% abaixo do índice); você compra
  **um por pregão**, o primeiro da lista que abrir até lá. Saída: **alvo +0,4 ATR** (~+1%),
  **stop −1 ATR** (~−2,6%), senão leilão de fechamento. Fora da amostra (jan/2024 → set/2026):
  **~3,4 operações por semana, 74% de acerto, +0,42% por operação**; com a exigência em 0,45%:
  ~1 por semana, 79%, +0,58%.
- **"por quê"** em cada papel da lista: os indicadores que mais puxaram a nota dele naquele dia.
- **CONFIGURAÇÕES → Exigência da nota** (0,25% a 0,50%, com o que a pesquisa mediu em cada nível)
  e **1 por pregão** como padrão (a configuração da v5 com 3 passa para 1).
- A **lista curta da v5** fica como referência no ESTRATÉGIAS; a venda continua em observação e
  desligada ("só compra").
- A saída no **leilão de fechamento** do motor passa a usar o fechamento oficial (COTAHIST) em
  vez do último candle do Yahoo.

**Da v5** (se você ainda está na v4): OPERAR pelo relógio do pregão, ACOMPANHAR e RESULTADOS
(suas operações na nuvem, ao lado do modelo), direção das sugestões, e o **COTAHIST diário na
base** (`dados/diario/`), de onde saem a nota e o COMPRA ATÉ.

## Como os dados chegam

| | Fonte | Quando | Profundidade |
|---|---|---|---|
| **Candles de 5 min** | Yahoo Finance | robô, 19h30 / 23h30 / 9h30, todo dia | carga inicial = 60 dias corridos (~43 pregões); daí em diante **acumula** um pregão por dia |
| **Candles de 60 min** | Yahoo Finance | carga inicial; depois = soma dos de 5 min | ~2 anos |
| **Séries de referência** (IBOV, USDBRL, SP500F, DXY) | Yahoo Finance | junto com as ações | as mesmas profundidades; só 9h–18h30 e só em pregão da B3 |
| **COTAHIST diário** (v5) | base do projeto overnight (arquivo oficial da B3) | robô, junto com os candles | desde 2023; abertura, máxima, mínima, fechamento e volume oficiais |
| **Pregão de hoje** | Yahoo Finance, pela função do Netlify | GRÁFICO: ao abrir, atualiza a cada minuto com o pregão aberto · OPERAR e ACOMPANHAR: só quando você aperta | atraso de 15 min do Yahoo |

A coleta **não gasta crédito do Netlify**: o robô grava na pasta `dados/` do
GitHub e o app lê de lá. O site só é republicado quando você sobe arquivo do
app (`public/`, `netlify/`, `package.json`), 15 créditos cada vez.

---

# Já está com a v4? Troque só isto

Conferi arquivo por arquivo contra o que está no seu repositório (29/09). **São 3 arquivos**
— GitHub → Add file → Upload files, arrastando **o conteúdo** da pasta `ARRASTAR-ESTE-CONTEUDO`
(a subpasta `public/` vai junto):

| Arquivo | Por que |
|---|---|
| `public/app.js` | o app novo: a Compra no leilão · nota, OPERAR pelo relógio, ACOMPANHAR, RESULTADOS |
| `coleta_intraday.py` | passa a gravar o COTAHIST diário em `dados/diario/` (é dele que sai a nota) |
| `README.md` | esta explicação |

Um commit só = **um** deploy no Netlify (15 créditos). Funções, workflow, `netlify.toml`,
`package.json` e `universo.txt` **não mudaram**. (Se já tinha subido a v5, são os mesmos 3
arquivos; o `coleta_intraday.py` é igual ao da v5.)

**Depois de subir, rode a coleta uma vez** (GitHub → Actions → Coleta intraday → Run workflow →
Run workflow). Leva poucos minutos e grava a pasta `dados/diario/`. Sem ela o app funciona, mas
avisa que a lista está saindo do fechamento do Yahoo (sem o leilão de fechamento). Daí em
diante a coleta das 9h30 traz o fechamento oficial de ontem antes da pré-abertura.

As configurações da v4/v5 continuam valendo (taxa, capital, piso, direção); o hedge e o
LABORATÓRIO da v4 são descartados. As operações que você marcar no ACOMPANHAR ficam na nuvem.

Está na v3 ou antes? Suba também `netlify/functions/dados.mjs`, `package.json` e `netlify.toml`.

Se ainda não subiu nada, siga do começo.

---

# PASSO 0 — Descompactar

Descompacte **`intraday-b3-v6.zip`**. Dentro da pasta tem:

```
.github/workflows/coleta-intraday.yml   ← agenda do robô (pasta oculta!)
netlify/functions/aovivo.mjs            ← pregão ao vivo + reserva da coleta
netlify/functions/dados.mjs             ← configurações e operações na nuvem (todos os aparelhos)
public/                                  ← o app (index.html, app.js, ícones)
package.json                             ← dependência da função de dados
coleta_intraday.py                       ← o robô de coleta
universo.txt                             ← exceções manuais do universo
netlify.toml                             ← como o Netlify publica
.gitignore
README.md
```

---

# PARTE 1 — GitHub

## 1.1 Criar o repositório

1. https://github.com → **+** → **New repository**
2. **Repository name**: `intraday-b3`
3. Marque **Public** — obrigatório: o app lê a base direto do GitHub, sem login.
   (É só cotação de mercado e o código do app, igual ao overnight.)
4. Não marque nada em "Initialize this repository" → **Create repository**.

## 1.2 Subir os arquivos

Na tela seguinte, clique em **uploading an existing file**, arraste **tudo que
está dentro da pasta** e clique em **Commit changes**.

> A pasta `.github` costuma não subir no arrastar (é oculta). Confira: se ela
> não aparecer na lista do repositório, faça o 1.3.

## 1.3 Criar o arquivo do robô à mão (só se a `.github` não subiu)

1. **Add file** → **Create new file**
2. Nome, exatamente: `.github/workflows/coleta-intraday.yml`
3. Cole o conteúdo do arquivo `coleta-intraday.yml` da pasta → **Commit changes**.

## 1.4 Liberar a escrita do robô

**Settings** → **Actions** → **General** → **Workflow permissions** →
**Read and write permissions** → **Save**.
Sem isso o robô coleta e falha na hora de salvar.

---

# PARTE 2 — Netlify

## 2.1 Publicar o site

1. https://app.netlify.com → **Add new project** → **Import an existing project**
   → **GitHub** → escolha **`intraday-b3`**.
2. As configurações vêm do `netlify.toml`; é só clicar em **Deploy**.
3. Se aparecer aviso de projeto privado (ou pedir login para abrir o site),
   clique em **Make public** (ou **Project configuration → General → Visitor
   access → Project visibility → Public**). Precisa ser público para o tablet
   abrir sem login e para o robô conseguir usar a reserva do passo 2.2.

## 2.2 Ligar a reserva da coleta (recomendado)

O Yahoo às vezes recusa consultas vindas dos servidores do GitHub. Quando isso
acontece, o robô passa a consultar pela função do próprio site no Netlify.

No GitHub: **Settings** → **Secrets and variables** → **Actions** → aba
**Variables** → **New repository variable**:

- Name: `URL_APP`
- Value: o endereço do site, ex. `https://intraday-b3.netlify.app` (sem barra no fim)

## 2.3 Testar a função ao vivo

Abra no navegador (trocando pelo seu endereço):

```
https://SEU-SITE.netlify.app/.netlify/functions/aovivo?t=PETR4,USDBRL
```

Deve voltar um JSON com `"dados":{"PETR4":{"dias":{...}},"USDBRL":{...}}`. Fora do
horário do pregão ele traz o último pregão.

---

# PARTE 3 — Carga inicial da base

1. GitHub → aba **Actions** → **Coleta intraday** → **Run workflow** → deixe os
   campos em branco → **Run workflow**.
2. Leva uns 5 a 10 minutos (~350 consultas: 60 dias de 5 min e 2 anos de
   60 min para ~175 séries). Bolinha amarela vira verde.
3. Abra o app: aba **BASE** mostra o período coletado e a
   **conferência com o COTAHIST** — o fechamento de cada papel-dia comparado com
   o arquivo oficial da B3. É o teste com dado real, e ele roda em toda coleta.

Daí em diante não precisa fazer nada. Se a base atrasar além das 9h15 do dia
seguinte ao pregão, a execução fica **vermelha** e o GitHub manda e-mail.

---

# PARTE 4 — Tablet

Abra o endereço no Chrome → menu ⋮ → **Adicionar à tela inicial**.

---

# Como usar

O dia, na ordem em que o app mostra:

| Quando | O que fazer | Onde |
|---|---|---|
| antes das 9h45 | Abra o OPERAR e ponha os papéis da lista numa lista do Profit, com a variação teórica do leilão. Lista vazia = hoje não tem entrada | OPERAR |
| 9h45 → 9h55 | Digite a variação do WIN (ou o Ibovespa teórico). O app refaz o COMPRA ATÉ, a nota e a ordem da lista | OPERAR |
| 9h55 → 9h59 | Desça a lista de cima para baixo: o primeiro papel com o preço teórico **até o COMPRA ATÉ** é o do dia. Compra limitada no leilão **ao COMPRA ATÉ**, na quantidade da tabela. Só um. Pule papel caindo 8% ou mais além do índice (notícia) | corretora |
| 10h | Executou: venda limitada no alvo e venda stop no stop (OCO, se houver). Não executou: cancele | corretora |
| depois das 10h15 | "buscar a abertura de hoje": o que entrou, alvo, stop, último preço. Marque a entrada | OPERAR · ACOMPANHAR |
| call de fechamento | Venda no leilão o que ainda estiver aberto (16h55–17h no verão dos EUA; 17h55–18h no resto do ano) | corretora |
| depois | Marque a saída. À noite o pregão entra na base e o modelo aparece ao lado | ACOMPANHAR · RESULTADOS |

Na dúvida sobre o índice, digite o valor **mais negativo**: errar para baixo só tira operações;
errar para cima põe papéis demais na lista.

**ESTRATÉGIAS**: a nota e a lista curta da v5 lado a lado num período (2 anos em candles de
60 min, ou desde julho em candles de 5 min) — curva, estatísticas, contribuição de cada papel,
planilha.

**CONFIGURAÇÕES**: direção (só compra / só venda / as duas), exigência da nota, máximo por
pregão, taxas, capital, piso, estratégias visíveis. **voltar os números ao padrão** não mexe no
piso nem na direção.

**READ ME**: tudo isto, com a ficha de cada estratégia, os 36 indicadores da nota e o que foi
testado e não passou.

## Estratégias

Pesquisa de 29/09/2026 com o COTAHIST (2023–2026) e os candles de 60 min (out/2023–set/2026),
R$ 10 mil por operação, taxa 0,046%, sem hedge. A nota foi validada em walk-forward: cada pregão
de jan/2024 a set/2026 decidido só com o modelo treinado nos pregões anteriores.

| Estratégia | Regra | Situação | Fora da amostra (60 min) |
|---|---|---|---|
| Compra no leilão · nota | lista = nota no COMPRA ATÉ ≥ 0,30%; entra o 1º que abrir até o COMPRA ATÉ (0,5% ou mais abaixo do índice); 1 por pregão; alvo +0,4 ATR, stop −1 ATR, senão fechamento | validada | ~3,4 por semana, 74% de acerto, +0,42%/op (2024 +0,38%, 2025 +0,47%, 2026 +0,39%) |
| Compra no leilão · lista curta (v5) | lista dos 15 de maior nota da v5; compra quem abrir ≤ −0,5% contra o índice, até 3; alvo +2%, stop −3% | referência (só no ESTRATÉGIAS) | ~8 por semana, 61%, +0,29% a +0,34%/op |
| Venda no leilão · lista curta | o espelho da v5 (vende quem abrir ≥ +0,5%), stop +3% | em observação (desligada: “só compra”) | +0,16% (t 1,7) |

Regras de poucas condições escolhidas no passado, filtros de mercado, alvos curtos, entradas no
meio do pregão e o WIN sozinho foram testados e não passaram — os números estão no READ ME.

---

# Ajustes

- **Universo** (quais papéis entram): monta sozinho a cada coleta a partir do
  COTAHIST do overnight — média de volume financeiro dos últimos 20 pregões,
  descartando os 10% maiores, acima de **R$ 5 MM** (~170 papéis), mais as 4
  séries de referência. Exceções no `universo.txt` (`+TICKER` inclui, `-TICKER`
  exclui). Papel que entra já ganha os 60 dias de 5 min e os 2 anos de 60 min
  que o Yahoo tiver.
- **Mudar o corte de R$ 5 MM**: em **Run workflow**, campo *vol_min*; para fixar,
  edite `coleta-intraday.yml` e acrescente `--vol-min 10` na linha
  `python coleta_intraday.py $ARGS`.
- **Rebaixar um papel** (ex. dado estranho): **Run workflow** com *ativos* =
  `PETR4` e *completo* marcado.
- **Repositório com outro nome**: no app, **CONFIGURAÇÕES → Neste aparelho**.

---

# Pontos de atenção

- **60 dias do Yahoo são corridos**, não pregões: a base de 5 min começa com ~43
  pregões. Para datas anteriores, o gráfico usa 60 min ou diário (2 anos).
- **Ao vivo = 15 min de atraso** (é o que o Yahoo entrega para a B3).
- **Volume** do Yahoo é quantidade de papéis; o financeiro é estimado candle a
  candle (quantidade × preço típico). A conferência mostra a razão contra a B3.
- **Dólar em pontos do WDO**: `USDBRL` é guardado como R$ por US$ 1.000
  (5,2345 → 5.234,50), a cotação do mini dólar. É o dólar à vista: o WDO tem o
  diferencial de juros por cima, mas o movimento dentro do dia é o mesmo.
- **Pregão guardado não é reajustado depois**: se houver desdobramento ou
  grupamento, o dia do evento aparece como salto de preço (igual ao COTAHIST) e
  fica fora do índice do dia nas estratégias (salto acima de 25%).
- **A API do Yahoo não é oficial.** Se a coleta parar, olhe o log em Actions;
  a reserva pelo Netlify (URL_APP) cobre bloqueio de IP do GitHub.
- **Tamanho**: ~5 MB por mês de 5 min para ~175 séries (~60 MB/ano), em
  arquivos mensais — longe do limite de 100 MB por arquivo do GitHub. O app
  baixa cada mês uma vez e guarda no aparelho.

---

# O que é cada arquivo

| Arquivo | Para que serve |
|---|---|
| `public/app.js` | o app compilado (fonte vai separada) |
| `public/index.html`, ícones, `manifest.webmanifest` | página e instalação no tablet |
| `netlify/functions/aovivo.mjs` | pregão ao vivo + reserva da coleta |
| `netlify/functions/dados.mjs` | CONFIGURAÇÕES e as operações do ACOMPANHAR, na nuvem do Netlify (Blobs) |
| `package.json` | dependência da função de dados (o Netlify instala no deploy) |
| `coleta_intraday.py` | coleta, grava `dados/` (candles e, na v5, o COTAHIST diário em `dados/diario/`), confere com o COTAHIST, audita (`--verificar`) |
| `.github/workflows/coleta-intraday.yml` | agenda o robô |
| `universo.txt` | exceções do universo |
| `dados/` | a base (criada pelo robô — não mexa à mão) |
| `netlify.toml` | publica `public/` e as funções, e só republica quando o app muda (`public/`, `netlify/`, `package.json`) |
