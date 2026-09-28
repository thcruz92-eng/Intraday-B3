# Intraday · B3

Base de candles intradiários da B3 (5 e 60 min), pregão ao vivo e motor de
estratégias de day trade. Mesmo esquema do overnight: o app mora no Netlify,
os dados moram no GitHub e um robô do GitHub Actions coleta tudo sozinho.

**Novidades da v3** (28/09/2026)
- **Campo "Saída"** nas estratégias: fim do pregão (padrão) ou zerar às 10h10, 10h15, 10h30,
  11h ou 12h. Medido na base real: o ganho da reversão do gap está nos **10 primeiros minutos**
  (veja "Estratégias" abaixo).

**Novidades da v2**
- **Séries de referência** para estudar WIN e WDO: Ibovespa (`IBOV`), dólar à
  vista em pontos do WDO (`USDBRL`), S&P 500 futuro (`SP500F`) e índice do dólar
  (`DXY`). Entram sempre na coleta, só no horário dos minicontratos (9h às
  18h30) e só em dia de pregão da B3. Já na primeira coleta vêm **2 anos em
  60 min**.
- **Aba ESTRATÉGIAS funcionando**: as estratégias da pesquisa de 27/09/2026
  (reversão do gap relativo ao índice) rodam sobre a base de 5 min, com
  parâmetros editáveis, período por dia, hedge no WIN, curva e lista de
  operações.

## Como os dados chegam

| | Fonte | Quando | Profundidade |
|---|---|---|---|
| **Candles de 5 min** | Yahoo Finance | robô, 19h30 / 23h30 / 9h30, todo dia | carga inicial = 60 dias corridos (~43 pregões); daí em diante **acumula** um pregão por dia |
| **Candles de 60 min** | Yahoo Finance | carga inicial; depois = soma dos de 5 min | ~2 anos |
| **Séries de referência** (IBOV, USDBRL, SP500F, DXY) | Yahoo Finance | junto com as ações | as mesmas profundidades; só 9h–18h30 e só em pregão da B3 |
| **Pregão de hoje** | Yahoo Finance, pela função do Netlify | ao abrir o gráfico; atualiza a cada minuto com o pregão aberto | atraso de 15 min do Yahoo |

A coleta **não gasta crédito do Netlify**: o robô grava na pasta `dados/` do
GitHub e o app lê de lá. O site só é republicado quando você sobe arquivo do
app (`public/`, `netlify/`), 15 créditos cada vez.

---

# Já subiu a v1 (ou a v2)? Troque só isto

Conferi arquivo por arquivo contra o que está no seu repositório. **São 4 arquivos**
(GitHub → Add file → Upload files, arrastando de dentro desta pasta):

| Arquivo | Por que |
|---|---|
| `coleta_intraday.py` | grava IBOV, dólar, S&P futuro e DXY; força o fuso de Brasília; dólar em pontos do WDO |
| `netlify/functions/aovivo.mjs` | as mesmas séries no ao vivo (e é a reserva da coleta) |
| `public/app.js` | aba ESTRATÉGIAS com as estratégias da pesquisa e o campo Saída |
| `universo.txt` | explica as séries de referência e como tirar uma delas |

Opcional: `README.md` (só documentação).

**Não precisa mexer** em `netlify.toml`, `.gitignore`, `.github/workflows/`,
`public/index.html`, `manifest.webmanifest` nem nos ícones — não mudaram desde a v1.

Não precisa rodar nada à mão: a próxima coleta agendada já baixa as séries
novas (2 anos em 60 min e 60 dias em 5 min). Se quiser na hora: **Actions →
Coleta intraday → Run workflow** (campos em branco).

Se ainda não subiu nada, siga do começo.

---

# PASSO 0 — Descompactar

Descompacte **`intraday-b3-v2.zip`**. Dentro da pasta tem:

