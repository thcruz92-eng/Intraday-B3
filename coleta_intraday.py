# -*- coding: utf-8 -*-
"""
COLETA INTRADAY — B3 via Yahoo Finance
====================================================================
Mantém a base de candles intradiários que o app lê direto do GitHub.

    dados/5m/AAAA-MM.json    candles de 5 min
    dados/60m/AAAA-MM.json   candles de 60 min
    dados/indice.json        o app lê este primeiro: meses, assinaturas,
                             universo, cobertura e conferência com o COTAHIST

Profundidade que o Yahoo entrega de graça:
    5 min   -> só os últimos 60 dias CORRIDOS (~41 pregões)
    60 min  -> últimos 730 dias corridos (~2 anos)
Por isso a base de 5 min ACUMULA: todo pregão coletado fica guardado
aqui para sempre, mesmo depois que o Yahoo apaga.

A base de 60 min vem do Yahoo uma vez (carga inicial de 2 anos) e daí
em diante é montada somando os candles de 5 min de cada pregão — as
duas bases nunca divergem e a coleta diária faz metade das consultas.

Séries de REFERÊNCIA (v2): além das ações, a coleta grava sempre o
Ibovespa (IBOV), o dólar à vista (USDBRL), o S&P 500 futuro (SP500F) e o
índice do dólar (DXY) — base para estudar WIN e WDO. Elas ficam só no
horário dos minicontratos (09:00–18:30) e só em dia de pregão da B3.

Modos:
    python coleta_intraday.py                    # incremental (o normal)
    python coleta_intraday.py --completo         # rebaixa tudo que o Yahoo tem
    python coleta_intraday.py --ativos PETR4,VALE3
    python coleta_intraday.py --verificar        # só audita a base publicada

Regras fixas (e por quê):
  * Só entra pregão ENCERRADO. Rodar às 14h não grava meio pregão.
  * Dia já gravado NÃO é trocado pela versão ajustada do Yahoo
    (desdobramento/grupamento). O Yahoo reajusta o histórico inteiro
    para trás; se aceitássemos, a quebra de preço sairia da data real do
    evento e iria parar numa data aleatória (a borda da janela de coleta).
    Guardando o dado como foi negociado, a quebra fica no dia do evento —
    igual ao COTAHIST — e o filtro de evento corporativo consegue achá-la.
  * Dia já gravado PODE ser completado (mais candles, volume revisado)
    quando os preços batem com o que está guardado.
  * Arquivo só é reescrito quando o conteúdo muda — sem commit à toa.
  * Quem decide verde/vermelho é só o modo --verificar.
  * Horário SEMPRE de Brasília: o Yahoo informa o fuso da bolsa de cada
    símbolo (o dólar vem no fuso de Londres); aqui tudo é convertido para
    UTC-3, o fuso da B3.

Formato de um pregão de um ativo (lista plana de inteiros):
    [m0, p0,  dm, do, dh, dl, dc, v,  dm, do, dh, dl, dc, v, ...]
    m0 = minuto do dia (Brasília) do 1º candle   (600 = 10:00)
    p0 = preço de referência, em centavos          (abertura do 1º candle)
    por candle: dm = minutos desde o candle anterior (0 no primeiro)
                do/dh/dl/dc = abertura/máxima/mínima/fechamento em centavos,
                              relativos ao FECHAMENTO do candle anterior
                              (no primeiro, relativos a p0)
                v  = quantidade de papéis negociados
Deltas pequenos = arquivo ~45% menor que guardar o preço cheio.
"""

import argparse
import hashlib
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from statistics import median

# ------------------------------------------------------------------
# Configuração
# ------------------------------------------------------------------
DIR_DADOS = os.environ.get("DIR_DADOS", "dados")
INDICE = os.path.join(DIR_DADOS, "indice.json")
UNIVERSO_TXT = os.environ.get("UNIVERSO_TXT", "universo.txt")

# Base oficial do projeto overnight (COTAHIST). Usada para duas coisas:
# escolher o universo pelo mesmo critério de liquidez e conferir se o
# fechamento/quantidade do Yahoo batem com o arquivo oficial da B3.
OVERNIGHT_URL = os.environ.get(
    "OVERNIGHT_URL",
    "https://raw.githubusercontent.com/thcruz92-eng/leilao-overnight/main/public/base_b3.json",
)

YAHOO_HOSTS = [h.rstrip("/") for h in os.environ.get(
    "YAHOO_BASE",
    "https://query1.finance.yahoo.com,https://query2.finance.yahoo.com",
).split(",") if h.strip()]

# Reserva: a função do próprio app no Netlify (IPs diferentes do GitHub).
# Preencha a variável URL_APP no repositório (Settings > Secrets and
# variables > Actions > Variables) com o endereço do site.
URL_APP = os.environ.get("URL_APP", "").strip().rstrip("/")

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")

INTERVALOS = (5, 60)
RANGE_COMPLETO = {5: "60d", 60: "730d"}
# se o range cheio for recusado (borda dos 60/730 dias), tenta um pouco menos
RANGE_COMPLETO_RESERVA = {5: "59d", 60: "729d"}

ESPACO_ENTRE_CONSULTAS = float(os.environ.get("ESPACO_CONSULTAS", "0.35"))
ESPERA_429 = float(os.environ.get("ESPERA_429", "15"))    # segundos, cresce a cada tentativa
ESPERA_ERRO = float(os.environ.get("ESPERA_ERRO", "3"))
FALHAS_SEGUIDAS_PARA_RESERVA = 8

