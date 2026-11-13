import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, send } from "./api";
import Chart from "./Chart";

type Queue = {
  labelled: number; total: number; remaining: number;
  item: { review_id: number; product: string; stars: number | null; text: string; language: string | null } | null;
};
type PerClass = Record<string, { precision: number | null; recall: number | null; f1: number | null; support: number }>;
type Block = {
  n: number; macro_f1: number | null; accuracy: number | null; macro_f1_ci: number[] | null;
  per_class: PerClass; confusion: Record<string, Record<string, number>>;
};
type Evaluation = {
  labelled: number; low_sample: boolean; min_labels: number; note: string;
  text_models?: (Block & { model: string })[]; fused_text_label?: Block; stars_only?: Block;
  by_language?: Record<string, { n: number; macro_f1: number | null; low_sample: boolean }>;
  mismatch_flags?: { n: number; true_mismatches: number; flagged: number; precision: number | null; recall: number | null };
  calibration?: { n: number; ece: number | null; bins: { lo: number; hi: number; n: number; mean_confidence: number; accuracy: number }[] };
  gold_vs_stars_disagreement?: number | null;
};

const f = (x: number | null | undefined, d = 2) => (x == null ? "n/a" : x.toFixed(d));
const NAMES: Record<string, string> = { neg: "Negative", neu: "Neutral", pos: "Positive" };

function Labeller() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["label-queue"], queryFn: () => api<Queue>("/labels/queue") });
  const [label, setLabel] = useState<string>("");
  const [mismatch, setMismatch] = useState<"" | "yes" | "no">("");
  const save = useMutation({
    mutationFn: (v: { review_id: number }) =>
      send("POST", "/labels", { review_id: v.review_id, label, mismatch_label: mismatch === "" ? null : mismatch === "yes", source: "gold" }),
    onSuccess: () => { setLabel(""); setMismatch(""); qc.invalidateQueries({ queryKey: ["label-queue"] }); qc.invalidateQueries({ queryKey: ["evaluation"] }); },
  });
  if (q.isLoading) return <p className="text-slate-500">Loading...</p>;
  if (q.error || !q.data) return <p className="text-red-600">Could not reach the API. Is uvicorn running on port 8010?</p>;
  const d = q.data;
  const btn = (active: boolean) => "rounded-md px-3 py-1 text-sm " + (active ? "bg-indigo-600 text-white" : "border text-slate-700 hover:bg-slate-100");

  return (
    <section className="rounded-xl bg-white p-4 shadow-sm">
      <p className="mb-1 text-sm text-slate-600">{d.labelled} of {d.total} reviews labelled. The plan asks for 300 to 500.</p>
      <div className="mb-3 h-2 rounded bg-slate-100"><div className="h-2 rounded bg-indigo-600" style={{ width: (d.total ? (100 * d.labelled) / d.total : 0) + "%" }} /></div>
      {d.item == null ? (
        <p className="text-slate-500">Every review is labelled.</p>
      ) : (
        <div>
          <div className="text-xs text-slate-500">{d.item.product} | customer gave {d.item.stars ?? "no"} stars | {d.item.language ?? "?"}</div>
          <p className="my-3 rounded-md bg-slate-50 p-3 text-sm">{d.item.text}</p>
          <p className="mb-1 text-sm font-medium">What does the text say, ignoring the stars?</p>
          <div className="flex gap-2">
            {["neg", "neu", "pos"].map((l) => <button key={l} className={btn(label === l)} onClick={() => setLabel(l)}>{NAMES[l]}</button>)}
          </div>
          <p className="mb-1 mt-3 text-sm font-medium">Does the text disagree with the star rating? (optional)</p>
          <div className="flex gap-2">
            {([["yes", "Yes"], ["no", "No"], ["", "Not sure"]] as const).map(([v, t]) => <button key={t} className={btn(mismatch === v)} onClick={() => setMismatch(v)}>{t}</button>)}
          </div>
          <button className="mt-4 rounded-md bg-emerald-600 px-4 py-1.5 text-sm text-white disabled:opacity-50"
            disabled={!label || save.isPending} onClick={() => save.mutate({ review_id: d.item!.review_id })}>Save and next</button>
          {save.error && <p className="mt-2 text-sm text-red-600">{(save.error as Error).message}</p>}
        </div>
      )}
      <a className="mt-4 inline-block text-sm text-indigo-600 underline" href="/api/labels/export.csv">Download labels as CSV (keep a backup)</a>
    </section>
  );
}

