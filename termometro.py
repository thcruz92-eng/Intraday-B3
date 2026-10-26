"""
TERMÔMETRO DA ABERTURA — base de saúde financeira e sensibilidades
============================================================
Grava dados/termometro.json, que a página public/termometro.html lê para
classificar as quedas da abertura entre empresas SAUDÁVEIS.

Para cada papel do universo da coleta:
  - balanço mais recente entregue à CVM (base do projeto overnight,
    dados/cvm/fundamentos.json): caixa + aplicações, dívida CP e LP,
    patrimônio; EBIT, lucro e receita dos últimos 4 trimestres; lucro do
    último trimestre contra o mesmo trimestre do ano anterior
  - beta ao Ibovespa e ao dólar: regressão dos retornos diários de
    fechamento (COTAHIST em dados/diario/) contra o IBOV e o USDBRL
    (último candle de 60 min de cada pregão), últimos ~250 pregões
  - volatilidade diária e último fechamento oficial

A NOTA de saúde é calculada na própria página, porque depende do choque
de juros que você digita (dívida líquida × alta do DI contra o lucro).

Bancos e seguradoras não têm dívida/EBIT no plano de contas padrão: a
saúde deles vem de uma classificação manual (CLASSIF_MANUAL) — revise.

Uso:  python termometro.py                      (baixa a base da CVM do GitHub)
      python termometro.py --cvm caminho/fundamentos.json
"""
import argparse, glob, json, os, re, statistics, urllib.request
from datetime import datetime, timezone, timedelta

CVM_URL = "https://raw.githubusercontent.com/thcruz92-eng/leilao-overnight/main/dados/cvm/fundamentos.json"
SAIDA = "dados/termometro.json"
ESPECIAIS = {"IBOV", "USDBRL", "SP500F", "DXY"}
JANELA_BETA = 250

# Controle estatal (União ou estado): risco de interferência com o governo
# reeleito. A página aplica o "prêmio político" a estes.
ESTATAIS = {
    "PETR3": "União", "PETR4": "União", "BBAS3": "União", "BBSE3": "União (via BB)",
    "CXSE3": "União (via Caixa)", "AXIA3": "União (golden share/influência)",
    "AXIA7": "União (golden share/influência)", "CMIG3": "MG", "CMIG4": "MG",
    "CSMG3": "MG", "SAPR4": "PR", "SAPR11": "PR", "BRSR6": "RS",
}

# Cadastro da CVM com ticker faltando ou errado para estas companhias
ALIAS_CNPJ = {
    "33.042.730/0001-04": ["CSNA3"],
    "08.902.291/0001-15": ["CMIN3"],
    "03.853.896/0001-40": ["MBRF3"],
    "89.637.490/0001-45": ["KLBN3", "KLBN4"],
}

# Fundos imobiliários e ETFs ficam fora do termômetro
def eh_fundo(t, reg):
    return t.endswith("11") and "nome" not in reg and "financeira" not in reg


# Bancos, seguradoras e afins: [nota 0–100, comentário]. Classificação
# manual (plano de contas diferente). Juros altos: seguradoras ganham no
# float; bancos médios sofrem com funding e inadimplência.
CLASSIF_MANUAL = {
    "ITUB3": [90, "ROE ~22%, capital folgado, inadimplência controlada"],
    "ITUB4": [90, "ROE ~22%, capital folgado, inadimplência controlada"],
    "BPAC11": [85, "ROE alto, banco de investimento; volátil em estresse"],
    "BBDC3": [68, "recuperação de rentabilidade em curso"],
    "BBDC4": [68, "recuperação de rentabilidade em curso"],
    "SANB11": [68, "ROE abaixo dos pares"],
    "ABCB4": [70, "atacado, bom capital"],
    "BBAS3": [55, "inadimplência no agro e risco de uso político"],
    "BRSR6": [50, "estatal gaúcha, ROE baixo"],
    "BMGB4": [40, "consignado, funding caro com juro alto"],
    "BPAN4": [45, "varejo de crédito, sensível a juro e inadimplência"],
    "PSSA3": [85, "seguradora: juro alto ajuda o resultado financeiro"],
    "BBSE3": [80, "seguradora: juro alto ajuda; dividendos altos"],
    "CXSE3": [80, "seguradora: juro alto ajuda"],
    "IRBR3": [60, "resseguradora em recuperação"],
    "B3SA3": [80, "caixa líquido; volume sobe em estresse"],
    "BRBI11": [60, "banco médio"],
}