```
.github/workflows/coleta-intraday.yml   ← agenda do robô (pasta oculta!)
netlify/functions/aovivo.mjs            ← pregão ao vivo + reserva da coleta
public/                                  ← o app (index.html, app.js, ícones)
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
3. Abra o app: aba **BASE DE DADOS** mostra o período coletado e a
   **conferência com o COTAHIST** — o fechamento de cada papel-dia comparado com
   o arquivo oficial da B3. É o teste com dado real, e ele roda em toda coleta.

Daí em diante não precisa fazer nada. Se a base atrasar além das 9h15 do dia
seguinte ao pregão, a execução fica **vermelha** e o GitHub manda e-mail.

---

# PARTE 4 — Tablet

Abra o endereço no Chrome → menu ⋮ → **Adicionar à tela inicial**.

---

# Estratégias (aba ESTRATÉGIAS)

1. Escolha a estratégia (toque no nome; o **?** explica a regra e o resultado da
   pesquisa).
2. Ajuste os parâmetros se quiser — **voltar ao padrão da pesquisa** desfaz.
3. Escolha o período (por dia; o padrão é a base de 5 min inteira) e toque em
   **Rodar backtest**.

O resultado mostra soma, média por operação, acerto, pior queda, exposição,
taxas, resultado do hedge, a curva acumulada e cada operação (entrada, saída,
motivo). As regras da simulação (taxa, capital, piso, impacto, custo do hedge)
ficam no fim da aba e valem para todas.

Estratégias incluídas (pesquisa com o COTAHIST 2023–2026, teste fora da amostra
de jul/2025 a set/2026):

| Estratégia | Regra | Teste |
|---|---|---|
| Reversão do gap (neutro) | vende quem abre +0,5% a +1,5% acima do índice, compra quem abre −0,5% a −1,5% abaixo; hedge no WIN; zera no fechamento | +0,22% por operação, Sharpe 5,9, 15/15 meses positivos |
| Compra no gap de baixa em tendência de alta | só a compra, em papel acima da média de 200 dias e volatilidade < 2,5%; vende WIN | +0,28% por operação, Sharpe 5,8 |

## O que a base real já mostrou (28/09/2026, 59 pregões de 5 min)

Rodado sobre a base coletada no seu repositório, com o motor do próprio app:

**1. A entrada tem que ser no leilão de abertura.** O efeito some em 15 minutos:

| Entrada | Média por operação |
|---|---|
| leilão das 10h00 | **+0,152%** |
| 10h05 | +0,060% |
| 10h15 | −0,014% |

Ou seja: o gap precisa ser calculado no **preço teórico da pré-abertura** (09h45–10h00) e a
ordem enviada para o leilão. Não funciona olhar o gap às 10h05 e entrar depois.

**2. O ganho acontece nos 10 primeiros minutos.** Decompondo o pregão (bruto, já sem o
movimento do índice): 10h00→10h05 +0,107%, 10h05→10h10 +0,088%, 10h10→10h15 +0,001%,
10h15→fechamento +0,023%. Segurar o dia inteiro rende quase o mesmo por operação, mas com
muito mais risco:

| Saída | Média/op | Acerto | Sharpe | Pior queda |
|---|---|---|---|---|
| fim do pregão (padrão) | +0,152% | 55,2% | 4,26 | −R$ 2.892 |
| **10h10** | +0,128% | 59,7% | **10,03** | **−R$ 756** |
| 12h00 | +0,185% | 57,7% | 6,72 | −R$ 2.088 |

**Cuidado ao ler isto:** são 59 pregões, o horário de saída foi escolhido *olhando esses
mesmos dados* (não é validação fora da amostra) e o spread pago na saída não está na conta —
o efeito aguenta até ~0,15% de custo total por operação e desaparece em 0,2%. Por isso o
padrão do app continua no fim do pregão, que é o que os 3,7 anos de COTAHIST validaram.
Use o campo **Saída** para acompanhar isso conforme a base cresce (ela ganha um pregão por dia).

**3. A base do Yahoo não traz o leilão de fechamento** (o último candle é 16:50 em 94% dos
casos). Isso explica a conferência com o COTAHIST ficar em ~78% em vez de ~97%, e **não
atrapalha**: a abertura bate exata com a B3 (diferença mediana 0,0000%) e trocar o leilão pelo
candle das 16:50 muda −0,003 pp por operação.

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
- **Repositório com outro nome**: no app, aba **BASE DE DADOS → Neste aparelho**.

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
| `coleta_intraday.py` | coleta, grava `dados/`, confere com o COTAHIST, audita (`--verificar`) |
| `.github/workflows/coleta-intraday.yml` | agenda o robô |
| `universo.txt` | exceções do universo |
| `dados/` | a base (criada pelo robô — não mexa à mão) |
| `netlify.toml` | publica `public/`, função, e só republica quando o app muda |
