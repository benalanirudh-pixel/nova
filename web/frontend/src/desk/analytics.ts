import { isNum } from "../lib/format";
import type { FnoDesk } from "../lib/types";

/** Date, open, high, low, close, volume. */
export type Bar = [string, number, number, number, number, number];

const avg = (a: number[]) => a.reduce((p, c) => p + c, 0) / a.length;
export const sd = (a: number[]) => {
  const m = avg(a);
  return Math.sqrt(a.reduce((p, x) => p + (x - m) ** 2, 0) / (a.length - 1));
};
const emaSeries = (a: number[], n: number) => {
  const k = 2 / (n + 1);
  let e = a[0];
  return a.map((v) => (e = v * k + e * (1 - k)));
};
const logReturns = (c: Bar[]) => c.slice(1).map((r, i) => Math.log(r[4] / c[i][4]));
const byDate = (c: Bar[]) => Object.fromEntries(logReturns(c).map((v, i) => [c[i + 1][0], v]));

/** Keep the last close aligned with the live quote: replace today's bar, or append it if history ends earlier. */
export function withQuote(c: Bar[], date: string | null, q: { px?: number | null; o?: number | null; h?: number | null; l?: number | null }): Bar[] {
  if (!c.length || !isNum(q.px) || !date) return c;
  const px = q.px, last = c[c.length - 1];
  if (last[0] === date) {
    return [...c.slice(0, -1), [date, last[1], Math.max(last[2], q.h ?? 0, px), Math.min(last[3], q.l ?? Infinity, px), px, last[5]]];
  }
  return last[0] < date ? [...c, [date, q.o ?? px, q.h ?? px, q.l ?? px, px, 0]] : c;
}

export type Risk = NonNullable<ReturnType<typeof risk>>;

/** Trend, volatility and relative measures from daily bars. `base` is Nifty for beta; null for Nifty itself. */
export function risk(c: Bar[] | undefined, px: number | null | undefined, base: Bar[] | null) {
  if (!c || c.length < 40 || !isNum(px)) return null;
  const n = c.length, cl = c.map((b) => b[4]), r = logReturns(c);
  const e9 = emaSeries(cl, 9), e20 = emaSeries(cl, 20), e50 = emaSeries(cl, 50);
  const fast = emaSeries(cl, 12), slow = emaSeries(cl, 26), macd = fast.map((v, i) => v - slow[i]), signal = emaSeries(macd, 9);
  const tr = c.slice(1).map((b, i) => Math.max(b[2] - b[3], Math.abs(b[2] - c[i][4]), Math.abs(b[3] - c[i][4])));
  const atr = avg(tr.slice(-14));
  const ret = (k: number) => (n > k ? (px / cl[n - 1 - k] - 1) * 100 : null);
  const hi = (k: number) => Math.max(...c.slice(-k).map((b) => b[2]));
  const lo = (k: number) => Math.min(...c.slice(-k).map((b) => b[3]));
  let peak = -Infinity, mdd = 0;
  for (const v of cl) { peak = Math.max(peak, v); mdd = Math.min(mdd, v / peak - 1); }
  const top = hi(n), since = n - 1 - c.map((b) => b[2]).lastIndexOf(top);
  const last60 = r.slice(-60).map((x) => (Math.exp(x) - 1) * 100);

  let beta: number | null = null, corr: number | null = null, alpha: number | null = null, pairs = 0;
  if (base) {
    const b = byDate(base);
    const p = Object.entries(byDate(c)).filter(([d]) => b[d] != null).slice(-60).map(([d, v]) => [v, b[d]]);
    pairs = p.length;
    if (p.length >= 30) {
      const a = p.map((x) => x[0]), m = p.map((x) => x[1]), ma = avg(a), mb = avg(m);
      const cv = a.reduce((s, x, i) => s + (x - ma) * (m[i] - mb), 0) / (a.length - 1);
      beta = cv / sd(m) ** 2;
      corr = cv / (sd(a) * sd(m));
      alpha = (a.reduce((s, x) => s + x, 0) - beta * m.reduce((s, x) => s + x, 0)) * 100;
    }
  }
  const last20 = c.slice(-20), volOf = (f: (b: Bar) => boolean) => last20.filter(f).reduce((s, b) => s + b[5], 0);
  const up = volOf((b) => b[4] >= b[1]), dn = volOf((b) => b[4] < b[1]);
  const prev = c[n - 2], pp = (prev[2] + prev[3] + prev[4]) / 3;
  let above = 0;
  for (let i = n - 1; i >= 0 && cl[i] > e20[i]; i--) above++;
  return {
    atr, atrPct: (atr / px) * 100, rv20: sd(r.slice(-20)) * Math.sqrt(252) * 100, rv60: sd(r.slice(-60)) * Math.sqrt(252) * 100,
    ret, hi, lo, maxDrawdown: mdd * 100, fromHigh: (px / top - 1) * 100, sinceHigh: since, best: Math.max(...last60), worst: Math.min(...last60),
    upDays: (last60.filter((x) => x > 0).length / last60.length) * 100, beta, corr, alpha, pairs,
    e9: e9[n - 1], e20: e20[n - 1], e50: e50[n - 1], slope20: (e20[n - 1] / e20[n - 6] - 1) * 100, slope50: (e50[n - 1] / e50[n - 6] - 1) * 100,
    hist: macd[n - 1] - signal[n - 1], upDown: dn ? up / dn : null, vol5: avg(c.slice(-5).map((b) => b[5])), vol20: avg(last20.map((b) => b[5])),
    streak: above, gap: (c[n - 1][1] / prev[4] - 1) * 100,
    pp, r1: 2 * pp - prev[3], s1: 2 * pp - prev[2], r2: pp + prev[2] - prev[3], s2: pp - prev[2] + prev[3], prevHigh: prev[2], prevLow: prev[3],
  };
}

