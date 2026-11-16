# Step 26: run from the project root (the folder that contains backend and frontend).
$ErrorActionPreference = 'Stop'

@'
"""Pure helpers for the sentiment distribution and star-gap views."""

LABELS = ("pos", "neu", "neg")
GAP_BUCKETS = ["over by 2 or more", "over by 1 to 2", "over by 0.5 to 1", "within 0.5", "under by 0.5 to 1", "under by 1 to 2", "under by 2 or more"]


def fold(rows, keep: int | None = None) -> list[dict]:
    """rows of (key, label, count) -> one dict per key with counts and shares, biggest key first."""
    acc: dict = {}
    for key, label, n in rows:
        if label not in LABELS:
            continue
        d = acc.setdefault(key, {"key": key, "pos": 0, "neu": 0, "neg": 0})
        d[label] += int(n)
    out = []
    for d in acc.values():
        total = d["pos"] + d["neu"] + d["neg"]
        d["n"] = total
        for k in LABELS:
            d[k + "_share"] = round(d[k] / total, 3) if total else 0.0
        out.append(d)
    out.sort(key=lambda d: -d["n"])
    return out[:keep] if keep else out


def gap_bucket(gap: float) -> int:
    """Index into GAP_BUCKETS for gap = text-supported stars minus customer stars.
    Negative: the stars are higher than the words (over-rated). Positive: the words are happier (under-rated)."""
    level = 0 if abs(gap) < 0.5 else 1 if abs(gap) < 1 else 2 if abs(gap) < 2 else 3
    if level == 0:
        return 3
    return 3 + level if gap > 0 else 3 - level
'@ | Set-Content -Encoding ascii backend\app\services\distribution.py

@'
from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dashboard import FILT, _args, _f, _ws
from app.core import thresholds as T
from app.db.session import get_session
from app.services.distribution import GAP_BUCKETS, fold
from app.services.export_csv import short_model

router = APIRouter(tags=["distribution"])

SCORED = """FROM review r JOIN product p ON p.product_id = r.product_id
            JOIN review_score s ON s.review_id = r.review_id
            WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND s.text_label IS NOT NULL""" + FILT


@router.get("/sentiment-distribution")
async def sentiment_distribution(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                                 session: AsyncSession = Depends(get_session)):
    """How many reviews are positive, neutral and negative: overall, by star level, product, aspect and language."""
    a = _args(await _ws(session), product, date_from, date_to)
    ex = session.execute
    overall = (await ex(text(f"SELECT 'all', s.text_label, count(*) {SCORED} GROUP BY 2"), a)).all()
    by_star = (await ex(text(f"""SELECT round(r.rating_norm::numeric)::int, s.text_label, count(*) {SCORED}
                                 AND r.rating_norm IS NOT NULL GROUP BY 1, 2"""), a)).all()
    by_product = (await ex(text(f"SELECT p.name, s.text_label, count(*) {SCORED} GROUP BY 1, 2"), a)).all()
    by_lang = (await ex(text(f"SELECT coalesce(r.language, 'unknown'), s.text_label, count(*) {SCORED} GROUP BY 1, 2"), a)).all()
    asp = dict(a, conf=T.ASPECT_MIN_CONF, thr=-T.NEG_MENTION)
    by_aspect = (await ex(text("""
        SELECT x.name, CASE WHEN ra.sentiment >= :thr THEN 'pos' WHEN ra.sentiment <= -:thr THEN 'neg' ELSE 'neu' END, count(*)
        FROM review_aspect ra JOIN aspect x ON x.aspect_id = ra.aspect_id
        JOIN review r ON r.review_id = ra.review_id JOIN product p ON p.product_id = r.product_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND ra.confidence >= :conf""" + FILT + " GROUP BY 1, 2"), asp)).all()
    tot = fold(overall)
    n = tot[0]["n"] if tot else 0
    stars = {d["key"]: d for d in fold(by_star)}
    return {
        "n": n, "low_sample": n < T.LOW_SAMPLE,
        "overall": tot[0] if tot else None,
        "by_star": [stars.get(s, {"key": s, "pos": 0, "neu": 0, "neg": 0, "n": 0, "pos_share": 0, "neu_share": 0, "neg_share": 0}) for s in range(1, 6)],
        "by_product": fold(by_product, keep=15),
        "by_aspect": fold(by_aspect),
        "by_language": fold(by_lang),
        "note": "Review labels come from the weighted ensemble. Aspect counts are sentence mentions, so one review can appear in several aspects.",
    }