MINUTO_ABERTURA = 600          # 10:00 — âncora da grade dos candles
FIM_SESSAO_MIN = 18 * 60 + 15  # 18:15: depois disso o pregão do dia está encerrado
# (cobre o fechamento das 17h e o das 18h, quando a B3 muda de horário)

# O pregão esperado tem até 09:15 do dia seguinte para estar na base.
# Depois disso a verificação fica vermelha (e o GitHub manda e-mail).
HORAS_TOLERANCIA = 15
COBERTURA_MINIMA = 0.80

FUSO_BR = timezone(timedelta(hours=-3))  # Brasil sem horário de verão desde 2019
OFFSET_BR = -3 * 3600

# Séries de referência (não são ações da B3): nome na base -> símbolo no Yahoo.
# Mesma lista em src/lib/especiais.js e netlify/functions/aovivo.mjs.
ESPECIAIS = {
    "IBOV": "^BVSP",       # Ibovespa à vista — referência do WIN
    "USDBRL": "BRL=X",     # dólar à vista — referência do WDO
    "SP500F": "ES=F",      # S&P 500 futuro (CME)
    "DXY": "DX-Y.NYB",     # índice do dólar (ICE)
}
# guardadas só no horário dos minicontratos da B3
JANELA_ESPECIAIS = (9 * 60, 18 * 60 + 30)
# Multiplicador do preço do Yahoo antes de guardar em centavos. O dólar vira
# pontos do WDO (R$ por US$ 1.000, como o mini dólar é cotado): 5,2345 -> 5.234,50.
# Sem isso, guardado em centavos de real, o dólar perderia a 3ª e a 4ª casa.
ESCALA = {"USDBRL": 1000}

# Mesma lista do projeto overnight — mantenha as duas iguais.
FERIADOS_B3 = {
    "2026-01-01", "2026-02-16", "2026-02-17", "2026-04-03", "2026-04-21",
    "2026-05-01", "2026-06-04", "2026-09-07", "2026-10-12", "2026-11-02",
    "2026-11-15", "2026-11-20", "2026-12-24", "2026-12-25", "2026-12-31",
    "2027-01-01", "2027-02-08", "2027-02-09", "2027-03-26", "2027-04-21",
    "2027-05-01", "2027-05-27", "2027-09-07", "2027-10-12", "2027-11-02",
    "2027-11-15", "2027-11-20", "2027-12-24", "2027-12-25", "2027-12-31",
}

# Universo de reserva (média aparada de 20 pregões >= R$ 5 MM no COTAHIST
# de 25/09/2026). Só é usado se a base do overnight estiver inacessível
# E ainda não existir índice anterior.
UNIVERSO_SEMENTE = """
ABCB4 ABEV3 ALOS3 ALPA4 ALUP11 ANIM3 ASAI3 AUAU3 AURE3 AXIA3 AXIA7 AZEV3 AZZA3
B3SA3 BBAS3 BBDC3 BBDC4 BBSE3 BEEF3 BMGB4 BMOB3 BPAC11 BRAP4 BRAV3 BRCO11 BRSR6
BTLG11 CASH3 CBAV3 CEAB3 CMIG4 CMIN3 COGN3 CPFE3 CPLE3 CPTS11 CSAN3 CSMG3 CSNA3
CURY3 CVCB3 CXSE3 CYRE3 CYRE4 DESK3 DIRR3 DXCO3 ECOR3 EGIE3 EMBJ3 ENEV3 ENGI11
EQTL3 EVEN3 EZTC3 FESA4 FLRY3 GARE11 GGBR4 GGPS3 GGRC11 GMAT3 GOAU4 GRND3 HAPV3
HGBS11 HGLG11 HGRU11 HYPE3 IBOV11 IGTI11 INTB3 IRBR3 ISAE4 ITSA4 ITUB3 ITUB4
JHSF3 JSLG3 KEPL3 KLBN11 KLBN4 KNCR11 KNIP11 KNRI11 KNUQ11 LAVV3 LEVE3 LIGT3
LOGG3 LREN3 LWSA3 MBRF3 MDIA3 MDNE3 MGLU3 MILS3 MOTV3 MOVI3 MRVE3 MULT3 MXRF11
MYPK3 NATU3 OBTC3 OPCT3 ORVR3 PASS3 PETR3 PETR4 PGMN3 PINE4 PLPL3 PNVL3 POMO3
POMO4 PRIO3 PRNR3 PSSA3 QUAL3 RADL3 RAIL3 RAPT4 RDOR3 RECV3 RENT3 RENT4 RIAA3
SANB11 SAPR11 SAPR4 SAUD3 SBFG3 SBSP3 SEER3 SIMH3 SLCE3 SMFT3 SMTO3 SNEL11
SOJA3 SUZB3 TAEE11 TASA4 TEND3 TFCO4 TGMA3 TIMS3 TOTS3 TRXF11 TTEN3 TUPY3 UGPA3
UNIP6 USIM3 USIM5 VALE3 VAMO3 VBBR3 VISC11 VIVA3 VIVT3 VTRU3 VULC3 VXXV11 WEGE3
XPLG11 XPML11 YDUQ3
""".split()


def log(msg="", erro=False):
    print(msg, file=sys.stderr if erro else sys.stdout, flush=True)


