/**
 * PREGÃO AO VIVO — candles intradiários pelo Yahoo Finance
 * ============================================================
 * O navegador não pode chamar o Yahoo direto (CORS). Esta função roda
 * no Netlify, busca e devolve os candles já no formato compacto da base
 * (o mesmo de coleta_intraday.py), para o app juntar com o histórico.
 *
 * Uso:
 *   /.netlify/functions/aovivo?t=PETR4                       pregão de hoje, 5 min
 *   /.netlify/functions/aovivo?t=PETR4,VALE3&range=5d        últimos pregões
 *   /.netlify/functions/aovivo?t=PETR4&intervalo=60&range=730d
 *
 * O Yahoo entrega a B3 com ATRASO DE 15 MINUTOS (fonte: tabela de bolsas
 * do próprio Yahoo). "Ao vivo" aqui = pregão em andamento, 15 min atrás.
 *
 * Usa só o v8/chart, que não exige cookie/crumb. Também é a RESERVA da
 * coleta noturna: se o Yahoo recusar os IPs do GitHub, o coletor chama
 * esta função (variável URL_APP no repositório).
 */

const HOSTS = (process.env.YAHOO_BASE ||
  "https://query1.finance.yahoo.com,https://query2.finance.yahoo.com").split(",");
const UA =
  "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36";
const MAX_TICKERS = 60;
const PARALELO = 6;
const RANGES = {
  5: ["1d", "5d", "1mo", "59d", "60d"],
  60: ["1d", "5d", "1mo", "3mo", "6mo", "1y", "729d", "730d"],
};
const ABERTURA = 600;

class SemDados extends Error {}

const mod = (a, n) => ((a % n) + n) % n;

/** Mesmas regras de parse_yahoo() do coletor. */
export function parseYahoo(js, iv) {
  const chart = js?.chart || {};
  if (chart.error) throw new SemDados(chart.error.description || String(chart.error.code || "erro"));
  const res = chart.result?.[0];
  if (!res) throw new SemDados("resposta vazia");
  const meta = res.meta || {};
  const off = Number.isFinite(meta.gmtoffset) ? meta.gmtoffset : -10800;
  const ts = res.timestamp || [];
  const q = res.indicators?.quote?.[0] || {};
  const porDia = {};
  for (let i = 0; i < ts.length; i++) {
    let [o, h, l, c] = [q.open?.[i], q.high?.[i], q.low?.[i], q.close?.[i]];
    const v = q.volume?.[i] || 0;
    if ([o, h, l, c].some((x) => x == null || !(x > 0))) continue;
    [o, h, l, c] = [o, h, l, c].map((x) => Math.round(x * 100));
    h = Math.max(h, o, c);
    l = Math.min(l, o, c);
    const local = new Date((ts[i] + off) * 1000);
    const dia = local.toISOString().slice(0, 10);
    const m = local.getUTCHours() * 60 + local.getUTCMinutes();
    const alinhado = m - mod(m - ABERTURA, iv);
    (porDia[dia] ||= []).push([alinhado, alinhado === m, o, h, l, c, Math.round(v)]);
  }
  const dias = {};
  for (const [dia, linhas] of Object.entries(porDia)) {
    const slots = new Map();
    for (const [m, naGrade, o, h, l, c, v] of linhas) {
      if (slots.has(m) && !naGrade) continue;
      slots.set(m, [m, o, h, l, c, v]);
    }
    const barras = [];
    for (const m of [...slots.keys()].sort((a, b) => a - b)) {
      const b = slots.get(m);
      const u = barras[barras.length - 1];
      if (u && b[5] === 0 && b[1] === b[2] && b[2] === b[3] && b[3] === b[4] && b[4] === u[4]) continue;
      barras.push(b);
    }
    if (barras.length) dias[dia] = barras;
  }
  return { dias, meta };
}