# bancos/seguradoras fora de CLASSIF_MANUAL: sem nota (plano de contas diferente)
FIN = re.compile(r"\bBCO\b|BANCO|SEGUR|RESSEGUR|FINANC")

# nome para os que a CVM não liga ao ticker (units de banco)
NOMES_MANUAIS = {"BPAC11": "BANCO BTG PACTUAL S.A.", "SANB11": "BANCO SANTANDER (BRASIL) S.A.",
                 "BRBI11": "BR ADVISORY PARTNERS PARTICIPAÇÕES S.A."}


def baixar_json(origem):
    if os.path.exists(origem):
        return json.load(open(origem, encoding="utf-8"))
    print("baixando", origem, flush=True)
    req = urllib.request.Request(origem, headers={"User-Agent": "intraday-b3/termometro"})
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())


def trimestres(emp):
    """valores de cada trimestre fiscal (mesma lógica do resumo_fundamentos do overnight)"""
    q, ytd = {}, {}
    for doc in emp["docs"]:
        if not doc.get("entrega") or "dre" not in doc:
            continue
        for per, vals in doc["dre"].items():
            ini, fim = per.split(":")
            if not ini or not fim:
                continue
            ano, mfim, mini = int(fim[:4]), int(fim[5:7]), int(ini[5:7])
            tri = (mfim - 1) // 3 + 1
            if mfim - mini + 1 == 3:
                k = (ano, tri)
                if k not in q or doc["entrega"] < q[k]["entrega"]:
                    q[k] = dict(vals, entrega=doc["entrega"])
            if mini == 1:
                ytd.setdefault((ano, tri), (vals, doc["entrega"]))
    for (ano, tri), (vals, ent) in ytd.items():
        if tri == 4 and (ano, 3) in ytd and (ano, 4) not in q:
            v9 = ytd[(ano, 3)][0]
            q[(ano, 4)] = {k: vals[k] - v9[k] for k in vals if k in v9 and vals[k] is not None and v9[k] is not None}
            q[(ano, 4)]["entrega"] = ent
    return q


def ultimos12(q, campo):
    chaves = sorted(q)[-4:]
    if len(chaves) < 4 or chaves[0] != _menos3(chaves[-1]):
        return None
    vs = [q[k].get(campo) for k in chaves]
    return sum(vs) if all(v is not None for v in vs) else None


def _menos3(k):
    ano, tri = k
    tri -= 3
    if tri < 1:
        ano, tri = ano - 1, tri + 4
    return (ano, tri)


def doze_meses(emp, campo):
    """fallback para exercício fora do ano civil (ex. abr–mar): último ano
    fechado + acumulado do exercício atual − mesmo acumulado do anterior"""
    per = {}
    for doc in sorted(emp["docs"], key=lambda d: d.get("entrega") or ""):
        for p, vals in (doc.get("dre") or {}).items():
            per.setdefault(p, vals)

    def meses(p):
        ini, fim = p.split(":")
        return (int(fim[:4]) - int(ini[:4])) * 12 + int(fim[5:7]) - int(ini[5:7]) + 1

    anuais = sorted(p for p in per if meses(p) == 12 and per[p].get(campo) is not None)
    if not anuais:
        return None
    a = anuais[-1]
    total = per[a][campo]
    melhor = None
    for p, vals in per.items():
        ini, fim = p.split(":")
        if ini > a[11:] and meses(p) < 12 and int(ini[5:7]) == int(a[5:7]) and vals.get(campo) is not None:
            if melhor is None or fim > melhor.split(":")[1]:
                melhor = p
    if melhor:
        ini, fim = melhor.split(":")
        ant = f"{int(ini[:4]) - 1}{ini[4:]}:{int(fim[:4]) - 1}{fim[4:]}"
        if ant in per and per[ant].get(campo) is not None:
            total += per[melhor][campo] - per[ant][campo]
    return total