# ------------------------------------------------------------------
# Relógio e calendário (Brasília)
# ------------------------------------------------------------------
def agora_br() -> datetime:
    """Permite simular o relógio nos testes: AGORA_BR=2026-09-28T19:00"""
    simulado = os.environ.get("AGORA_BR")
    if simulado:
        return datetime.fromisoformat(simulado).replace(tzinfo=FUSO_BR)
    return datetime.now(FUSO_BR)


def eh_pregao(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in FERIADOS_B3


def minuto_do_dia(dt: datetime) -> int:
    return dt.hour * 60 + dt.minute


def ultimo_pregao_encerrado(agora: datetime = None) -> date:
    """O pregão mais recente que já terminou."""
    agora = agora or agora_br()
    d = agora.date()
    if not (eh_pregao(d) and minuto_do_dia(agora) >= FIM_SESSAO_MIN):
        d -= timedelta(days=1)
    while not eh_pregao(d):
        d -= timedelta(days=1)
    return d


def sessao_encerrada(dia: str, agora: datetime = None) -> bool:
    agora = agora or agora_br()
    hoje = agora.date().isoformat()
    if dia < hoje:
        return True
    if dia > hoje:
        return False
    return minuto_do_dia(agora) >= FIM_SESSAO_MIN


# ------------------------------------------------------------------
# Formato compacto
# ------------------------------------------------------------------
def codificar(barras):
    """barras: [(minuto, o, h, l, c, v)] com preços em centavos, ordenadas."""
    if not barras:
        return []
    m0, p0 = barras[0][0], barras[0][1]
    out = [m0, p0]
    ref_m, ref_p = m0, p0
    for m, o, h, l, c, v in barras:
        out += [m - ref_m, o - ref_p, h - ref_p, l - ref_p, c - ref_p, int(v)]
        ref_m, ref_p = m, c
    return out


def decodificar(plano):
    if not plano:
        return []
    m, p = plano[0], plano[1]
    out = []
    for i in range(2, len(plano), 6):
        dm, do, dh, dl, dc, v = plano[i:i + 6]
        m += dm
        o, h, l, c = p + do, p + dh, p + dl, p + dc
        out.append((m, o, h, l, c, v))
        p = c
    return out


def agregar(barras, intervalo):
    """Soma candles menores num intervalo maior, na grade que começa às 10:00."""
    out = []
    for m, o, h, l, c, v in barras:
        balde = m - ((m - MINUTO_ABERTURA) % intervalo)
        if out and out[-1][0] == balde:
            bm, bo, bh, bl, _bc, bv = out[-1]
            out[-1] = (bm, bo, max(bh, h), min(bl, l), c, bv + v)
        else:
            out.append((balde, o, h, l, c, v))
    return out


def assinatura(obj) -> str:
    bruto = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha1(bruto).hexdigest()[:12]


# ------------------------------------------------------------------
# Yahoo
# ------------------------------------------------------------------
class SemDados(Exception):
    """Yahoo respondeu, mas não tem esse papel/período."""


class Bloqueio(Exception):
    """429/403/queda de rede — o problema é o acesso, não o papel."""


def simbolo_yahoo(ticker: str) -> str:
    return ESPECIAIS.get(ticker) or f"{ticker}.SA"


def _contexto_tls():
    ctx = ssl.create_default_context()
    ca = os.environ.get("SSL_CERT_FILE")
    if ca and os.path.exists(ca):
        ctx.load_verify_locations(ca)
    return ctx


def _get_json(url: str, timeout: int = 40):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept": "application/json",
    })
    ctx = _contexto_tls() if url.startswith("https") else None
    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_yahoo(js: dict, intervalo: int, escala: float = 1):
    """Resposta do v8/chart -> {dia: [(minuto, o, h, l, c, v)]}.

    Cuidados:
      * horário sempre de Brasília (UTC-3), qualquer que seja o fuso da
        bolsa informado pelo Yahoo (o dólar vem no fuso de Londres)
      * candle sem preço (sem negócio) vem null -> descartado
      * máxima/mínima incoerentes com abertura/fechamento são corrigidas
      * linha fora da grade (o "último negócio" que o Yahoo às vezes
        pendura no fim) só entra se o horário dela não tiver candle
      * candle de enchimento (volume 0, preço parado) é descartado"""
    chart = js.get("chart") or {}
    if chart.get("error"):
        raise SemDados(str(chart["error"].get("description") or chart["error"]))
    res = (chart.get("result") or [None])[0]
    if not res:
        raise SemDados("resposta vazia")
    off = OFFSET_BR
    ts = res.get("timestamp") or []
    q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
    O, H, L, C, V = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))

    por_dia = {}
    for i, t in enumerate(ts):
        try:
            o, h, l, c = O[i], H[i], L[i], C[i]
            v = V[i] if i < len(V) else 0
        except IndexError:
            continue
        if None in (o, h, l, c) or min(o, h, l, c) <= 0:
            continue
        o, h, l, c = (int(round(x * escala * 100)) for x in (o, h, l, c))
        h, l = max(h, o, c), min(l, o, c)
        local = datetime.fromtimestamp(t + off, tz=timezone.utc)
        dia = local.date().isoformat()
        m = local.hour * 60 + local.minute
        alinhado = m - ((m - MINUTO_ABERTURA) % intervalo)
        por_dia.setdefault(dia, []).append((alinhado, alinhado == m, o, h, l, c, int(v or 0)))

    out = {}
    for dia, linhas in por_dia.items():
        slots = {}
        for m, na_grade, o, h, l, c, v in linhas:
            if m in slots and not na_grade:
                continue                      # linha fora da grade não pisa em candle real
            slots[m] = (m, o, h, l, c, v)     # repetido na grade: fica o último
        barras = []
        for m in sorted(slots):
            b = slots[m]
            if barras and b[5] == 0 and b[1] == b[2] == b[3] == b[4] == barras[-1][4]:
                continue                      # enchimento
            barras.append(b)
        if barras:
            out[dia] = barras
    return out


