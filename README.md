# Termômetro B3 — swing trade no pânico

**Versão atual: v2.2 (26/10/2026)** — aparece ao lado do título na página.

| Versão | Data | O que mudou |
|---|---|---|
| v2.2 | 26/10/2026 | barra de filtros combináveis sobre a lista: nota, veredito, excesso vs IBOV, queda, lucro em 5/5 anos, caixa líquido, ROE, dív.líq/EBIT, % abaixo do justo/consenso, opções líquidas |
| v2.1 | 26/10/2026 | coluna **opções (só CALL)** por papel com as regras do app de derivativos: vencimento, strike, trava de alta, VH, execução |
| v2.0 | 26/10/2026 | lista única com abas, veredito por papel, resumo em texto, detalhes ao clicar, cartões no celular, preço justo como faixa patrimônio–lucro |
| v1.1 | 26/10/2026 | o termômetro vira o app: preço justo, consenso, lucro constante, racionalidade da queda |
| v1.0 | 26/10/2026 | termômetro da abertura dentro do app intraday |

Ao mudar o app, atualize a etiqueta em `public/index.html` (ao lado do `<h1>`) e esta tabela.

Página única (`public/index.html`, publicada no Netlify) que responde três perguntas para cada
papel líquido da B3:

1. **A empresa é boa?** Nota de saúde 0–100 pelo último balanço na CVM: lucro, dívida líquida/EBIT,
   dívida de curto prazo contra o caixa, ROE, margem, lucro constante nos últimos 5 exercícios e o
   **choque do DI** (quanto do lucro a alta do juro consome via dívida líquida).
2. **Caiu muito além do Ibovespa? Por quê?** Excesso = queda do dia − beta × Ibovespa. A coluna
   *racionalidade* diz se o excesso tem motivo no balanço (dívida, prejuízo, estatal) ou é exagero
   — candidata a recuperar.
3. **Qual o preço justo?** Lucro residual sobre o patrimônio (Gordon no P/VP) com ROE normalizado
   e custo de capital = DI longo + prêmio; conferido por *justo pelo lucro*, *Graham* e o
   **consenso de bancos/casas** (`dados/alvos.json`). Mostra a **distorção** tela ÷ justo.

A lista **Candidatas ao swing** filtra saudáveis, líquidas e caindo além da queda mínima,
ordenadas por oportunidade; **Armadilhas** são as que caem muito mas o balanço não aguenta o DI.
Não é recomendação de investimento.

## Arquivos

| Arquivo | Para que serve |
|---|---|
| `public/index.html` | a página (HTML + JS, sem build) |
| `termometro.py` | gera `dados/termometro.json`: balanços (CVM, via base do projeto overnight), betas, ações em circulação, lucros anuais, consenso |
| `dados/alvos.json` | preço-alvo de consenso por papel, **manual** — `{preco, fonte, data, n}`. Edite quando as casas revisarem |
| `dados/termometro.json` | saída do `termometro.py`; a página lê daqui |
| `coleta_intraday.py` + `.github/workflows/coleta-intraday.yml` | o robô: traz o COTAHIST diário (`dados/diario/`) e o IBOV/dólar (`dados/60m/`), de onde saem fechamento, variação do dia e betas; depois roda o `termometro.py` |
| `netlify/functions/aovivo.mjs` | preço de tela pelo Yahoo (15 min de atraso) para o botão **buscar preço de tela agora** |
| `netlify.toml` | publica `public/` e só republica quando o app muda |

O robô ainda coleta candles de 5 e 60 min (herança do intraday); a página só usa o diário e o
IBOV/dólar de 60 min. Para parar de coletar 5 min, tire o intervalo no `coleta_intraday.py`.

## Rodar à mão

```
python termometro.py                      # baixa a base da CVM do repositório overnight
python termometro.py --cvm fundamentos.json
```

Parâmetros na página (ficam salvos no aparelho): Ibovespa e dólar do dia, amplificação do pânico,
DI antes/agora (choque no lucro), **juro longo + prêmio de risco + g** (preço justo), nota mínima,
queda mínima, volume mínimo, estatais. Preços: botão do Yahoo, ou colar do Profit
(`PETR4 31,20` ou `PETR4 -12,5%`).

## Preço justo — por que sai abaixo do consenso

`Justo = VPA × (ROEn − g) / (Ke − g)`. Com o DI jan/2035 a 15,4% (26/10/2026) e prêmio de 4,5%,
Ke ≈ 20%: P/L justo de 6,7× e P/VP justo de 1,0× para ROE de 20%. Os bancos usam Ke de 13–15% e
horizonte de 12 meses, por isso os alvos deles são 40–60% maiores. Ponha 12,7 no juro longo (o DI
2035 de sexta) para ver o valor com o juro de antes da eleição.

Bancos: sem preço justo pelo modelo (o plano de contas da CVM não traz patrimônio comparável);
só nota manual (`termometro.py`) e consenso.