GAP_CASE = """CASE WHEN abs(s.fused_stars - r.rating_norm) < 0.5 THEN 3
       WHEN s.fused_stars > r.rating_norm THEN 3 + CASE WHEN abs(s.fused_stars - r.rating_norm) < 1 THEN 1
                                                        WHEN abs(s.fused_stars - r.rating_norm) < 2 THEN 2 ELSE 3 END
       ELSE 3 - CASE WHEN abs(s.fused_stars - r.rating_norm) < 1 THEN 1
                     WHEN abs(s.fused_stars - r.rating_norm) < 2 THEN 2 ELSE 3 END END"""


def _matrix(rows) -> list[list[int]]:
    m = [[0] * 5 for _ in range(5)]
    for act, other, n in rows:
        if act and other and 1 <= act <= 5 and 1 <= other <= 5:
            m[act - 1][other - 1] = int(n)
    return m


@router.get("/star-gap")
async def star_gap(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                   session: AsyncSession = Depends(get_session)):
    """Fused stars against customer stars. Gap = fused minus customer: above 0 is under-rated, below 0 is over-rated."""
    a = _args(await _ws(session), product, date_from, date_to)
    base = SCORED + " AND s.fused_stars IS NOT NULL AND r.rating_norm IS NOT NULL"
    n, mean, mabs, under, over = (await session.execute(text(f"""
        SELECT count(*), avg(s.fused_stars - r.rating_norm), avg(abs(s.fused_stars - r.rating_norm)),
               count(*) FILTER (WHERE s.mismatch_type = 'underrated'), count(*) FILTER (WHERE s.mismatch_type = 'overrated')
        {base}"""), a)).one()
    bk = dict((await session.execute(text(f"SELECT {GAP_CASE} AS b, count(*) {base} GROUP BY 1"), a)).all())
    per = (await session.execute(text(f"""
        SELECT round(r.rating_norm::numeric)::int, count(*), avg(r.rating_norm), avg(s.fused_stars),
               count(*) FILTER (WHERE s.mismatch_type = 'underrated'), count(*) FILTER (WHERE s.mismatch_type = 'overrated')
        {base} GROUP BY 1 ORDER BY 1"""), a)).all()
    fm = (await session.execute(text(f"""
        SELECT round(r.rating_norm::numeric)::int, round(s.fused_stars::numeric)::int, count(*) {base} GROUP BY 1, 2"""), a)).all()
    pm = (await session.execute(text(f"""
        SELECT round(r.rating_norm::numeric)::int, round(s.pred_stars::numeric)::int, count(*) {base} AND s.pred_stars IS NOT NULL GROUP BY 1, 2"""), a)).all()
    return {
        "n": n, "low_sample": n < T.LOW_SAMPLE, "mean_gap": _f(mean), "mean_abs_gap": _f(mabs),
        "underrated": under, "overrated": over,
        "buckets": [{"label": GAP_BUCKETS[i], "count": int(bk.get(i, 0))} for i in range(7)],
        "by_star": [{"stars": s, "reviews": c, "avg_actual": _f(x), "avg_fused": _f(f), "underrated": u, "overrated": o}
                    for s, c, x, f, u, o in per],
        "fused_matrix": _matrix(fm), "predicted_matrix": _matrix(pm),
        "predicted_n": sum(int(c) for _, _, c in pm),
        "note": "Rows are the customer's stars, columns are what the model says. Predicted stars are not available for Hindi and Hinglish.",
    }