def calendario_b3(overnight):
    """Pregões que a B3 de fato teve: as datas do COTAHIST do overnight (arquivo
    oficial). A lista de feriados do código só cobre 2026-2027; o COTAHIST cobre
    todo o histórico. Devolve (datas, última data do arquivo)."""
    if not overnight or not overnight.get("dados"):
        return set(), None
    datas = {l[0] for linhas in overnight["dados"].values() for l in linhas}
    return datas, (max(datas) if datas else None)


def recortar_especial(dias, calendario=(set(), None)):
    """Série de referência: só pregão da B3 e só 09:00–18:30.
    Até a última data do COTAHIST vale o calendário oficial; depois dela (o
    arquivo sai com atraso), dia útil fora da lista de feriados."""
    pregoes, ate = calendario
    ini, fim = JANELA_ESPECIAIS
    out = {}
    for dia, barras in dias.items():
        if ate and dia <= ate:
            if dia not in pregoes:
                continue
        elif not eh_pregao(date.fromisoformat(dia)):
            continue
        b = [x for x in barras if ini <= x[0] < fim]
        if b:
            out[dia] = b
    return out


def consultar_yahoo(ticker: str, intervalo: int, rng: str):
    """Tenta os dois hosts do Yahoo, com espera crescente em caso de 429."""
    sym = urllib.parse.quote(simbolo_yahoo(ticker), safe="")
    ultimo = None
    for tentativa in range(3):
        host = YAHOO_HOSTS[tentativa % len(YAHOO_HOSTS)]
        url = (f"{host}/v8/finance/chart/{sym}?interval={intervalo}m"
               f"&range={rng}&includePrePost=false&events=")
        try:
            return parse_yahoo(_get_json(url), intervalo, ESCALA.get(ticker, 1))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise SemDados("Yahoo não tem esse papel (404)")
            if e.code == 422 or e.code == 400:
                raise SemDados(f"range recusado ({e.code})")
            ultimo = Bloqueio(f"HTTP {e.code}")
            espera = ESPERA_429 * (tentativa + 1) if e.code == 429 else ESPERA_ERRO
        except SemDados:
            raise
        except Exception as e:  # rede, TLS, JSON truncado
            ultimo = Bloqueio(f"{type(e).__name__}: {e}")
            espera = ESPERA_ERRO
        if tentativa < 2:
            time.sleep(espera)
    raise ultimo


def consultar_reserva(ticker: str, intervalo: int, rng: str):
    """Mesma consulta pela função aovivo do app no Netlify."""
    url = (f"{URL_APP}/.netlify/functions/aovivo?t={urllib.parse.quote(ticker)}"
           f"&intervalo={intervalo}&range={rng}")
    try:
        js = _get_json(url, timeout=70)
    except urllib.error.HTTPError as e:
        raise Bloqueio(f"reserva HTTP {e.code}")
    except Exception as e:
        raise Bloqueio(f"reserva: {type(e).__name__}: {e}")
    item = (js.get("dados") or {}).get(ticker)
    if not item:
        raise SemDados("; ".join(js.get("falhas") or []) or "reserva sem dados")
    return {dia: decodificar(plano) for dia, plano in (item.get("dias") or {}).items()}


class Coletor:
    """Decide entre acesso direto e reserva, e conta as consultas."""

    def __init__(self, calendario=(set(), None)):
        self.modo = "direto"
        self.falhas_seguidas = 0
        self.consultas = 0
        self.desistiu = False
        self.calendario = calendario

    def buscar(self, ticker, intervalo, rng):
        if self.desistiu:
            raise Bloqueio("acesso ao Yahoo suspenso nesta execução")
        self.consultas += 1
        time.sleep(ESPACO_ENTRE_CONSULTAS)
        try:
            if self.modo == "direto":
                r = consultar_yahoo(ticker, intervalo, rng)
            else:
                r = consultar_reserva(ticker, intervalo, rng)
            self.falhas_seguidas = 0
            return recortar_especial(r, self.calendario) if ticker in ESPECIAIS else r
        except Bloqueio:
            self.falhas_seguidas += 1
            if self.falhas_seguidas >= FALHAS_SEGUIDAS_PARA_RESERVA:
                if self.modo == "direto" and URL_APP:
                    log(f"  !! {self.falhas_seguidas} bloqueios seguidos no acesso direto — "
                        f"passando a usar a reserva ({URL_APP})", erro=True)
                    self.modo = "reserva"
                    self.falhas_seguidas = 0
                else:
                    self.desistiu = True
                    log("  !! acesso ao Yahoo bloqueado"
                        + ("" if URL_APP else " e URL_APP não configurada")
                        + " — encerrando as consultas desta execução", erro=True)
            raise


# ------------------------------------------------------------------
# Armazenamento
# ------------------------------------------------------------------
def caminho_mes(intervalo: int, mes: str) -> str:
    return os.path.join(DIR_DADOS, f"{intervalo}m", f"{mes}.json")