const phi = (x: number) => Math.exp((-x * x) / 2) / Math.sqrt(2 * Math.PI);
export const normCdf = (x: number) => {
  const t = 1 / (1 + 0.2316419 * Math.abs(x));
  const y = phi(x) * t * (0.31938153 + t * (-0.356563782 + t * (1.781477937 + t * (-1.821255978 + t * 1.330274429))));
  return x >= 0 ? 1 - y : y;
};

export type FnoRow = NonNullable<FnoDesk["metrics"]>["profile"][number] & { dc: number; dp: number; net: number; gp: number };
export type Fno = NonNullable<ReturnType<typeof analyzeChain>>;

/** Black-Scholes on the put-call parity forward, no dividend term. Model output, shown as such. */
export function analyzeChain(C: FnoDesk | null | undefined) {
  const M = C?.metrics;
  if (!C || !M || !isNum(C.spot) || !isNum(M.atm_iv) || M.atm_iv <= 0) return null;
  const R = [...M.profile].sort((a, b) => a.strike - b.strike);
  if (!R.length) return null;
  const spot = C.spot, atmIv = M.atm_iv, T = Math.max(M.days_to_expiry ?? 0, 0.5) / 365, st = Math.sqrt(T), sig = atmIv / 100;
  const at = R.find((r) => r.strike === M.atm) ?? R[R.length >> 1];
  const fwd = (at.call_ltp ?? 0) > 0 && (at.put_ltp ?? 0) > 0 ? at.call_ltp! - at.put_ltp! + at.strike : spot;
  const d1 = (K: number, s: number) => (Math.log(fwd / K) + 0.5 * s * s * T) / (s * st);
  const vol = (iv: number | null) => ((iv ?? 0) > 0 ? iv! : atmIv) / 100;
  const gamma = (K: number, iv: number | null) => { const s = vol(iv); return phi(d1(K, s)) / (fwd * s * st); };
  const rows: FnoRow[] = R.map((r) => {
    const net = gamma(r.strike, r.call_iv) * (r.call_oi ?? 0) - gamma(r.strike, r.put_iv) * (r.put_oi ?? 0);
    const dc = normCdf(d1(r.strike, vol(r.call_iv))), dp = normCdf(d1(r.strike, vol(r.put_iv))) - 1;
    return { ...r, dc, dp, net, gp: 0 };
  });
  const total = rows.reduce((p, r) => p + Math.abs(r.net), 0) || 1, sum = rows.reduce((p, r) => p + r.net, 0);
  let run = 0, flip: number | null = null;
  rows.forEach((r, i) => {
    r.gp = (r.net / total) * 100;
    const was = run;
    run += r.net;
    if (i && was * run < 0 && flip == null) flip = r.strike;
  });
  const near = (k: number) => rows.reduce((a, b) => (Math.abs(b.strike - k) < Math.abs(a.strike - k) ? b : a));
  const band = (lo: number, hi: number) => {
    const p = rows.filter((r) => { const d = Math.abs(r.strike / spot - 1) * 100; return d >= lo && d < hi; });
    const c = p.reduce((s, r) => s + (r.call_oi ?? 0), 0), u = p.reduce((s, r) => s + (r.put_oi ?? 0), 0);
    return { c, u, pcr: c ? u / c : null };
  };
  const smile = [-3, -2, -1, 0, 1, 2, 3].map((m) => {
    const r = near(spot * (1 + m / 100)), iv = m < 0 ? r.put_iv : m > 0 ? r.call_iv : atmIv;
    return { m, k: r.strike, iv, spread: (iv ?? 0) > 0 ? iv! - atmIv : null };
  });
  const topBy = (k: "call_oi" | "put_oi") => [...rows].sort((a, b) => (b[k] ?? 0) - (a[k] ?? 0)).slice(0, 4);
  const basis = fwd - spot;
  return {
    rows, fwd, basis, carry: (basis / spot / T) * 100, above: (K: number) => normCdf(d1(K, sig) - sig * st) * 100, zOf: (K: number) => Math.log(K / fwd) / (sig * st),
    flip: flip as number | null, netPct: (sum / total) * 100, callHeavy: sum >= 0, band, smile, topC: topBy("call_oi"), topP: topBy("put_oi"),
    dayMove: (spot * sig) / Math.sqrt(252), sigmaMove: spot * sig * st,
  };
}
