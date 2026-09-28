# Intraday · B3

Base de candles intradiários da B3 (5 e 60 min), pregão ao vivo e motor de
estratégias de day trade. Mesmo esquema do overnight: o app mora no Netlify,
os dados moram no GitHub e um robô do GitHub Actions coleta tudo sozinho.

## Como os dados chegam

| | Fonte | Quando | Profundidade |
|---|---|---|---|
| **Candles de 5 min** | Yahoo Finance | robô, 19h30 / 23h30 / 9h30, todo dia | carga inicial = 60 dias corridos (~43 pregões); daí em diante **acumula** um pregão por dia |
| **Candles de 60 min** | Yahoo Finance | carga inicial; depois = soma dos de 5 min | ~2 anos |
| **Pregão de hoje** | Yahoo Finance, pela função do Netlify | ao abrir o gráfico; atualiza a cada minuto com o pregão aberto | atraso de 15 min do Yahoo |

A coleta **não gasta crédito do Netlify**: o robô grava na pasta `dados/` do
GitHub e o app lê de lá. O site só é republicado quando você sobe arquivo do
app (`public/`, `netlify/`), 15 créditos cada vez.

---

# PASSO 0 — Descompactar

Descompacte **`intraday-b3-v1.zip`**. Dentro da pasta tem:

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
https://SEU-SITE.netlify.app/.netlify/functions/aovivo?t=PETR4
```

Deve voltar um JSON com `"dados":{"PETR4":{"dias":{...}}}`. Fora do horário do
pregão ele traz o último pregão.

---

# PARTE 3 — Carga inicial da base

1. GitHub → aba **Actions** → **Coleta intraday** → **Run workflow** → deixe os
   campos em branco → **Run workflow**.
2. Leva uns 5 a 10 minutos (~340 consultas: 60 dias de 5 min e 2 anos de
   60 min para ~170 papéis). Bolinha amarela vira verde.
3. Abra o app: aba **BASE DE DADOS** mostra o período coletado e a
   **conferência com o COTAHIST** — o fechamento de cada papel-dia comparado com
   o arquivo oficial da B3. É o teste com dado real, e ele roda em toda coleta.

Daí em diante não precisa fazer nada. Se a base atrasar além das 9h15 do dia
seguinte ao pregão, a execução fica **vermelha** e o GitHub manda e-mail.

---

# PARTE 4 — Tablet

Abra o endereço no Chrome → menu ⋮ → **Adicionar à tela inicial**.

---

# Ajustes

- **Universo** (quais papéis entram): monta sozinho a cada coleta a partir do
  COTAHIST do overnight — média de volume financeiro dos últimos 20 pregões,
  descartando os 10% maiores, acima de **R$ 5 MM** (~170 papéis). Exceções no
  `universo.txt` (`+TICKER` inclui, `-TICKER` exclui). Papel que entra já ganha
  os 60 dias de 5 min e os 2 anos de 60 min que o Yahoo tiver.
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
- **Pregão guardado não é reajustado depois**: se houver desdobramento ou
  grupamento, o dia do evento aparece como salto de preço (igual ao COTAHIST) e
  é filtrado na camada das estratégias.
- **A API do Yahoo não é oficial.** Se a coleta parar, olhe o log em Actions;
  a reserva pelo Netlify (URL_APP) cobre bloqueio de IP do GitHub.
- **Tamanho**: ~5 MB por mês de 5 min para ~170 papéis (~60 MB/ano), em
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