class Loja:
    """Meses carregados sob demanda; só grava o que mudou."""

    def __init__(self):
        self.meses = {}       # (intervalo, mes) -> {dia: {ticker: plano}}
        self.alterados = set()

    def mes(self, intervalo, mes):
        chave = (intervalo, mes)
        if chave not in self.meses:
            arq = caminho_mes(intervalo, mes)
            dias = {}
            if os.path.exists(arq):
                with open(arq, encoding="utf-8") as f:
                    dias = json.load(f).get("dias", {})
            self.meses[chave] = dias
        return self.meses[chave]

    def ler(self, intervalo, dia, ticker):
        return self.mes(intervalo, dia[:7]).get(dia, {}).get(ticker)

    def gravar(self, intervalo, dia, ticker, plano):
        m = self.mes(intervalo, dia[:7])
        m.setdefault(dia, {})[ticker] = plano
        self.alterados.add((intervalo, dia[:7]))

    def salvar(self):
        gravados = []
        for intervalo, mes in sorted(self.alterados):
            dias = self.meses[(intervalo, mes)]
            dias = {d: {t: dias[d][t] for t in sorted(dias[d])} for d in sorted(dias)}
            doc = {
                "formato": 1,
                "intervalo": intervalo,
                "mes": mes,
                "campos": "[m0,p0, dm,do,dh,dl,dc,v, ...] — ver coleta_intraday.py",
                "assinatura": assinatura(dias),
                "dias": dias,
            }
            arq = caminho_mes(intervalo, mes)
            os.makedirs(os.path.dirname(arq), exist_ok=True)
            if os.path.exists(arq):
                with open(arq, encoding="utf-8") as f:
                    if json.load(f).get("assinatura") == doc["assinatura"]:
                        continue
            with open(arq, "w", encoding="utf-8") as f:
                json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
            gravados.append(arq)
        return gravados


def meses_existentes(intervalo):
    pasta = os.path.join(DIR_DADOS, f"{intervalo}m")
    if not os.path.isdir(pasta):
        return []
    return sorted(n[:-5] for n in os.listdir(pasta) if n.endswith(".json"))