export function codificar(barras) {
  if (!barras.length) return [];
  const [m0, p0] = barras[0];
  const out = [m0, p0];
  let rm = m0;
  let rp = p0;
  for (const [m, o, h, l, c, v] of barras) {
    out.push(m - rm, o - rp, h - rp, l - rp, c - rp, v);
    rm = m;
    rp = c;
  }
  return out;
}

async function buscar(ticker, iv, rng) {
  let ultimo = null;
  for (let t = 0; t < 3; t++) {
    const host = HOSTS[t % HOSTS.length].replace(/\/$/, "");
    const url = `${host}/v8/finance/chart/${encodeURIComponent(ticker + ".SA")}` +
      `?interval=${iv}m&range=${rng}&includePrePost=false&events=`;
    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), 12000);
    try {
      const r = await fetch(url, {
        headers: { "User-Agent": UA, Accept: "application/json" },
        signal: ctrl.signal,
      });
      if (r.status === 404) throw new SemDados("Yahoo não tem esse papel (404)");
      if (r.status === 400 || r.status === 422) throw new SemDados(`range recusado (${r.status})`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return parseYahoo(await r.json(), iv);
    } catch (e) {
      if (e instanceof SemDados) throw e;
      ultimo = e;
      await new Promise((ok) => setTimeout(ok, t === 0 ? 400 : 1500));
    } finally {
      clearTimeout(timer);
    }
  }
  throw ultimo;
}

export default async (req) => {
  const url = new URL(req.url);
  const tickers = [...new Set((url.searchParams.get("t") || url.searchParams.get("tickers") || "")
    .split(",").map((x) => x.trim().toUpperCase().replace(/\.SA$/, "")).filter((x) => /^[A-Z0-9]{4,8}$/.test(x)))];
  const iv = Number(url.searchParams.get("intervalo") || 5);
  const rng = url.searchParams.get("range") || "1d";
  const erro = (msg) => Response.json({ erro: msg }, { status: 400, headers: { "Access-Control-Allow-Origin": "*" } });
  if (!tickers.length) return erro("Informe ?t=PETR4 (ou vários: ?t=PETR4,VALE3)");
  if (tickers.length > MAX_TICKERS) return erro(`No máximo ${MAX_TICKERS} papéis por chamada`);
  if (!RANGES[iv]) return erro("intervalo deve ser 5 ou 60");
  if (!RANGES[iv].includes(rng)) return erro(`range para ${iv} min: ${RANGES[iv].join(", ")}`);

  const dados = {};
  const falhas = [];
  const fila = [...tickers];
  const agora = Date.now() / 1000;
  await Promise.all(Array.from({ length: Math.min(PARALELO, fila.length) }, async () => {
    while (fila.length) {
      const t = fila.shift();
      try {
        const { dias, meta } = await buscar(t, iv, rng);
        const reg = meta.currentTradingPeriod?.regular || {};
        dados[t] = {
          dias: Object.fromEntries(Object.entries(dias).map(([d, b]) => [d, codificar(b)])),
          preco: meta.regularMarketPrice ?? null,
          fechamentoAnterior: meta.chartPreviousClose ?? meta.previousClose ?? null,
          atualizadoEm: meta.regularMarketTime ? new Date(meta.regularMarketTime * 1000).toISOString() : null,
          pregaoAberto: reg.start && reg.end ? agora >= reg.start && agora < reg.end : null,
        };
      } catch (e) {
        falhas.push(`${t}: ${e.message}`);
      }
    }
  }));

  return Response.json(
    {
      consultadoEm: new Date().toISOString(),
      fonte: "Yahoo Finance v8/chart",
      atrasoMin: 15,
      intervalo: iv,
      range: rng,
      dados,
      ausentes: tickers.filter((t) => !dados[t]),
      falhas,
    },
    {
      headers: {
        "Access-Control-Allow-Origin": "*",
        "Cache-Control": rng === "1d" ? "public, max-age=30" : "public, max-age=300",
      },
    },
  );
};