def fundamentos_por_ticker(cvm):
    out = {}
    for cnpj, e in cvm["empresas"].items():
        bal = sorted([d for d in e["docs"] if d.get("entrega") and d.get("patrimonio") is not None],
                     key=lambda d: (d["ref"], d.get("con", False), d["entrega"]))
        if not bal:
            continue
        b = bal[-1]
        q = trimestres(e)
        ult = max(q) if q else None
        g = None
        if ult and (ult[0] - 1, ult[1]) in q:
            ll, ll0 = q[ult].get("lucroLiquido"), q[(ult[0] - 1, ult[1])].get("lucroLiquido")
            if ll is not None and ll0:
                g = round((ll - ll0) / abs(ll0), 4)
        caixa = (b.get("caixa") or 0) + (b.get("aplicacoes") or 0)
        div_cp, div_lp = b.get("dividaCP") or 0, b.get("dividaLP") or 0
        reg = {
            "nome": e.get("nome"),
            "ref": b["ref"],
            "caixa": caixa,
            "divCP": div_cp,
            "divLP": div_lp,
            "pl": b.get("patrimonio"),
            "ebit12": ultimos12(q, "ebit") or doze_meses(e, "ebit"),
            "lucro12": ultimos12(q, "lucroLiquido") or doze_meses(e, "lucroLiquido"),
            "receita12": ultimos12(q, "receita") or doze_meses(e, "receita"),
            "lucroTriAA": g,
        }
        for t in (e.get("tickers") or []) + ALIAS_CNPJ.get(cnpj, []):
            out[t] = reg
    return out


def series_diarias():
    """fechamento diário (R$) dos papéis (COTAHIST) e do IBOV/USDBRL (último candle de 60 min)"""
    fech = {}
    for arq in sorted(glob.glob("dados/diario/*.json")):
        for dia, papeis in json.load(open(arq, encoding="utf-8"))["dias"].items():
            for t, v in papeis.items():
                fech.setdefault(t, {})[dia] = v[3] / 100
    for arq in sorted(glob.glob("dados/60m/*.json")):
        for dia, series in json.load(open(arq, encoding="utf-8"))["dias"].items():
            for t in ("IBOV", "USDBRL"):
                plano = series.get(t)
                if not plano:
                    continue
                p = plano[1]
                for i in range(2, len(plano), 6):
                    p += plano[i + 4]
                fech.setdefault(t, {})[dia] = p / 100
    return fech


def retornos(serie, dias):
    out = {}
    for a, b in zip(dias, dias[1:]):
        if a in serie and b in serie and serie[a] > 0:
            r = serie[b] / serie[a] - 1
            if abs(r) < 0.25:  # desdobramento/grupamento fica de fora
                out[b] = r
    return out