def ler_indice():
    if not os.path.exists(INDICE):
        return None
    try:
        with open(INDICE, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        log(f"  índice ilegível ({e}) — será reconstruído", erro=True)
        return None


# ------------------------------------------------------------------
# Decisão de gravação de um pregão
# ------------------------------------------------------------------
def decidir(antigo_plano, novas):
    """'novo' | 'igual' | 'completa' | 'ajustado' | 'menor'"""
    if not antigo_plano:
        return "novo"
    antigas = decodificar(antigo_plano)
    if antigas == novas:
        return "igual"
    fech_ant = {b[0]: b[4] for b in antigas}
    razoes = [b[4] / fech_ant[b[0]] for b in novas if b[0] in fech_ant and fech_ant[b[0]] > 0]
    if razoes and abs(median(razoes) - 1) > 0.01:
        return "ajustado"
    if len(novas) >= len(antigas):
        return "completa"
    return "menor"


# ------------------------------------------------------------------
# Universo
# ------------------------------------------------------------------
def media_aparada(valores, descarte=0.10):
    """Média descartando os 10% maiores — a mesma regra do piso de liquidez."""
    v = sorted(valores)
    k = int(len(v) * descarte)
    v = v[:len(v) - k] if k else v
    return sum(v) / len(v) if v else 0.0


def baixar_overnight():
    try:
        if os.path.exists(OVERNIGHT_URL):
            with open(OVERNIGHT_URL, encoding="utf-8") as f:
                return json.load(f)
        return _get_json(OVERNIGHT_URL, timeout=120)
    except Exception as e:
        log(f"  base do overnight inacessível ({e})", erro=True)
        return None


def ler_ajustes_universo():
    incluir, excluir = set(), set()
    if os.path.exists(UNIVERSO_TXT):
        with open(UNIVERSO_TXT, encoding="utf-8") as f:
            for linha in f:
                linha = linha.split("#")[0].strip().upper()
                if linha.startswith("+") and len(linha) > 1:
                    incluir.add(linha[1:].strip())
                elif linha.startswith("-") and len(linha) > 1:
                    excluir.add(linha[1:].strip())
    return incluir, excluir


def montar_universo(overnight, indice_ant, vol_min_mm):
    incluir, excluir = ler_ajustes_universo()
    origem = None
    ativos = []
    if overnight and overnight.get("dados"):
        ult = overnight.get("ultimo_pregao") or max(a[-1][0] for a in overnight["dados"].values())
        corte = (date.fromisoformat(ult) - timedelta(days=7)).isoformat()
        for t, linhas in overnight["dados"].items():
            if len(linhas) < 20 or linhas[-1][0] < corte:
                continue
            if media_aparada([l[5] for l in linhas[-20:]]) >= vol_min_mm * 1e6:
                ativos.append(t)
        origem = f"COTAHIST do overnight ({ult[8:10]}/{ult[5:7]}/{ult[:4]})"
    elif indice_ant and indice_ant.get("universo", {}).get("ativos"):
        ativos = [t for t in indice_ant["universo"]["ativos"] if t not in ESPECIAIS]
        origem = "índice anterior (base do overnight inacessível)"
    else:
        ativos = list(UNIVERSO_SEMENTE)
        origem = "lista semente (base do overnight inacessível)"
    final = sorted((set(ativos) | incluir | set(ESPECIAIS)) - excluir)
    return {
        "criterio": (f"média dos últimos 20 pregões, descartando os 10% de maior volume, "
                     f">= R$ {vol_min_mm:g} MM"),
        "vol_min_mm": vol_min_mm,
        "origem": origem,
        "incluidos_a_mao": sorted(incluir),
        "excluidos_a_mao": sorted(excluir),
        "especiais": {t: s for t, s in ESPECIAIS.items() if t in final},
        "ativos": final,
    }


# ------------------------------------------------------------------
# Cobertura, conferência e índice
# ------------------------------------------------------------------
def varrer_base(intervalo):
    """Relê os arquivos do disco (fonte de verdade) e resume a base."""
    meses, ativos, pregoes = [], {}, set()
    for mes in meses_existentes(intervalo):
        arq = caminho_mes(intervalo, mes)
        with open(arq, encoding="utf-8") as f:
            doc = json.load(f)
        dias = doc.get("dias", {})
        tickers_mes = set()
        for dia in sorted(dias):
            pregoes.add(dia)
            for t in dias[dia]:
                tickers_mes.add(t)
                a = ativos.setdefault(t, {"primeiro": dia, "ultimo": dia, "dias": 0})
                a["primeiro"] = min(a["primeiro"], dia)
                a["ultimo"] = max(a["ultimo"], dia)
                a["dias"] += 1
        meses.append({
            "mes": mes,
            "arquivo": f"{intervalo}m/{mes}.json",
            "assinatura": doc.get("assinatura") or assinatura(dias),
            "bytes": os.path.getsize(arq),
            "pregoes": len(dias),
            "ativos": len(tickers_mes),
        })
    ps = sorted(pregoes)
    return {
        "primeiro": ps[0] if ps else None,
        "ultimo": ps[-1] if ps else None,
        "pregoes": len(ps),
        "meses": meses,
        "ativos": {t: ativos[t] for t in sorted(ativos)},
    }


def conferir_cotahist(overnight, intervalo, n_pregoes=10):
    """Fechamento e quantidade do dia (somados dos candles) contra o COTAHIST.
    É o teste de integração com dado real que roda em toda coleta."""
    if not overnight or not overnight.get("dados"):
        return None
    oficiais = {}
    for t, linhas in overnight["dados"].items():
        for l in linhas[-(n_pregoes + 5):]:
            oficiais[(t, l[0])] = (l[4], l[6])
    datas = sorted({d for (_t, d) in oficiais})[-n_pregoes:]
    difs, razoes, piores = [], [], []
    for mes in sorted({d[:7] for d in datas}):
        arq = caminho_mes(intervalo, mes)
        if not os.path.exists(arq):
            continue
        with open(arq, encoding="utf-8") as f:
            dias = json.load(f).get("dias", {})
        for dia in datas:
            for t, plano in dias.get(dia, {}).items():
                of = oficiais.get((t, dia))
                if not of or not of[0]:
                    continue
                barras = decodificar(plano)
                fech = barras[-1][4] / 100
                dif = abs(fech / of[0] - 1) * 100
                difs.append(dif)
                qtd = sum(b[5] for b in barras)
                if of[1]:
                    razoes.append(qtd / of[1])
                piores.append((round(dif, 3), t, dia, fech, of[0]))
    if not difs:
        return None
    piores.sort(reverse=True)
    return {
        "pregoes_conferidos": datas,
        "comparacoes": len(difs),
        "fechamento_dif_mediana_pct": round(median(difs), 4),
        "fechamento_ate_0_5pct": round(sum(1 for d in difs if d <= 0.5) / len(difs), 4),
        "quantidade_razao_mediana": round(median(razoes), 4) if razoes else None,
        "piores": [{"ativo": t, "dia": d, "yahoo": y, "cotahist": o, "dif_pct": p}
                   for p, t, d, y, o in piores[:8] if p > 0.5],
    }


def montar_indice(indice_ant, universo, checado, execucao, conferencia):
    idx = {
        "formato": 1,
        "gerado_em": agora_br().isoformat(timespec="seconds"),
        "fonte": "Yahoo Finance (v8/chart) — candles do pregão regular",
        "repositorio": os.environ.get("GITHUB_REPOSITORY") or
                       (indice_ant or {}).get("repositorio"),
        "fuso": "America/Sao_Paulo (UTC-3)",
        "feriados": sorted(FERIADOS_B3),
        "fim_sessao": f"{FIM_SESSAO_MIN // 60:02d}:{FIM_SESSAO_MIN % 60:02d}",
        "universo": universo,
        "bases": {},
        "conferencia": conferencia,
        "execucao": execucao,
    }
    for iv in INTERVALOS:
        b = varrer_base(iv)
        b["checado"] = {t: checado[iv][t] for t in sorted(checado[iv])}
        idx["bases"][str(iv)] = b
    return idx


def indice_mudou(novo, antigo):
    if not antigo:
        return True
    ignorar = ("gerado_em", "execucao")
    a = {k: v for k, v in antigo.items() if k not in ignorar}
    b = {k: v for k, v in novo.items() if k not in ignorar}
    return a != b


# ------------------------------------------------------------------
# Coleta
# ------------------------------------------------------------------
def escolher_range(intervalo, referencia, hoje: date, completo: bool):
    """Menor janela que cobre o buraco desde a última data conhecida."""
    if completo or not referencia:
        return RANGE_COMPLETO[intervalo]
    buraco = (hoje - date.fromisoformat(referencia)).days
    if buraco <= 4:
        return "5d"
    if buraco <= 27:
        return "1mo"
    if intervalo == 5:
        return "60d"
    if buraco <= 85:
        return "3mo"
    if buraco <= 175:
        return "6mo"
    if buraco <= 360:
        return "1y"
    return "730d"


def coletar(args):
    t0 = time.time()
    agora = agora_br()
    hoje = agora.date()
    esperado = ultimo_pregao_encerrado(agora).isoformat()
    log(f"Agora (Brasília): {agora:%d/%m/%Y %H:%M} — último pregão encerrado: {esperado}")

    indice_ant = ler_indice()
    overnight = baixar_overnight()
    universo = montar_universo(overnight, indice_ant, args.vol_min)
    log(f"Universo: {len(universo['ativos'])} ativos — {universo['origem']} "
        f"(+ referências: {', '.join(universo['especiais'])})")

    alvo = universo["ativos"]
    if args.ativos:
        alvo = sorted({a.strip().upper() for a in args.ativos.split(",") if a.strip()})
        log(f"Restrito a: {', '.join(alvo)}")

    checado = {iv: dict(((indice_ant or {}).get("bases", {}).get(str(iv), {})
                         .get("checado") or {})) for iv in INTERVALOS}
    cobertura_ant = {iv: ((indice_ant or {}).get("bases", {}).get(str(iv), {})
                          .get("ativos") or {}) for iv in INTERVALOS}

    loja = Loja()
    coletor = Coletor(calendario_b3(overnight))
    contagem = {k: 0 for k in ("novo", "completa", "igual", "ajustado", "menor",
                               "em_andamento", "derivado_60", "coberto_por_5m")}
    falhas = []
    tempo_limite = time.time() + args.limite_minutos * 60

    for n, ticker in enumerate(alvo, 1):
        for iv in INTERVALOS:
            if time.time() > tempo_limite:
                falhas.append(f"{ticker} {iv}m: limite de tempo da execução")
                continue
            ultimo = (cobertura_ant[iv].get(ticker) or {}).get("ultimo")
            ref = max(filter(None, [ultimo, checado[iv].get(ticker)]), default=None)
            # 60 min: depois da carga inicial, vem somado dos candles de 5 min.
            # Só volta a consultar o Yahoo se o buraco passou do que os 5 min
            # ainda conseguem cobrir (a janela de 60 dias do Yahoo).
            if (iv == 60 and ref and not args.completo
                    and (hoje - date.fromisoformat(ref)).days <= 50):
                continue
            if ref and ref >= esperado and not args.completo:
                continue
            rng = escolher_range(iv, ref, hoje, args.completo)
            try:
                try:
                    dias = coletor.buscar(ticker, iv, rng)
                except SemDados as e:
                    if rng != RANGE_COMPLETO[iv]:
                        raise
                    log(f"  {ticker} {iv}m: {e} — tentando {RANGE_COMPLETO_RESERVA[iv]}")
                    dias = coletor.buscar(ticker, iv, RANGE_COMPLETO_RESERVA[iv])
            except SemDados as e:
                falhas.append(f"{ticker} {iv}m: {e}")
                checado[iv][ticker] = esperado
                continue
            except Bloqueio as e:
                falhas.append(f"{ticker} {iv}m: {e}")
                continue

            gravou = 0
            for dia in sorted(dias):
                if not sessao_encerrada(dia, agora):
                    contagem["em_andamento"] += 1
                    continue
                if iv == 60 and loja.ler(5, dia, ticker):
                    # pregão que tem 5 min: o de 60 min é a soma deles, não o
                    # do Yahoo — assim as duas bases nunca divergem
                    contagem["coberto_por_5m"] += 1
                    continue
                barras = dias[dia]
                decisao = decidir(loja.ler(iv, dia, ticker), barras)
                contagem[decisao] += 1
                if decisao in ("novo", "completa"):
                    loja.gravar(iv, dia, ticker, codificar(barras))
                    gravou += 1
                # pregão de 5 min que entrou/mudou alimenta a base de 60 min
                if iv == 5 and decisao in ("novo", "completa"):
                    agregado = agregar(barras, 60)
                    if decidir(loja.ler(60, dia, ticker), agregado) == "novo":
                        loja.gravar(60, dia, ticker, codificar(agregado))
                        contagem["derivado_60"] += 1
            checado[iv][ticker] = esperado
            # a base de 60 min deste papel acompanha a de 5 min (pregão
            # sem negócio conta como conferido nas duas)
            if iv == 5 and (cobertura_ant[60].get(ticker) or checado[60].get(ticker)):
                checado[60][ticker] = max(checado[60].get(ticker) or "", esperado)
            if gravou:
                log(f"  [{n:>3}/{len(alvo)}] {ticker:<7} {iv:>2}m {rng:>5}: "
                    f"{gravou} pregão(ões) gravado(s)")

    gravados = loja.salvar()
    execucao = {
        "inicio": agora.isoformat(timespec="seconds"),
        "duracao_s": round(time.time() - t0),
        "modo": ("completo" if args.completo else
                 "carga inicial" if not indice_ant else "incremental"),
        "acesso": coletor.modo,
        "consultas": coletor.consultas,
        "pregoes": contagem,
        "arquivos": [os.path.relpath(g, DIR_DADOS) for g in gravados],
        "falhas": falhas[:60],
        "total_falhas": len(falhas),
    }
    conferencia = {str(iv): conferir_cotahist(overnight, iv) for iv in INTERVALOS}
    indice = montar_indice(indice_ant, universo, checado, execucao, conferencia)
    if gravados or indice_mudou(indice, indice_ant):
        os.makedirs(DIR_DADOS, exist_ok=True)
        with open(INDICE, "w", encoding="utf-8") as f:
            json.dump(indice, f, ensure_ascii=False, separators=(",", ":"))
        log(f"\nÍndice gravado ({len(gravados)} arquivo(s) de candles alterado(s)).")
    else:
        log("\nNada mudou na base — nenhum arquivo reescrito.")

    log(f"Consultas ao Yahoo: {coletor.consultas} (acesso {coletor.modo}) — "
        f"{time.time() - t0:.0f}s")
    log("Pregões: " + ", ".join(f"{k}={v}" for k, v in contagem.items() if v))
    if falhas:
        log(f"{len(falhas)} falha(s):", erro=True)
        for f_ in falhas[:30]:
            log(f"   - {f_}", erro=True)
    for iv in INTERVALOS:
        b = indice["bases"][str(iv)]
        log(f"Base {iv:>2} min: {b['primeiro']} → {b['ultimo']} · {b['pregoes']} pregões · "
            f"{len(b['ativos'])} ativos")
    c5 = conferencia.get("5")
    if c5:
        log(f"Conferência 5 min x COTAHIST: {c5['comparacoes']} papel-dia, "
            f"{c5['fechamento_ate_0_5pct'] * 100:.1f}% com fechamento a até 0,5% do oficial")
    return 0


# ------------------------------------------------------------------
# Verificação — o ÚNICO lugar que decide verde ou vermelho
# ------------------------------------------------------------------
def verificar() -> int:
    agora = agora_br()
    esperado = ultimo_pregao_encerrado(agora)
    fim = datetime(esperado.year, esperado.month, esperado.day,
                   FIM_SESSAO_MIN // 60, FIM_SESSAO_MIN % 60, tzinfo=FUSO_BR)
    limite = fim + timedelta(hours=HORAS_TOLERANCIA)
    idx = ler_indice()
    if not idx:
        log(f"::error::{INDICE} não existe — a coleta nunca gravou nada.", erro=True)
        return 1

    universo = idx.get("universo", {}).get("ativos") or []
    linhas, problemas = [], []
    for iv in INTERVALOS:
        b = idx.get("bases", {}).get(str(iv), {})
        ativos, checado = b.get("ativos", {}), b.get("checado", {})
        em_dia = [t for t in universo
                  if max(filter(None, [(ativos.get(t) or {}).get("ultimo"), checado.get(t)]),
                         default="") >= esperado.isoformat()]
        cob = len(em_dia) / len(universo) if universo else 0
        linhas.append(f"- base {iv} min: `{b.get('primeiro')}` → `{b.get('ultimo')}` · "
                      f"{b.get('pregoes', 0)} pregões · cobertura do último pregão: "
                      f"`{cob * 100:.0f}%` ({len(em_dia)}/{len(universo)})")
        if (b.get("ultimo") or "") < esperado.isoformat() or cob < COBERTURA_MINIMA:
            problemas.append(iv)

    estourou = agora > limite
    if not problemas:
        veredito = "✅ Base em dia."
    elif estourou:
        veredito = f"🔴 **BASE ATRASADA** — o prazo (`{limite:%d/%m %H:%M}`) já passou."
    else:
        veredito = f"🟡 Aguardando a próxima janela. Vira falha depois de `{limite:%d/%m %H:%M}`."

    ex = idx.get("execucao") or {}
    conf = (idx.get("conferencia") or {}).get("5") or {}
    resumo = [
        "### Coleta intraday",
        "",
        f"- verificada em: `{agora:%d/%m/%Y %H:%M}` (Brasília)",
        f"- último pregão esperado: `{esperado.isoformat()}`",
        *linhas,
        f"- última gravação: `{idx.get('gerado_em')}` · consultas: `{ex.get('consultas')}` · "
        f"acesso: `{ex.get('acesso')}` · falhas: `{ex.get('total_falhas')}`",
    ]
    if conf:
        resumo.append(f"- conferência com o COTAHIST: `{conf.get('comparacoes')}` papel-dia, "
                      f"`{conf.get('fechamento_ate_0_5pct', 0) * 100:.1f}%` com fechamento a até "
                      f"0,5% do oficial")
    resumo += ["", veredito]
    destino = os.environ.get("GITHUB_STEP_SUMMARY")
    if destino:
        with open(destino, "a", encoding="utf-8") as fh:
            fh.write("\n".join(resumo) + "\n")
    log("\n".join(resumo))

    if not problemas:
        return 0
    if estourou:
        log(f"::error::base atrasada (esperado {esperado.isoformat()}). Veja as falhas no "
            f"passo 'Executar coleta'. Se aparecer bloqueio do Yahoo, configure URL_APP.",
            erro=True)
        return 1
    log("::warning::base ainda sem o último pregão — as próximas janelas tentam de novo.",
        erro=True)
    return 0


# ------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ativos", help="lista separada por vírgula (padrão: universo inteiro)")
    ap.add_argument("--completo", action="store_true",
                    help="rebaixa tudo que o Yahoo tem (60 dias em 5 min, 730 dias em 60 min)")
    ap.add_argument("--vol-min", type=float, default=5.0,
                    help="universo: média aparada de 20 pregões em R$ milhões (padrão 5)")
    ap.add_argument("--limite-minutos", type=float, default=40.0)
    ap.add_argument("--verificar", action="store_true")
    args = ap.parse_args()
    if args.verificar:
        sys.exit(verificar())
    sys.exit(coletar(args))


if __name__ == "__main__":
    main()