@router.get("/model-comparison")
async def model_comparison(product: str | None = None, date_from: date | None = None, date_to: date | None = None,
                           session: AsyncSession = Depends(get_session)):
    """Each model's own votes next to the ensemble, and how often each agrees with the ensemble and with the stars."""
    a = _args(await _ws(session), product, date_from, date_to)
    star = "CASE WHEN round(r.rating_norm::numeric) >= 4 THEN 'pos' WHEN round(r.rating_norm::numeric) = 3 THEN 'neu' ELSE 'neg' END"
    vote = ("CASE WHEN p.p_neg >= p.p_neu AND p.p_neg >= p.p_pos THEN 'neg' "
            "WHEN p.p_neu > p.p_neg AND p.p_neu >= p.p_pos THEN 'neu' ELSE 'pos' END")
    rows = (await session.execute(text(f"""
        SELECT m.name, count(*),
               count(*) FILTER (WHERE {vote} = 'neg'), count(*) FILTER (WHERE {vote} = 'neu'), count(*) FILTER (WHERE {vote} = 'pos'),
               avg(p.expected_stars),
               count(*) FILTER (WHERE {vote} = s.text_label),
               count(*) FILTER (WHERE r.rating_norm IS NOT NULL), count(*) FILTER (WHERE r.rating_norm IS NOT NULL AND {vote} = {star})
        FROM prediction p JOIN model m ON m.model_id = p.model_id
        JOIN review r ON r.review_id = p.review_id JOIN product pr ON pr.product_id = r.product_id
        JOIN review_score s ON s.review_id = r.review_id
        WHERE r.workspace_id = :ws AND r.spam_score <= :spam AND s.text_label IS NOT NULL
          AND (CAST(:product AS text) IS NULL OR pr.name = CAST(:product AS text))
          AND (CAST(:d1 AS date) IS NULL OR r.review_date >= CAST(:d1 AS date))
          AND (CAST(:d2 AS date) IS NULL OR r.review_date <= CAST(:d2 AS date))
        GROUP BY m.model_id, m.name ORDER BY m.name"""), a)).all()
    ens = (await session.execute(text(f"""
        SELECT count(*), count(*) FILTER (WHERE s.text_label = 'neg'), count(*) FILTER (WHERE s.text_label = 'neu'),
               count(*) FILTER (WHERE s.text_label = 'pos'), count(*) FILTER (WHERE r.rating_norm IS NOT NULL),
               count(*) FILTER (WHERE r.rating_norm IS NOT NULL AND s.text_label = {star}) {SCORED}"""), a)).one()
    sh = lambda x, d: _f(x / d, 3) if d else None  # noqa: E731
    models = [{"model": short_model(n), "reviews": c, "neg": ng, "neu": nu, "pos": ps,
               "avg_expected_stars": _f(ex), "agree_with_ensemble": sh(ag, c), "agree_with_stars": sh(st_ok, st_n)}
              for n, c, ng, nu, ps, ex, ag, st_n, st_ok in rows]
    models.append({"model": "Ensemble (final)", "reviews": ens[0], "neg": ens[1], "neu": ens[2], "pos": ens[3],
                   "avg_expected_stars": None, "agree_with_ensemble": 1.0 if ens[0] else None, "agree_with_stars": sh(ens[5], ens[4])})
    return {"models": models, "note": "Agreement with stars is only a rough guide: stars are noisy, which is why gold labels decide the weights."}
'@ | Set-Content -Encoding ascii backend\app\api\distribution.py

@'
"""Offline checks for the distribution helpers. Run: python -m tests.check_distribution"""
from app.services.distribution import GAP_BUCKETS, fold, gap_bucket

assert [gap_bucket(g) for g in (-2.5, -2, -1.5, -1, -0.7, -0.5, -0.4, 0, 0.4, 0.5, 0.9, 1, 1.9, 2, 3)] == [0, 0, 1, 1, 2, 2, 3, 3, 3, 4, 4, 5, 5, 6, 6]
assert len(GAP_BUCKETS) == 7

rows = [(5, "pos", 8), (5, "neg", 2), (1, "neg", 3), (1, "neu", 1), (3, "weird", 9), (5, "neu", 0)]
out = fold(rows)
assert [d["key"] for d in out] == [5, 1]                # biggest first; the unknown label is ignored
assert out[0]["n"] == 10 and out[0]["pos_share"] == 0.8 and out[0]["neg_share"] == 0.2
assert out[1]["neg"] == 3 and out[1]["neu"] == 1 and out[1]["pos"] == 0
assert len(fold(rows, keep=1)) == 1
assert fold([]) == []
print("distribution checks passed")
'@ | Set-Content -Encoding ascii backend\tests\check_distribution.py

@'
import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api } from "./api";
import Chart from "./Chart";
import { filterQs, useFilters } from "./store";

type D = { key: string | number; pos: number; neu: number; neg: number; n: number; pos_share: number; neu_share: number; neg_share: number };
type Dist = { n: number; low_sample: boolean; overall: D | null; by_star: D[]; by_product: D[]; by_aspect: D[]; by_language: D[]; note: string };
type Gap = {
  n: number; low_sample: boolean; mean_gap: number | null; mean_abs_gap: number | null; underrated: number; overrated: number;
  buckets: { label: string; count: number }[];
  by_star: { stars: number; reviews: number; avg_actual: number | null; avg_fused: number | null; underrated: number; overrated: number }[];
  fused_matrix: number[][]; predicted_matrix: number[][]; predicted_n: number; note: string;
};
type Models = { models: { model: string; reviews: number; neg: number; neu: number; pos: number; avg_expected_stars: number | null;
  agree_with_ensemble: number | null; agree_with_stars: number | null }[]; note: string };

