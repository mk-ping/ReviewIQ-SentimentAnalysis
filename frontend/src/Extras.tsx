import type { ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import Chart from "./Chart";

type Absa = {
  available: boolean; command?: string; model?: string; created?: string; n?: number; agree_rate?: number | null; kappa?: number | null;
  confusion?: Record<string, Record<string, number>>; by_aspect?: { aspect: string; n: number; agree_rate: number }[];
  disagreements?: { aspect: string; sentence: string; ours: string; absa: string }[];
};
type Topics = {
  available: boolean; command?: string; created?: string; sentences?: number; outliers?: number;
  topics?: { topic: number; size: number; words: string[]; dominant_aspect: string; general_share: number; emerging: boolean; examples: string[] }[];
};

const pct = (x: number | null | undefined) => (x == null ? "-" : Math.round(x * 100) + "%");
const NAMES: Record<string, string> = { neg: "Negative", neu: "Neutral", pos: "Positive" };

function Panel({ title, sub, children }: { title: string; sub: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4">
      <h2 className="font-semibold">{title}</h2>
      <p className="mb-3 text-sm text-slate-500">{sub}</p>
      {children}
    </section>
  );
}

function NotRun({ command }: { command?: string }) {
  return (
    <div className="rounded-lg border border-dashed border-slate-300 p-4 text-sm text-slate-500">
      Not run yet for your account. In the backend folder, run:
      <pre className="mt-2 overflow-x-auto rounded bg-slate-100 p-2 text-slate-800">{command}</pre>
      Then reload this page.
    </div>
  );
}

export default function Extras() {
  const absa = useQuery({ queryKey: ["extras-absa"], queryFn: () => api<Absa>("/extras/absa") });
  const topics = useQuery({ queryKey: ["extras-topics"], queryFn: () => api<Topics>("/extras/topics") });
  const a = absa.data, t = topics.data;
  const bars = a?.available && a.by_aspect ? {
    grid: { left: 90, right: 16, top: 10, bottom: 24 }, tooltip: { trigger: "axis" },
    xAxis: { type: "value", max: 100, axisLabel: { formatter: "{value}%" } },
    yAxis: { type: "category", inverse: true, data: a.by_aspect.map((x) => x.aspect) },
    series: [{ type: "bar", data: a.by_aspect.map((x) => Math.round(x.agree_rate * 100)), itemStyle: { color: "#8b7bff" } }],
  } : null;
  return (
    <div className="mx-auto max-w-6xl space-y-6 p-4 sm:p-6">
      <header>
        <h1 className="text-2xl font-bold">Model checks</h1>
        <p className="text-slate-500">Two optional checks that run on your machine: an independent model that re-scores our aspect sentiment, and topic discovery for complaints the seven aspects miss.</p>
      </header>

      <Panel title="Aspect sentiment against an ABSA model" sub="An independent aspect-based model reads each sentence with its aspect and gives its own label. High agreement means our sentence scores can be trusted.">
        {absa.isLoading ? <p className="text-slate-500">Loading...</p> : !a?.available ? <NotRun command={a?.command ?? "python -m scripts.absa_validate"} /> : (
          <>
            <div className="mb-4 grid grid-cols-2 gap-4 md:grid-cols-4">
              <div><div className="text-sm text-slate-500">Sentences checked</div><div className="text-2xl font-semibold">{a.n}</div></div>
              <div><div className="text-sm text-slate-500">Agreement</div><div className="text-2xl font-semibold">{pct(a.agree_rate)}</div></div>
              <div><div className="text-sm text-slate-500">Cohen&apos;s kappa</div><div className="text-2xl font-semibold">{a.kappa ?? "-"}</div><div className="text-xs text-slate-400">1 perfect, 0 chance</div></div>
              <div><div className="text-sm text-slate-500">Model</div><div className="truncate text-sm">{a.model}</div><div className="text-xs text-slate-400">{a.created}</div></div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div><h3 className="mb-1 text-sm font-medium">Agreement by aspect</h3>{bars && <Chart option={bars as never} height={Math.max(180, 40 + (a.by_aspect?.length ?? 0) * 32)} />}</div>
              <div>
                <h3 className="mb-1 text-sm font-medium">Our label (rows) against the ABSA label (columns)</h3>
                <table className="w-full text-sm"><thead className="text-left text-slate-500"><tr><th></th>{["neg", "neu", "pos"].map((k) => <th key={k}>{NAMES[k]}</th>)}</tr></thead>
                  <tbody>{(Object.entries(a.confusion ?? {}) as [string, Record<string, number>][]).map(([o, row]) => (
                    <tr key={o} className="border-t"><td className="py-1.5 font-medium">{NAMES[o]}</td>{["neg", "neu", "pos"].map((k) => <td key={k} style={o === k ? { color: "#34d399" } : undefined}>{row[k]}</td>)}</tr>
                  ))}</tbody></table>
              </div>
            </div>
            {a.disagreements && a.disagreements.length > 0 && (
              <details className="mt-4 text-sm"><summary className="cursor-pointer text-slate-600">Examples where the two disagree</summary>
                <ul className="mt-2 space-y-2">{a.disagreements.map((d, i) => (
                  <li key={i} className="border-t pt-2"><span className="text-xs text-slate-500">{d.aspect}: we say {NAMES[d.ours]}, ABSA says {NAMES[d.absa]}</span><div>{d.sentence}</div></li>
                ))}</ul></details>
            )}
          </>
        )}
      </Panel>

      <Panel title="Complaint topics (BERTopic style)" sub="Negative sentences are embedded, clustered and named by their top words. Topics marked Emerging are mostly sentences the seven aspects tagged as general, so they point to something new.">
        {topics.isLoading ? <p className="text-slate-500">Loading...</p> : !t?.available ? <NotRun command={t?.command ?? "python -m scripts.topic_discovery"} /> : (
          <>
            <p className="mb-3 text-sm text-slate-500">{t.sentences} negative sentences, {t.topics?.length} topics, {t.outliers} not placed in any topic. {t.created}</p>
            <div className="space-y-3">
              {(t.topics ?? []).map((x) => (
                <div key={x.topic} className="rounded-lg border border-slate-200 p-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-medium">{x.words.slice(0, 4).join(", ") || "Topic " + x.topic}</span>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">{x.size} sentences</span>
                    <span className="rounded-full bg-indigo-50 px-2 py-0.5 text-xs text-indigo-700">main aspect: {x.dominant_aspect}</span>
                    {x.emerging && <span className="rounded-full bg-amber-100 px-2 py-0.5 text-xs text-amber-800">Emerging</span>}
                  </div>
                  <p className="mt-1 text-xs text-slate-400">{x.words.join(", ")}</p>
                  <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-600">{x.examples.map((e, i) => <li key={i}>{e}</li>)}</ul>
                </div>
              ))}
            </div>
          </>
        )}
      </Panel>
    </div>
  );
}
