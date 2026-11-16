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