const POS = "#34d399", NEU = "#8a92a6", NEG = "#fb7185", UNDER = "#22d3ee", OVER = "#f5b83d";
const pct = (x: number | null | undefined) => (x == null ? "-" : Math.round(x * 100) + "%");
const cap = (s: string | number) => String(s).charAt(0).toUpperCase() + String(s).slice(1);

function stacked(rows: D[], horizontal: boolean, label = (k: string | number) => cap(k)) {
  const names = rows.map((r) => label(r.key));
  const mk = (name: string, k: "pos" | "neu" | "neg", color: string) => ({
    name, type: "bar", stack: "t", itemStyle: { color }, emphasis: { focus: "series" },
    data: rows.map((r) => Math.round(r[(k + "_share") as "pos_share"] * 1000) / 10),
  });
  const cat = { type: "category", data: names, inverse: horizontal, axisLabel: { width: 110, overflow: "truncate" } };
  const val = { type: "value", max: 100, axisLabel: { formatter: "{value}%" } };
  return {
    legend: { top: 0, textStyle: { color: "#a7aebf" } },
    grid: { left: horizontal ? 120 : 40, right: 16, top: 32, bottom: 28 },
    tooltip: {
      trigger: "axis", axisPointer: { type: "shadow" },
      formatter: (p: { dataIndex: number }[]) => {
        const r = rows[p[0].dataIndex];
        return `<b>${label(r.key)}</b> (${r.n} reviews)<br/>Positive ${r.pos} (${pct(r.pos_share)})<br/>Neutral ${r.neu} (${pct(r.neu_share)})<br/>Negative ${r.neg} (${pct(r.neg_share)})`;
      },
    },
    xAxis: horizontal ? val : cat, yAxis: horizontal ? cat : val,
    series: [mk("Positive", "pos", POS), mk("Neutral", "neu", NEU), mk("Negative", "neg", NEG)],
  };
}

function heat(m: number[][], title: string) {
  const data: number[][] = [];
  let max = 1;
  m.forEach((row, y) => row.forEach((v, x) => { data.push([x, y, v]); if (v > max) max = v; }));
  const lab = ["1", "2", "3", "4", "5"];
  return {
    title: { text: title, left: "center", textStyle: { fontSize: 13, color: "#c3c9d6" } },
    grid: { left: 56, right: 16, top: 36, bottom: 48 },
    tooltip: { formatter: (p: { value: number[] }) => `Customer ${lab[p.value[1]]} stars, model ${lab[p.value[0]]} stars: ${p.value[2]} reviews` },
    xAxis: { type: "category", data: lab, name: "Model says (stars)", nameLocation: "middle", nameGap: 28, splitArea: { show: true } },
    yAxis: { type: "category", data: lab, name: "Customer gave", nameLocation: "middle", nameGap: 36 },
    visualMap: { min: 0, max, show: false, inRange: { color: ["#171a22", "#8b7bff"] } },
    series: [{ type: "heatmap", data, label: { show: true, color: "#f2f4f8" } }],
  };
}

function Panel({ title, sub, children }: { title: string; sub?: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">{title}</h2>
      {sub && <p className="mb-2 text-xs text-slate-500">{sub}</p>}
      {children}
    </section>
  );
}

function Stat({ label, value, note, color }: { label: string; value: string; note?: string; color?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <div className="text-sm text-slate-500">{label}</div>
      <div className="mt-1 text-3xl font-semibold" style={{ color }}>{value}</div>
      {note && <div className="mt-1 text-xs text-slate-400">{note}</div>}
    </div>
  );
}