function Results() {
  const e = useQuery({ queryKey: ["evaluation"], queryFn: () => api<Evaluation>("/evaluation") });
  if (e.isLoading) return <p className="text-slate-500">Loading...</p>;
  if (e.error || !e.data) return <p className="text-red-600">Could not reach the API. Is uvicorn running on port 8010?</p>;
  const d = e.data;
  if (d.labelled === 0) return <p className="text-slate-500">{d.note}</p>;
  const m = d.text_models?.[0];

  const cal = d.calibration;
  const calOpt = cal && cal.bins.length ? {
    grid: { left: 45, right: 10, top: 30, bottom: 30 }, legend: { top: 0 }, tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: cal.bins.map((b) => `${Math.round(b.lo * 100)}-${Math.round(b.hi * 100)}%`) },
    yAxis: { type: "value", min: 0, max: 1 },
    series: [
      { name: "Claimed confidence", type: "line", data: cal.bins.map((b) => b.mean_confidence), itemStyle: { color: "#94a3b8" }, lineStyle: { type: "dashed" } },
      { name: "Actually right", type: "bar", data: cal.bins.map((b) => b.accuracy), itemStyle: { color: "#4f46e5" } },
    ],
  } : null;

  const row = (name: string, b?: Block) => b && (
    <tr key={name} className="border-t"><td className="py-1">{name}</td><td>{b.n}</td><td>{f(b.macro_f1)}{b.macro_f1_ci && <span className="text-slate-400"> ({f(b.macro_f1_ci[0])} to {f(b.macro_f1_ci[1])})</span>}</td><td>{f(b.accuracy)}</td></tr>
  );

  return (
    <div className="space-y-4">
      {d.low_sample && <p className="rounded-md bg-amber-50 p-3 text-sm text-amber-700">Warning: only {d.labelled} labelled reviews (the minimum is {d.min_labels}). Treat every number below as a first look.</p>}
      <section className="rounded-xl bg-white p-4 shadow-sm">
        <h2 className="mb-2 font-semibold">How well does each method read sentiment?</h2>
        <table className="w-full text-sm">
          <thead className="text-left text-slate-500"><tr><th>Method</th><th>Reviews</th><th>Macro F1 (95% range)</th><th>Accuracy</th></tr></thead>
          <tbody>
            {d.text_models?.map((t) => row(t.model, t))}
            {row("Fused text label", d.fused_text_label)}
            {row("Stars alone", d.stars_only)}
          </tbody>
        </table>
        <p className="mt-2 text-xs text-slate-400">{d.note} A model stays only if it beats stars alone and the TF-IDF baseline (python -m scripts.baseline_tfidf).</p>
        {d.gold_vs_stars_disagreement != null && <p className="mt-1 text-sm text-slate-600">Stars and your labels disagree on {f(d.gold_vs_stars_disagreement * 100, 0)}% of reviews.</p>}
      </section>

      {m && (
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">Where does {m.model} go wrong?</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th>Your label</th><th>Predicted negative</th><th>Predicted neutral</th><th>Predicted positive</th></tr></thead>
            <tbody>
              {["neg", "neu", "pos"].map((g) => (
                <tr key={g} className="border-t"><td className="py-1">{NAMES[g]} ({m.per_class[g].support})</td>
                  {["neg", "neu", "pos"].map((p) => <td key={p} className={g === p ? "font-semibold" : ""}>{m.confusion[g][p]}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </section>
      )}

      {d.mismatch_flags && (
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">Mismatch flags</h2>
          <p className="text-sm">
            Of {d.mismatch_flags.flagged} reviews flagged, {f(d.mismatch_flags.precision == null ? null : d.mismatch_flags.precision * 100, 0)}% were real mismatches.
            Of {d.mismatch_flags.true_mismatches} real mismatches you marked, {f(d.mismatch_flags.recall == null ? null : d.mismatch_flags.recall * 100, 0)}% were caught ({d.mismatch_flags.n} reviews answered).
          </p>
        </section>
      )}

      {calOpt && cal && (
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">Does "90% sure" mean right 90% of the time?</h2>
          <Chart option={calOpt as never} />
          <p className="text-xs text-slate-400">Expected calibration error {f(cal.ece, 3)} on {cal.n} reviews. Bars below the dashed line mean the model is overconfident.</p>
        </section>
      )}

      {d.by_language && (
        <section className="rounded-xl bg-white p-4 shadow-sm">
          <h2 className="mb-2 font-semibold">By language</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-slate-500"><tr><th>Language</th><th>Reviews</th><th>Macro F1</th></tr></thead>
            <tbody>{Object.entries(d.by_language).map(([l, v]) => (
              <tr key={l} className="border-t"><td className="py-1">{l}</td><td>{v.n}</td><td>{f(v.macro_f1)}{v.low_sample && <span className="ml-2 text-xs text-amber-600">few labels</span>}</td></tr>
            ))}</tbody>
          </table>
        </section>
      )}
    </div>
  );
}

export default function Label() {
  const [tab, setTab] = useState<"label" | "results">("label");
  return (
    <div className="mx-auto max-w-4xl space-y-4 p-6">
      <header>
        <h1 className="text-2xl font-bold">Gold labels and evaluation</h1>
        <p className="text-slate-600">Label reviews by hand, then measure the models against your labels, not against stars.</p>
      </header>
      <div className="flex gap-2 text-sm">
        {([["label", "Label reviews"], ["results", "Results"]] as const).map(([k, t]) => (
          <button key={k} onClick={() => setTab(k)} className={"rounded-md px-3 py-1 " + (tab === k ? "bg-indigo-600 text-white" : "border text-slate-600 hover:bg-slate-100")}>{t}</button>
        ))}
      </div>
      {tab === "label" ? <Labeller /> : <Results />}
    </div>
  );
}