def regressao(y, x1, x2):
    """y = a + b1·x1 + b2·x2 por mínimos quadrados (equações normais 2×2 centradas)"""
    n = len(y)
    my, m1, m2 = sum(y) / n, sum(x1) / n, sum(x2) / n
    s11 = sum((a - m1) ** 2 for a in x1)
    s22 = sum((a - m2) ** 2 for a in x2)
    s12 = sum((a - m1) * (b - m2) for a, b in zip(x1, x2))
    s1y = sum((a - m1) * (c - my) for a, c in zip(x1, y))
    s2y = sum((a - m2) * (c - my) for a, c in zip(x2, y))
    det = s11 * s22 - s12 * s12
    if det <= 0:
        return None, None
    return (s1y * s22 - s2y * s12) / det, (s2y * s11 - s1y * s12) / det


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cvm", default=CVM_URL, help="fundamentos.json do overnight (arquivo ou URL)")
    args = ap.parse_args()

    indice = json.load(open("dados/indice.json", encoding="utf-8"))
    universo = [t for t in indice["universo"]["ativos"] if t not in ESPECIAIS]
    fund = fundamentos_por_ticker(baixar_json(args.cvm))
    fech = series_diarias()

    dias_ibov = sorted(fech.get("IBOV", {}))[-(JANELA_BETA + 1):]
    r_ibov = retornos(fech["IBOV"], dias_ibov)
    r_usd = retornos(fech.get("USDBRL", {}), dias_ibov)

    papeis = {}
    for t in universo:
        serie = fech.get(t, {})
        if not serie:
            continue
        ultimo = max(serie)
        r = retornos(serie, dias_ibov)
        comuns = [d for d in r if d in r_ibov and d in r_usd]
        beta = beta_usd = None
        if len(comuns) >= 60:
            beta, beta_usd = regressao([r[d] for d in comuns], [r_ibov[d] for d in comuns], [r_usd[d] for d in comuns])
        vol = statistics.pstdev(list(r.values())) if len(r) >= 20 else None
        reg = {
            "fech": serie[ultimo],
            "dataFech": ultimo,
            "beta": None if beta is None else round(beta, 3),
            "betaUsd": None if beta_usd is None else round(beta_usd, 3),
            "vol": None if vol is None else round(vol, 4),
            "pregoesBeta": len(comuns),
        }
        f = fund.get(t)
        if f:
            reg.update(f)
        if t in ESTATAIS:
            reg["estatal"] = ESTATAIS[t]
        if t in CLASSIF_MANUAL:
            reg["financeira"] = CLASSIF_MANUAL[t]
            reg.setdefault("nome", NOMES_MANUAIS.get(t))
        elif FIN.search(reg.get("nome") or "") and "CORRETORA" not in (reg.get("nome") or ""):
            reg["semNota"] = "banco/seguradora fora da classificação manual"
        if eh_fundo(t, reg):
            continue
        papeis[t] = reg

    agora = datetime.now(timezone(timedelta(hours=-3))).isoformat(timespec="seconds")
    saida = {
        "formato": 1,
        "gerado_em": agora,
        "fontes": {
            "balancos": "CVM ITR/DFP — base do projeto overnight (dados/cvm/fundamentos.json)",
            "precos": "COTAHIST diário (dados/diario/) e IBOV/USDBRL de 60 min (dados/60m/)",
        },
        "janelaBeta": len(dias_ibov) - 1,
        "campos": {
            "caixa": "caixa + aplicações financeiras, R$",
            "divCP/divLP": "empréstimos e financiamentos de curto/longo prazo, R$",
            "ebit12/lucro12/receita12": "soma dos últimos 4 trimestres, R$",
            "lucroTriAA": "lucro do último trimestre contra o mesmo trimestre do ano anterior",
            "beta/betaUsd": "regressão do retorno diário contra IBOV e USDBRL",
            "financeira": "[nota manual 0–100, comentário] — bancos e seguradoras",
        },
        "papeis": papeis,
    }
    os.makedirs("dados", exist_ok=True)
    with open(SAIDA, "w", encoding="utf-8") as f:
        json.dump(saida, f, ensure_ascii=False, separators=(",", ":"))
    com_bal = sum(1 for p in papeis.values() if "ebit12" in p)
    print(f"OK: {len(papeis)} papéis ({com_bal} com balanço, "
          f"{sum(1 for p in papeis.values() if 'financeira' in p)} financeiras manuais) → {SAIDA}")


if __name__ == "__main__":
    main()