export default function Distribution() {
  const f = useFilters();
  const qs = filterQs(f);
  const dist = useQuery({ queryKey: ["sent-dist", qs], queryFn: () => api<Dist>("/sentiment-distribution" + qs) });
  const gap = useQuery({ queryKey: ["star-gap", qs], queryFn: () => api<Gap>("/star-gap" + qs) });
  const models = useQuery({ queryKey: ["model-comp", qs], queryFn: () => api<Models>("/model-comparison" + qs) });

  if (dist.isLoading || gap.isLoading) return <div className="p-8 text-slate-500">Loading...</div>;
  if (dist.error || gap.error || !dist.data || !gap.data) return <div className="p-8 text-red-600">Could not reach the API. Is uvicorn running on port 8010?</div>;
  const d = dist.data, g = gap.data;
  if (d.n === 0) {
    return (
      <div className="mx-auto max-w-xl p-10 text-center">
        <h2 className="text-2xl font-bold">No scored reviews yet</h2>
        <p className="mt-2 text-slate-500">Upload a file and run the analysis. This page shows who likes what and where the stars and the words disagree.</p>
        <Link to="/upload" className="mt-6 inline-block rounded-lg bg-gradient-to-r from-accent to-accent2 px-5 py-2.5 text-sm font-semibold text-slate-50">Upload reviews</Link>
      </div>
    );
  }
  const o = d.overall!;
  const donut = {
    tooltip: { trigger: "item" },
    legend: { bottom: 0, textStyle: { color: "#a7aebf" } },
    series: [{ type: "pie", radius: ["52%", "74%"], center: ["50%", "46%"], label: { color: "#c3c9d6", formatter: "{b}: {d}%" },
      data: [{ name: "Positive", value: o.pos, itemStyle: { color: POS } }, { name: "Neutral", value: o.neu, itemStyle: { color: NEU } }, { name: "Negative", value: o.neg, itemStyle: { color: NEG } }] }],
  };
  const gapBars = {
    grid: { left: 40, right: 10, top: 20, bottom: 56 },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: g.buckets.map((b) => b.label), axisLabel: { interval: 0, rotate: 28, fontSize: 11 } },
    yAxis: { type: "value" },
    series: [{ type: "bar", data: g.buckets.map((b, i) => ({ value: b.count, itemStyle: { color: i < 3 ? OVER : i === 3 ? NEU : UNDER } })) }],
  };
  const perStar = {
    grid: { left: 40, right: 10, top: 36, bottom: 28 },
    legend: { top: 0, textStyle: { color: "#a7aebf" } },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: g.by_star.map((b) => b.stars + " star") },
    yAxis: { type: "value", min: 1, max: 5 },
    series: [
      { name: "Customer stars", type: "bar", data: g.by_star.map((b) => b.avg_actual), itemStyle: { color: "#6b7389" } },
      { name: "Fused stars", type: "bar", data: g.by_star.map((b) => b.avg_fused), itemStyle: { color: "#8b7bff" } },
    ],
  };
  const rowH = (n: number) => Math.max(180, 56 + n * 34);

  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-2xl font-bold">Who likes what</h1>
        <p className="text-slate-500">
          How many customers are positive, neutral and negative, and how far the stars sit from what the words say.
          {d.low_sample && <span className="text-amber-700"> Only {d.n} reviews, so treat these as rough.</span>}
        </p>
      </header>

      <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
        <Stat label="Reviews scored" value={String(o.n)} />
        <Stat label="Positive" value={pct(o.pos_share)} note={`${o.pos} reviews`} color={POS} />
        <Stat label="Neutral" value={pct(o.neu_share)} note={`${o.neu} reviews`} />
        <Stat label="Negative" value={pct(o.neg_share)} note={`${o.neg} reviews`} color={NEG} />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="Overall sentiment" sub="What the text says, after the model ensemble"><Chart option={donut as never} height={280} /></Panel>
        <Panel title="Sentiment at each star level" sub="Share of reviews at each rating. A 5 star review can still be negative in words."><Chart option={stacked(d.by_star, false, (k) => k + " star") as never} height={280} /></Panel>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Panel title="By product" sub="The 15 products with the most reviews"><Chart option={stacked(d.by_product, true) as never} height={rowH(d.by_product.length)} /></Panel>
        <Panel title="By aspect" sub="Sentence mentions that are positive, neutral or negative"><Chart option={stacked(d.by_aspect, true) as never} height={rowH(d.by_aspect.length)} /></Panel>
      </div>

      {d.by_language.length > 1 && (
        <Panel title="By language"><Chart option={stacked(d.by_language, true) as never} height={rowH(d.by_language.length)} /></Panel>
      )}

      <header className="pt-4">
        <h2 className="text-xl font-bold">Fused stars against customer stars</h2>
        <p className="text-slate-500">
          Gap = fused stars minus the stars the customer gave. Above zero the customer under-rated (the words are happier); below zero they over-rated.
        </p>
      </header>

      {g.n === 0 ? (
        <p className="text-slate-500">No reviews with both a rating and a score yet.</p>
      ) : (
        <>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <Stat label="Reviews compared" value={String(g.n)} />
            <Stat label="Average gap" value={g.mean_gap == null ? "-" : (g.mean_gap > 0 ? "+" : "") + g.mean_gap.toFixed(2)} note={`average size ${g.mean_abs_gap?.toFixed(2) ?? "-"} stars`} />
            <Stat label="Under-rated" value={String(g.underrated)} note="words happier than the stars" color={UNDER} />
            <Stat label="Over-rated" value={String(g.overrated)} note="stars happier than the words" color={OVER} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Panel title="How big is the gap?" sub="Amber: stars too high. Cyan: stars too low."><Chart option={gapBars as never} height={280} /></Panel>
            <Panel title="Customer stars vs fused stars" sub="Average fused stars at each rating"><Chart option={perStar as never} height={280} /></Panel>
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Panel title="Customer vs fused" sub="Bright cells off the diagonal are disagreements"><Chart option={heat(g.fused_matrix, "Fused stars") as never} height={300} /></Panel>
            <Panel title="Customer vs predicted" sub={g.predicted_n ? `${g.predicted_n} reviews with a predicted star rating (not Hindi or Hinglish)` : "No predicted star ratings yet"}>
              <Chart option={heat(g.predicted_matrix, "Predicted stars (nlptown)") as never} height={300} />
            </Panel>
          </div>
        </>
      )}

      {models.data && models.data.models.length > 0 && (
        <Panel title="Model comparison" sub={models.data.note}>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] text-sm">
              <thead className="text-left text-slate-500">
                <tr><th className="py-1">Model</th><th>Reviews</th><th>Negative</th><th>Neutral</th><th>Positive</th><th>Avg expected stars</th><th>Agrees with ensemble</th><th>Agrees with stars</th></tr>
              </thead>
              <tbody>
                {models.data.models.map((m) => (
                  <tr key={m.model} className="border-t">
                    <td className="py-1.5 font-medium">{m.model}</td><td>{m.reviews}</td><td>{m.neg}</td><td>{m.neu}</td><td>{m.pos}</td>
                    <td>{m.avg_expected_stars ?? "-"}</td><td>{pct(m.agree_with_ensemble)}</td><td>{pct(m.agree_with_stars)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
      <p className="text-xs text-slate-400">{d.note}</p>
    </div>
  );
}
'@ | Set-Content -Encoding ascii frontend\src\Distribution.tsx

@'
"""Step 26 patcher. Safe to run twice."""
import io

def edit(path, marker, fn):
    s = io.open(path, encoding="utf-8").read()
    if marker in s:
        print("already applied:", path); return
    s2 = fn(s)
    assert s2 != s, "no change: " + path
    io.open(path, "w", encoding="utf-8", newline="\n").write(s2)
    print("patched:", path)

def once(s, old, new):
    assert s.count(old) == 1, "anchor not found exactly once: " + old[:70]
    return s.replace(old, new)

def main_py(s):
    s = once(s, "from app.api.evaluation import router as evaluation_router\n",
             "from app.api.distribution import router as distribution_router\nfrom app.api.evaluation import router as evaluation_router\n")
    return once(s, "app.include_router(sentiment_router, dependencies=protected)\n",
                "app.include_router(sentiment_router, dependencies=protected)\napp.include_router(distribution_router, dependencies=protected)\n")
edit("backend/app/main.py", "distribution_router", main_py)

edit("frontend/src/Layout.tsx", "/distribution", lambda s: once(s,
    '    { to: "/sentiment", label: "Sentiment", icon: "smile" },\n',
    '    { to: "/sentiment", label: "Sentiment", icon: "smile" },\n    { to: "/distribution", label: "Who Likes What", icon: "compare" },\n'))

def main_tsx(s):
    s = once(s, 'import Sentiment from "./Sentiment";\n', 'import Sentiment from "./Sentiment";\nimport Distribution from "./Distribution";\n')
    return once(s, '            <Route path="sentiment" element={<Sentiment />} />\n',
                '            <Route path="sentiment" element={<Sentiment />} />\n            <Route path="distribution" element={<Distribution />} />\n')
edit("frontend/src/main.tsx", "<Distribution", main_tsx)
'@ | Set-Content -Encoding ascii patch_step26.py
python patch_step26.py
Remove-Item patch_step26.py

Write-Host 'Step 26 files written.'
